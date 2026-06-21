package cache

import (
	"fmt"
	"sync"
	"time"

	lru "github.com/hashicorp/golang-lru/v2"
	"golang.org/x/sync/singleflight"
)

type ZipCache struct {
	mu        sync.Mutex
	maxBytes  int64
	usedBytes int64
	cache     *lru.Cache[string, []byte]
	sf        singleflight.Group
}

func New(maxSizeMB int, lifeWindow time.Duration) (*ZipCache, error) {
	_ = lifeWindow
	cache, err := lru.New[string, []byte](1_000_000)
	if err != nil {
		return nil, err
	}
	return &ZipCache{
		maxBytes: int64(maxSizeMB) * 1024 * 1024,
		cache:    cache,
	}, nil
}

func (c *ZipCache) Get(key string) ([]byte, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.cache.Get(key)
}

func (c *ZipCache) Set(key string, data []byte) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.setLocked(key, data)
}

func (c *ZipCache) setLocked(key string, data []byte) error {
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

	v, err, _ := c.sf.Do(key, func() (interface{}, error) {
		if data, ok := c.Get(key); ok {
			return data, nil
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
	return v.([]byte), nil
}

func (c *ZipCache) Evict(key string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if old, ok := c.cache.Peek(key); ok {
		c.usedBytes -= int64(len(old))
		c.cache.Remove(key)
	}
}

func (c *ZipCache) Close() error {
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
