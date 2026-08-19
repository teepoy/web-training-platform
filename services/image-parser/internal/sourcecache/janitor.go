// Package sourcecache owns the display server's shared-cache eviction policy.
// It is intentionally separate from filesource and from job-owned cleanup.
package sourcecache

import (
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	"image-parser/internal/filesource"
)

type CleanupResult struct {
	Expired        int
	Evicted        int
	RemovedBytes   int64
	RemainingFiles int
	RemainingBytes int64
}

type cacheFile struct {
	path     string
	size     int64
	lastUsed time.Time
}

type Janitor struct {
	source   *filesource.Source
	ttl      time.Duration
	maxBytes int64
	stop     chan struct{}
	done     chan struct{}
	close    sync.Once
	running  bool
}

func New(source *filesource.Source, ttl time.Duration, maxBytes int64) (*Janitor, error) {
	if source == nil {
		return nil, fmt.Errorf("shared cache source is required")
	}
	if source.Kind() != filesource.KindDirectory || source.Ownership() != filesource.OwnershipSharedCache {
		return nil, fmt.Errorf("cache janitor requires a shared-cache directory source")
	}
	if ttl <= 0 {
		return nil, fmt.Errorf("cache TTL must be greater than zero")
	}
	if maxBytes < 0 {
		return nil, fmt.Errorf("cache max bytes must not be negative")
	}
	return &Janitor{
		source:   source,
		ttl:      ttl,
		maxBytes: maxBytes,
		stop:     make(chan struct{}),
		done:     make(chan struct{}),
	}, nil
}

func Start(source *filesource.Source, ttl, interval time.Duration, maxBytes int64) (*Janitor, error) {
	if interval <= 0 {
		return nil, fmt.Errorf("cache cleanup interval must be greater than zero")
	}
	janitor, err := New(source, ttl, maxBytes)
	if err != nil {
		return nil, err
	}
	if _, err := janitor.Cleanup(time.Now()); err != nil {
		return nil, err
	}
	janitor.running = true
	go janitor.run(interval)
	return janitor, nil
}

func (j *Janitor) Cleanup(now time.Time) (CleanupResult, error) {
	files, err := j.scan()
	if err != nil {
		return CleanupResult{}, err
	}
	result := CleanupResult{}
	active := files[:0]
	for _, file := range files {
		if now.Sub(file.lastUsed) > j.ttl {
			if err := os.Remove(file.path); err != nil && !os.IsNotExist(err) {
				return CleanupResult{}, fmt.Errorf("remove expired source cache file: %w", err)
			}
			result.Expired++
			result.RemovedBytes += file.size
			continue
		}
		active = append(active, file)
	}
	sort.Slice(active, func(left, right int) bool {
		return active[left].lastUsed.Before(active[right].lastUsed)
	})
	remainingBytes := totalBytes(active)
	for j.maxBytes > 0 && remainingBytes > j.maxBytes && len(active) > 0 {
		file := active[0]
		active = active[1:]
		if err := os.Remove(file.path); err != nil && !os.IsNotExist(err) {
			return CleanupResult{}, fmt.Errorf("evict source cache file: %w", err)
		}
		remainingBytes -= file.size
		result.Evicted++
		result.RemovedBytes += file.size
	}
	result.RemainingFiles = len(active)
	result.RemainingBytes = remainingBytes
	return result, nil
}

func (j *Janitor) Close() {
	j.close.Do(func() {
		close(j.stop)
		if j.running {
			<-j.done
		}
	})
}

func (j *Janitor) run(interval time.Duration) {
	defer close(j.done)
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case now := <-ticker.C:
			_, _ = j.Cleanup(now)
		case <-j.stop:
			return
		}
	}
}

func (j *Janitor) scan() ([]cacheFile, error) {
	files := make([]cacheFile, 0)
	err := filepath.WalkDir(j.source.Path(), func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.Type()&os.ModeSymlink != 0 {
			if entry.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		if entry.IsDir() {
			return nil
		}
		if strings.HasPrefix(entry.Name(), ".stage-") {
			return nil
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		if info.Mode().IsRegular() {
			files = append(files, cacheFile{path: path, size: info.Size(), lastUsed: info.ModTime()})
		}
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("scan source cache: %w", err)
	}
	return files, nil
}

func totalBytes(files []cacheFile) int64 {
	var total int64
	for _, file := range files {
		total += file.size
	}
	return total
}
