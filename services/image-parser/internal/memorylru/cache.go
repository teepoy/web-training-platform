// Package memorylru provides a small bounded in-memory LRU for immutable
// metadata. Artifact bytes remain owned by artifactcache.
package memorylru

import (
	"container/list"
	"fmt"
	"sync"
)

type entry[K comparable, V any] struct {
	key   K
	value V
}

type Cache[K comparable, V any] struct {
	mu       sync.Mutex
	capacity int
	items    map[K]*list.Element
	order    *list.List
}

func New[K comparable, V any](capacity int) (*Cache[K, V], error) {
	if capacity <= 0 {
		return nil, fmt.Errorf("LRU capacity must be positive")
	}
	return &Cache[K, V]{capacity: capacity, items: make(map[K]*list.Element, capacity), order: list.New()}, nil
}

func (c *Cache[K, V]) Get(key K) (V, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	element, ok := c.items[key]
	if !ok {
		var zero V
		return zero, false
	}
	c.order.MoveToFront(element)
	return element.Value.(entry[K, V]).value, true
}

func (c *Cache[K, V]) Add(key K, value V) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if element, ok := c.items[key]; ok {
		element.Value = entry[K, V]{key: key, value: value}
		c.order.MoveToFront(element)
		return
	}
	element := c.order.PushFront(entry[K, V]{key: key, value: value})
	c.items[key] = element
	if c.order.Len() <= c.capacity {
		return
	}
	evicted := c.order.Back()
	if evicted == nil {
		return
	}
	c.order.Remove(evicted)
	delete(c.items, evicted.Value.(entry[K, V]).key)
}
