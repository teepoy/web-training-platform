package cache

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"
)

const (
	cacheFileSuffix = ".cache"
	tempFilePrefix  = ".cache-write-"
)

type LocalFileCacheConfig struct {
	Dir             string
	TTL             time.Duration
	CleanupInterval time.Duration
	MaxBytes        int64
}

type LocalFileCleanupResult struct {
	ExpiredFiles int
	EvictedFiles int
	RemovedBytes int64
	UsedBytes    int64
	EntryCount   int
}

type fileEntry struct {
	path     string
	size     int64
	lastUsed time.Time
}

type LocalFileCache struct {
	mu        sync.Mutex
	config    LocalFileCacheConfig
	usedBytes int64
	stop      chan struct{}
	done      chan struct{}
	closeOne  sync.Once
}

func NewLocalFileCache(config LocalFileCacheConfig) (*LocalFileCache, error) {
	if strings.TrimSpace(config.Dir) == "" {
		return nil, errors.New("cache directory is required")
	}
	if config.TTL <= 0 {
		return nil, errors.New("cache TTL must be greater than zero")
	}
	if config.CleanupInterval <= 0 {
		return nil, errors.New("cache cleanup interval must be greater than zero")
	}
	if config.MaxBytes < 0 {
		return nil, errors.New("cache max bytes must not be negative")
	}
	if err := os.MkdirAll(config.Dir, 0o750); err != nil {
		return nil, fmt.Errorf("create cache directory: %w", err)
	}

	cache := &LocalFileCache{
		config: config,
		stop:   make(chan struct{}),
		done:   make(chan struct{}),
	}
	if _, err := cache.Cleanup(); err != nil {
		return nil, fmt.Errorf("initial cache cleanup: %w", err)
	}
	go cache.cleanupLoop()
	return cache, nil
}

func (c *LocalFileCache) Get(key string) ([]byte, bool, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	path := c.pathForKey(key)
	info, err := os.Stat(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, fmt.Errorf("stat cache entry: %w", err)
	}

	now := time.Now()
	if isExpired(info.ModTime(), now, c.config.TTL) {
		if err := os.Remove(path); err != nil && !errors.Is(err, os.ErrNotExist) {
			return nil, false, fmt.Errorf("remove expired cache entry: %w", err)
		}
		c.usedBytes = subtractFloorZero(c.usedBytes, info.Size())
		return nil, false, nil
	}

	data, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, fmt.Errorf("read cache entry: %w", err)
	}
	if err := os.Chtimes(path, now, now); err != nil {
		return nil, false, fmt.Errorf("update cache entry last-used time: %w", err)
	}
	return data, true, nil
}

func (c *LocalFileCache) Set(key string, data []byte) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	size := int64(len(data))
	if c.config.MaxBytes > 0 && size > c.config.MaxBytes {
		return fmt.Errorf("entry %d bytes exceeds cache max %d bytes", size, c.config.MaxBytes)
	}

	target := c.pathForKey(key)
	var oldSize int64
	if info, err := os.Stat(target); err == nil {
		oldSize = info.Size()
	} else if !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("stat existing cache entry: %w", err)
	}
	baseUsedBytes := subtractFloorZero(c.usedBytes, oldSize)
	if c.config.MaxBytes > 0 && baseUsedBytes+size > c.config.MaxBytes {
		entries, err := c.scanLocked(time.Now(), target)
		if err != nil {
			return err
		}
		baseUsedBytes, err = c.enforceMaxBytesLocked(entries, size)
		if err != nil {
			return err
		}
		c.usedBytes = baseUsedBytes + oldSize
	}

	temp, err := os.CreateTemp(c.config.Dir, tempFilePrefix)
	if err != nil {
		return fmt.Errorf("create temporary cache entry: %w", err)
	}
	tempPath := temp.Name()
	defer func() {
		_ = temp.Close()
		_ = os.Remove(tempPath)
	}()
	if err := temp.Chmod(0o600); err != nil {
		return fmt.Errorf("set temporary cache entry permissions: %w", err)
	}
	if _, err := temp.Write(data); err != nil {
		return fmt.Errorf("write temporary cache entry: %w", err)
	}
	if err := temp.Sync(); err != nil {
		return fmt.Errorf("sync temporary cache entry: %w", err)
	}
	if err := temp.Close(); err != nil {
		return fmt.Errorf("close temporary cache entry: %w", err)
	}
	if err := os.Rename(tempPath, target); err != nil {
		return fmt.Errorf("publish cache entry: %w", err)
	}
	c.usedBytes = baseUsedBytes + size
	return nil
}

func (c *LocalFileCache) Evict(key string) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	path := c.pathForKey(key)
	info, statErr := os.Stat(path)
	if statErr != nil && !errors.Is(statErr, os.ErrNotExist) {
		return fmt.Errorf("stat cache entry for eviction: %w", statErr)
	}
	if err := os.Remove(path); err != nil && !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("evict cache entry: %w", err)
	}
	if statErr == nil {
		c.usedBytes = subtractFloorZero(c.usedBytes, info.Size())
	}
	return nil
}

func (c *LocalFileCache) Cleanup() (LocalFileCleanupResult, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	now := time.Now()
	entries, err := c.scanLocked(now, "")
	if err != nil {
		return LocalFileCleanupResult{}, err
	}
	result := LocalFileCleanupResult{}
	active := entries[:0]
	for _, entry := range entries {
		if isExpired(entry.lastUsed, now, c.config.TTL) {
			if err := removeEntry(entry); err != nil {
				return LocalFileCleanupResult{}, err
			}
			result.ExpiredFiles++
			result.RemovedBytes += entry.size
			continue
		}
		active = append(active, entry)
	}
	sort.Slice(active, func(i, j int) bool {
		return active[i].lastUsed.Before(active[j].lastUsed)
	})
	usedBytes := totalSize(active)
	if c.config.MaxBytes > 0 {
		for len(active) > 0 && usedBytes > c.config.MaxBytes {
			entry := active[0]
			active = active[1:]
			if err := removeEntry(entry); err != nil {
				return LocalFileCleanupResult{}, err
			}
			usedBytes -= entry.size
			result.EvictedFiles++
			result.RemovedBytes += entry.size
		}
	}
	result.UsedBytes = usedBytes
	result.EntryCount = len(active)
	c.usedBytes = usedBytes
	return result, nil
}

func (c *LocalFileCache) Close() error {
	c.closeOne.Do(func() {
		close(c.stop)
		<-c.done
	})
	return nil
}

func (c *LocalFileCache) pathForKey(key string) string {
	digest := sha256.Sum256([]byte(key))
	return filepath.Join(c.config.Dir, hex.EncodeToString(digest[:])+cacheFileSuffix)
}

func (c *LocalFileCache) cleanupLoop() {
	defer close(c.done)
	ticker := time.NewTicker(c.config.CleanupInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ticker.C:
			result, err := c.Cleanup()
			if err != nil {
				log.Printf("image cache cleanup failed: %v", err)
				continue
			}
			if result.ExpiredFiles > 0 || result.EvictedFiles > 0 {
				log.Printf(
					"image cache cleanup removed expired=%d evicted=%d bytes=%d remaining_files=%d remaining_bytes=%d",
					result.ExpiredFiles,
					result.EvictedFiles,
					result.RemovedBytes,
					result.EntryCount,
					result.UsedBytes,
				)
			}
		case <-c.stop:
			return
		}
	}
}

func (c *LocalFileCache) scanLocked(now time.Time, excludedPath string) ([]fileEntry, error) {
	dirEntries, err := os.ReadDir(c.config.Dir)
	if err != nil {
		return nil, fmt.Errorf("scan cache directory: %w", err)
	}
	entries := make([]fileEntry, 0, len(dirEntries))
	for _, dirEntry := range dirEntries {
		path := filepath.Join(c.config.Dir, dirEntry.Name())
		if strings.HasPrefix(dirEntry.Name(), tempFilePrefix) {
			info, infoErr := dirEntry.Info()
			if infoErr != nil {
				if errors.Is(infoErr, os.ErrNotExist) {
					continue
				}
				return nil, fmt.Errorf("stat temporary cache entry: %w", infoErr)
			}
			if isExpired(info.ModTime(), now, c.config.TTL) {
				if removeErr := os.Remove(path); removeErr != nil && !errors.Is(removeErr, os.ErrNotExist) {
					return nil, fmt.Errorf("remove stale temporary cache entry: %w", removeErr)
				}
			}
			continue
		}
		if dirEntry.IsDir() || !isCacheFileName(dirEntry.Name()) || path == excludedPath {
			continue
		}
		info, infoErr := dirEntry.Info()
		if infoErr != nil {
			if errors.Is(infoErr, os.ErrNotExist) {
				continue
			}
			return nil, fmt.Errorf("stat cache entry: %w", infoErr)
		}
		if !info.Mode().IsRegular() {
			continue
		}
		entries = append(entries, fileEntry{
			path:     path,
			size:     info.Size(),
			lastUsed: info.ModTime(),
		})
	}
	return entries, nil
}

func (c *LocalFileCache) enforceMaxBytesLocked(entries []fileEntry, incomingBytes int64) (int64, error) {
	if c.config.MaxBytes == 0 {
		return totalSize(entries), nil
	}
	now := time.Now()
	active := entries[:0]
	for _, entry := range entries {
		if isExpired(entry.lastUsed, now, c.config.TTL) {
			if err := removeEntry(entry); err != nil {
				return 0, err
			}
			continue
		}
		active = append(active, entry)
	}
	sort.Slice(active, func(i, j int) bool {
		return active[i].lastUsed.Before(active[j].lastUsed)
	})
	usedBytes := totalSize(active)
	for len(active) > 0 && usedBytes+incomingBytes > c.config.MaxBytes {
		entry := active[0]
		active = active[1:]
		if err := removeEntry(entry); err != nil {
			return 0, err
		}
		usedBytes -= entry.size
	}
	return usedBytes, nil
}

func isExpired(lastUsed, now time.Time, ttl time.Duration) bool {
	return !lastUsed.Add(ttl).After(now)
}

func totalSize(entries []fileEntry) int64 {
	var size int64
	for _, entry := range entries {
		size += entry.size
	}
	return size
}

func subtractFloorZero(value, amount int64) int64 {
	if amount >= value {
		return 0
	}
	return value - amount
}

func isCacheFileName(name string) bool {
	digest := strings.TrimSuffix(name, cacheFileSuffix)
	if digest == name || len(digest) != sha256.Size*2 {
		return false
	}
	_, err := hex.DecodeString(digest)
	return err == nil
}

func removeEntry(entry fileEntry) error {
	if err := os.Remove(entry.path); err != nil && !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("remove cache entry %s: %w", entry.path, err)
	}
	return nil
}
