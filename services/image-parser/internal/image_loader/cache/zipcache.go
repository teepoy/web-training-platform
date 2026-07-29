package cache

import (
	"fmt"
	"log"
	"sync"
	"time"

	lru "github.com/hashicorp/golang-lru/v2"
	"golang.org/x/sync/singleflight"
)

type Option func(*ZipCache)

func WithLocalFileCache(local *LocalFileCache) Option {
	return func(cache *ZipCache) {
		cache.local = local
	}
}

type ZipCache struct {
	mu        sync.Mutex
	maxBytes  int64
	usedBytes int64
	cache     *lru.Cache[string, []byte]
	local     *LocalFileCache
	sf        singleflight.Group
}

func New(maxSizeMB int, lifeWindow time.Duration, options ...Option) (*ZipCache, error) {
	_ = lifeWindow
	memory, err := lru.New[string, []byte](1_000_000)
	if err != nil {
		return nil, err
	}
	cache := &ZipCache{
		maxBytes: int64(maxSizeMB) * 1024 * 1024,
		cache:    memory,
	}
	for _, option := range options {
		option(cache)
	}
	return cache, nil
}

func (c *ZipCache) Get(key string) ([]byte, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.cache.Get(key)
}

func (c *ZipCache) Set(key string, data []byte) error {
	if int64(len(data)) > c.maxBytes {
		return fmt.Errorf("entry %d bytes exceeds cache max %d bytes", len(data), c.maxBytes)
	}
	if c.local != nil {
		if err := c.local.Set(key, data); err != nil {
			return fmt.Errorf("write local file cache: %w", err)
		}
	}
	return c.setMemory(key, data)
}

func (c *ZipCache) setMemory(key string, data []byte) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.setMemoryLocked(key, data)
}

func (c *ZipCache) setMemoryLocked(key string, data []byte) error {
	size := int64(len(data))

	if old, ok := c.cache.Peek(key); ok {
		c.usedBytes -= int64(len(old))
		c.cache.Remove(key)
	}

	for c.usedBytes+size > c.maxBytes && c.cache.Len() > 0 {
		_, oldest, _ := c.cache.GetOldest()
		c.cache.RemoveOldest()
		c.usedBytes -= int64(len(oldest))
	}

	if size > c.maxBytes {
		return fmt.Errorf("entry %d bytes exceeds cache max %d bytes", size, c.maxBytes)
	}

	c.cache.Add(key, data)
	c.usedBytes += size
	return nil
}

func (c *ZipCache) GetOrLoad(key string, loader func() ([]byte, error)) ([]byte, error) {
	if data, ok := c.Get(key); ok {
		return data, nil
	}

	value, err, _ := c.sf.Do(key, func() (interface{}, error) {
		if data, ok := c.Get(key); ok {
			return data, nil
		}
		if c.local != nil {
			data, ok, err := c.local.Get(key)
			if err != nil {
				return nil, fmt.Errorf("read local file cache: %w", err)
			}
			if ok {
				if err := c.setMemory(key, data); err != nil {
					return nil, err
				}
				return data, nil
			}
		}
		data, err := loader()
		if err != nil {
			return nil, err
		}
		if err := c.Set(key, data); err != nil {
			return nil, err
		}
		return data, nil
	})
	if err != nil {
		return nil, err
	}
	return value.([]byte), nil
}

func (c *ZipCache) Evict(key string) {
	c.mu.Lock()
	if old, ok := c.cache.Peek(key); ok {
		c.usedBytes -= int64(len(old))
		c.cache.Remove(key)
	}
	c.mu.Unlock()

	if c.local != nil {
		if err := c.local.Evict(key); err != nil {
			log.Printf("evict local file cache entry failed: %v", err)
		}
	}
}

func (c *ZipCache) Close() error {
	if c.local != nil {
		return c.local.Close()
	}
	return nil
}

func (c *ZipCache) Stats() (usedBytes int64, maxBytes int64, entryCount int) {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.usedBytes, c.maxBytes, c.cache.Len()
}

func CacheKey(bucket, key string) string {
	return bucket + "/" + key
}
