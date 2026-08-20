// Package artifactcache owns service-side source artifact publication and
// eviction. It caches downloaded files or directories, never parsed images.
package artifactcache

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"golang.org/x/sync/singleflight"

	"image-parser/internal/artifactcache/entrylock"
)

type Kind string

const (
	KindFile      Kind = "file"
	KindDirectory Kind = "directory"
)

type Ref struct {
	EntryID        string
	SourceIdentity string
	Revision       string
	Kind           Kind
}

func (r Ref) validate() error {
	if strings.TrimSpace(r.EntryID) == "" {
		return fmt.Errorf("artifact entry_id is required")
	}
	if strings.TrimSpace(r.SourceIdentity) == "" {
		return fmt.Errorf("artifact source_identity is required")
	}
	if strings.TrimSpace(r.Revision) == "" {
		return fmt.Errorf("artifact source revision is required")
	}
	if r.Kind != KindFile && r.Kind != KindDirectory {
		return fmt.Errorf("unsupported artifact kind %q", r.Kind)
	}
	return nil
}

func (r Ref) key() string {
	identity := r.EntryID + "\x00" + r.SourceIdentity + "\x00" + r.Revision + "\x00" + string(r.Kind)
	return fmt.Sprintf("%x", sha256.Sum256([]byte(identity)))
}

type DownloadFunc func(ctx context.Context, destination string) error

type Cache interface {
	GetOrDownload(ctx context.Context, ref Ref, download DownloadFunc) (string, error)
}

type Options struct {
	TTL             time.Duration
	CleanupInterval time.Duration
	MaxBytes        int64
}

type Manager struct {
	root      string
	objects   string
	options   Options
	requests  singleflight.Group
	stop      chan struct{}
	done      chan struct{}
	close     sync.Once
	hits      atomic.Int64
	misses    atomic.Int64
	downloads atomic.Int64
	evictions atomic.Int64
}

type Stats struct {
	Hits      int64
	Misses    int64
	Downloads int64
	Evictions int64
}

func New(root string, options Options) (*Manager, error) {
	if !filepath.IsAbs(root) {
		return nil, fmt.Errorf("artifact cache root must be absolute")
	}
	if options.TTL <= 0 {
		return nil, fmt.Errorf("artifact cache TTL must be greater than zero")
	}
	if options.CleanupInterval <= 0 {
		return nil, fmt.Errorf("artifact cache cleanup interval must be greater than zero")
	}
	if options.MaxBytes < 0 {
		return nil, fmt.Errorf("artifact cache max bytes must not be negative")
	}
	cleanRoot := filepath.Clean(root)
	if err := os.MkdirAll(filepath.Join(cleanRoot, "objects"), 0o750); err != nil {
		return nil, fmt.Errorf("create artifact cache: %w", err)
	}
	resolvedRoot, err := filepath.EvalSymlinks(cleanRoot)
	if err != nil {
		return nil, fmt.Errorf("resolve artifact cache root: %w", err)
	}
	manager := &Manager{
		root: resolvedRoot, objects: filepath.Join(resolvedRoot, "objects"), options: options,
		stop: make(chan struct{}), done: make(chan struct{}),
	}
	if _, err := manager.Cleanup(time.Now()); err != nil {
		return nil, err
	}
	go manager.run()
	return manager, nil
}

func (m *Manager) Root() string { return m.root }

func (m *Manager) Stats() Stats {
	return Stats{Hits: m.hits.Load(), Misses: m.misses.Load(), Downloads: m.downloads.Load(), Evictions: m.evictions.Load()}
}

func (m *Manager) Close() {
	m.close.Do(func() {
		close(m.stop)
		<-m.done
	})
}

func (m *Manager) GetOrDownload(ctx context.Context, ref Ref, download DownloadFunc) (string, error) {
	if err := ref.validate(); err != nil {
		return "", err
	}
	if download == nil {
		return "", fmt.Errorf("artifact downloader is required")
	}
	key := ref.key()
	result := m.requests.DoChan(key, func() (any, error) {
		return m.getOrDownload(ctx, ref, key, download)
	})
	select {
	case <-ctx.Done():
		return "", ctx.Err()
	case resolved := <-result:
		if resolved.Err != nil {
			return "", resolved.Err
		}
		path, ok := resolved.Val.(string)
		if !ok {
			return "", fmt.Errorf("artifact cache returned an invalid path")
		}
		return path, nil
	}
}

func (m *Manager) getOrDownload(ctx context.Context, ref Ref, key string, download DownloadFunc) (path string, resultErr error) {
	relative := filepath.Join("objects", key)
	lock, err := entrylock.Acquire(ctx, m.root, relative)
	if err != nil {
		return "", fmt.Errorf("lock artifact cache entry: %w", err)
	}
	defer func() {
		if err := lock.Release(); err != nil {
			resultErr = errors.Join(resultErr, err)
		}
	}()
	target := filepath.Join(m.objects, key)
	if hit, err := cacheHit(target, ref.Kind); err != nil {
		return "", err
	} else if hit {
		m.hits.Add(1)
		if err := touch(target); err != nil {
			return "", err
		}
		return target, nil
	}
	m.misses.Add(1)
	stagingRoot, err := os.MkdirTemp(m.objects, ".stage-"+key[:12]+"-")
	if err != nil {
		return "", fmt.Errorf("create artifact staging directory: %w", err)
	}
	defer os.RemoveAll(stagingRoot)
	staged := filepath.Join(stagingRoot, "artifact")
	if err := download(ctx, staged); err != nil {
		return "", fmt.Errorf("download artifact: %w", err)
	}
	if err := validateArtifact(staged, ref.Kind); err != nil {
		return "", err
	}
	if err := syncArtifact(staged); err != nil {
		return "", err
	}
	if err := os.Rename(staged, target); err != nil {
		return "", fmt.Errorf("publish artifact: %w", err)
	}
	m.downloads.Add(1)
	if err := syncDirectory(m.objects); err != nil {
		return "", err
	}
	return target, nil
}

func cacheHit(path string, kind Kind) (bool, error) {
	info, err := os.Lstat(path)
	if errors.Is(err, os.ErrNotExist) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("inspect cached artifact: %w", err)
	}
	if info.Mode()&os.ModeSymlink != 0 {
		return false, fmt.Errorf("cached artifact is a symlink")
	}
	if kind == KindFile && !info.Mode().IsRegular() {
		return false, fmt.Errorf("cached artifact is not a regular file")
	}
	if kind == KindDirectory && !info.IsDir() {
		return false, fmt.Errorf("cached artifact is not a directory")
	}
	return true, nil
}

func validateArtifact(path string, kind Kind) error {
	hit, err := cacheHit(path, kind)
	if err != nil {
		return fmt.Errorf("validate downloaded artifact: %w", err)
	}
	if !hit {
		return fmt.Errorf("artifact downloader did not create its destination")
	}
	if kind == KindDirectory {
		if err := filepath.WalkDir(path, func(_ string, entry fs.DirEntry, err error) error {
			if err != nil {
				return err
			}
			if entry.Type()&os.ModeSymlink != 0 {
				return fmt.Errorf("downloaded artifact directory contains a symlink")
			}
			return nil
		}); err != nil {
			return fmt.Errorf("validate downloaded artifact directory: %w", err)
		}
	}
	return nil
}

func syncArtifact(path string) error {
	info, err := os.Stat(path)
	if err != nil {
		return fmt.Errorf("stat downloaded artifact: %w", err)
	}
	if info.Mode().IsRegular() {
		file, err := os.Open(path)
		if err != nil {
			return fmt.Errorf("open downloaded artifact for sync: %w", err)
		}
		syncErr := file.Sync()
		closeErr := file.Close()
		if syncErr != nil || closeErr != nil {
			return errors.Join(syncErr, closeErr)
		}
		return nil
	}
	return filepath.WalkDir(path, func(current string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.Type().IsRegular() {
			return syncArtifact(current)
		}
		return nil
	})
}

func syncDirectory(path string) error {
	directory, err := os.Open(path)
	if err != nil {
		return fmt.Errorf("open artifact cache directory for sync: %w", err)
	}
	defer directory.Close()
	if err := directory.Sync(); err != nil {
		return fmt.Errorf("sync artifact cache directory: %w", err)
	}
	return nil
}

func touch(path string) error {
	now := time.Now()
	if err := os.Chtimes(path, now, now); err != nil {
		return fmt.Errorf("touch cached artifact: %w", err)
	}
	return nil
}

type cachedArtifact struct {
	name     string
	path     string
	size     int64
	lastUsed time.Time
}

func (m *Manager) Cleanup(now time.Time) (removed int, err error) {
	artifacts, err := m.scan()
	if err != nil {
		return 0, err
	}
	active := make([]cachedArtifact, 0, len(artifacts))
	for _, artifact := range artifacts {
		if now.Sub(artifact.lastUsed) > m.options.TTL {
			deleted, busy, err := m.removeIfUnlocked(artifact)
			if err != nil {
				return removed, err
			}
			if deleted {
				removed++
				m.evictions.Add(1)
			}
			if busy {
				active = append(active, artifact)
			}
			continue
		}
		active = append(active, artifact)
	}
	sort.Slice(active, func(i, j int) bool { return active[i].lastUsed.Before(active[j].lastUsed) })
	var total int64
	for _, artifact := range active {
		total += artifact.size
	}
	for len(active) > 0 && m.options.MaxBytes > 0 && total > m.options.MaxBytes {
		artifact := active[0]
		active = active[1:]
		deleted, busy, err := m.removeIfUnlocked(artifact)
		if err != nil {
			return removed, err
		}
		if busy {
			continue
		}
		if deleted {
			removed++
			m.evictions.Add(1)
			total -= artifact.size
		}
	}
	return removed, nil
}

func (m *Manager) scan() ([]cachedArtifact, error) {
	entries, err := os.ReadDir(m.objects)
	if err != nil {
		return nil, fmt.Errorf("scan artifact cache: %w", err)
	}
	artifacts := make([]cachedArtifact, 0, len(entries))
	for _, entry := range entries {
		if strings.HasPrefix(entry.Name(), ".stage-") || entry.Type()&os.ModeSymlink != 0 {
			continue
		}
		path := filepath.Join(m.objects, entry.Name())
		info, err := entry.Info()
		if err != nil {
			return nil, err
		}
		size, err := artifactSize(path, info)
		if err != nil {
			return nil, err
		}
		artifacts = append(artifacts, cachedArtifact{name: entry.Name(), path: path, size: size, lastUsed: info.ModTime()})
	}
	return artifacts, nil
}

func artifactSize(path string, info fs.FileInfo) (int64, error) {
	if info.Mode().IsRegular() {
		return info.Size(), nil
	}
	if !info.IsDir() {
		return 0, nil
	}
	var total int64
	err := filepath.WalkDir(path, func(current string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.Type().IsRegular() {
			info, err := entry.Info()
			if err != nil {
				return err
			}
			total += info.Size()
		}
		return nil
	})
	return total, err
}

func (m *Manager) removeIfUnlocked(artifact cachedArtifact) (removed bool, busy bool, resultErr error) {
	lock, acquired, err := entrylock.TryAcquire(m.root, filepath.Join("objects", artifact.name))
	if err != nil {
		return false, false, err
	}
	if !acquired {
		return false, true, nil
	}
	defer func() {
		if err := lock.Release(); err != nil {
			resultErr = errors.Join(resultErr, err)
		}
	}()
	if err := os.RemoveAll(artifact.path); err != nil {
		return false, false, fmt.Errorf("remove cached artifact: %w", err)
	}
	return true, false, nil
}

func (m *Manager) run() {
	defer close(m.done)
	ticker := time.NewTicker(m.options.CleanupInterval)
	defer ticker.Stop()
	for {
		select {
		case now := <-ticker.C:
			_, _ = m.Cleanup(now)
		case <-m.stop:
			return
		}
	}
}
