package cache

import (
	"fmt"

	lru "github.com/hashicorp/golang-lru/v2"
	"golang.org/x/sync/singleflight"
)

type RecordCache struct {
	cache *lru.Cache[string, []string]
	sf    singleflight.Group
}

func NewRecordCache() *RecordCache {
	c, _ := lru.New[string, []string](10000)
	return &RecordCache{cache: c}
}

func (c *RecordCache) Get(record string) ([]string, bool) {
	return c.cache.Get(record)
}

func (c *RecordCache) Set(record string, keys []string) {
	c.cache.Add(record, keys)
}

func (c *RecordCache) GetOrLoad(record string) ([]string, error) {
	if keys, ok := c.Get(record); ok {
		return keys, nil
	}
	return nil, fmt.Errorf("record %q not found (record cache is read-only in this mode)", record)
}
