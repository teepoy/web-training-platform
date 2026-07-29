package cache

import (
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestZipCacheUsesLocalFileHelperBeforeLoader(t *testing.T) {
	local := newTestCache(t, 0, time.Hour)
	first, err := New(1, time.Minute, WithLocalFileCache(local))
	if err != nil {
		t.Fatal(err)
	}
	if err := first.Set("bucket/key", []byte("disk")); err != nil {
		t.Fatal(err)
	}

	second, err := New(1, time.Minute, WithLocalFileCache(local))
	if err != nil {
		t.Fatal(err)
	}
	var loaderCalls atomic.Int32
	data, err := second.GetOrLoad("bucket/key", func() ([]byte, error) {
		loaderCalls.Add(1)
		return []byte("remote"), nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if string(data) != "disk" {
		t.Fatalf("GetOrLoad() = %q; want disk", data)
	}
	if loaderCalls.Load() != 0 {
		t.Fatalf("loader calls = %d; want 0", loaderCalls.Load())
	}
	if memoryData, ok := second.Get("bucket/key"); !ok || string(memoryData) != "disk" {
		t.Fatalf("local file hit was not promoted to memory: data=%q ok=%v", memoryData, ok)
	}
}

func TestZipCacheGetOrLoadCoalescesConcurrentLoads(t *testing.T) {
	local := newTestCache(t, 0, time.Hour)
	cache, err := New(1, time.Minute, WithLocalFileCache(local))
	if err != nil {
		t.Fatal(err)
	}
	var calls atomic.Int32
	start := make(chan struct{})
	var wg sync.WaitGroup
	for range 10 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			data, err := cache.GetOrLoad("same", func() ([]byte, error) {
				calls.Add(1)
				time.Sleep(10 * time.Millisecond)
				return []byte("loaded"), nil
			})
			if err != nil {
				t.Errorf("GetOrLoad() error = %v", err)
				return
			}
			if string(data) != "loaded" {
				t.Errorf("GetOrLoad() = %q; want loaded", data)
			}
		}()
	}
	close(start)
	wg.Wait()
	if calls.Load() != 1 {
		t.Fatalf("loader calls = %d; want 1", calls.Load())
	}
}
