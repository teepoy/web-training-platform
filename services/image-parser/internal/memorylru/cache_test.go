package memorylru_test

import (
	"testing"

	"image-parser/internal/memorylru"
)

func TestCacheEvictsLeastRecentlyUsedEntry(t *testing.T) {
	cache, err := memorylru.New[string, int](2)
	if err != nil {
		t.Fatal(err)
	}
	cache.Add("a", 1)
	cache.Add("b", 2)
	if _, ok := cache.Get("a"); !ok {
		t.Fatal("expected a")
	}
	cache.Add("c", 3)
	if _, ok := cache.Get("b"); ok {
		t.Fatal("least recently used entry was retained")
	}
	if value, ok := cache.Get("a"); !ok || value != 1 {
		t.Fatalf("a = %d, %v", value, ok)
	}
}

func TestCacheRequiresPositiveCapacity(t *testing.T) {
	if _, err := memorylru.New[string, int](0); err == nil {
		t.Fatal("expected capacity error")
	}
}
