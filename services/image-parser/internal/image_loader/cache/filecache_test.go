package cache

import (
	"crypto/sha256"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestGetRefreshesProgramLastUsedTime(t *testing.T) {
	cache := newTestCache(t, 0, time.Hour)
	if err := cache.Set("bucket/key", []byte("zip")); err != nil {
		t.Fatal(err)
	}

	path := cache.pathForKey("bucket/key")
	old := time.Now().Add(-30 * time.Minute)
	if err := os.Chtimes(path, old, old); err != nil {
		t.Fatal(err)
	}
	beforeRead := time.Now()

	data, ok, err := cache.Get("bucket/key")
	if err != nil {
		t.Fatal(err)
	}
	if !ok || string(data) != "zip" {
		t.Fatalf("Get() = %q, %v; want zip, true", data, ok)
	}
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if info.ModTime().Before(beforeRead) {
		t.Fatalf("last-used time = %s; want at least %s", info.ModTime(), beforeRead)
	}
}

func TestCleanupDeletesEntriesExpiredSinceLastUse(t *testing.T) {
	cache := newTestCache(t, 0, time.Hour)
	if err := cache.Set("expired", []byte("old")); err != nil {
		t.Fatal(err)
	}
	if err := cache.Set("active", []byte("new")); err != nil {
		t.Fatal(err)
	}
	expiredPath := cache.pathForKey("expired")
	old := time.Now().Add(-2 * time.Hour)
	if err := os.Chtimes(expiredPath, old, old); err != nil {
		t.Fatal(err)
	}

	result, err := cache.Cleanup()
	if err != nil {
		t.Fatal(err)
	}
	if result.ExpiredFiles != 1 {
		t.Fatalf("ExpiredFiles = %d; want 1", result.ExpiredFiles)
	}
	if _, err := os.Stat(expiredPath); !os.IsNotExist(err) {
		t.Fatalf("expired entry still exists: %v", err)
	}
	if _, ok, err := cache.Get("active"); err != nil || !ok {
		t.Fatalf("active entry unavailable: ok=%v err=%v", ok, err)
	}
}

func TestPeriodicCleanupRunsFullScan(t *testing.T) {
	cache := newTestCache(t, 0, 10*time.Millisecond)
	if err := cache.Set("expired", []byte("old")); err != nil {
		t.Fatal(err)
	}
	path := cache.pathForKey("expired")
	old := time.Now().Add(-2 * time.Hour)
	if err := os.Chtimes(path, old, old); err != nil {
		t.Fatal(err)
	}

	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		if _, err := os.Stat(path); os.IsNotExist(err) {
			return
		}
		time.Sleep(5 * time.Millisecond)
	}
	t.Fatal("periodic cleanup did not remove expired entry")
}

func TestNewRunsInitialFullScan(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, strings.Repeat("a", sha256.Size*2)+cacheFileSuffix)
	if err := os.WriteFile(path, []byte("old"), 0o600); err != nil {
		t.Fatal(err)
	}
	old := time.Now().Add(-2 * time.Hour)
	if err := os.Chtimes(path, old, old); err != nil {
		t.Fatal(err)
	}

	cache, err := NewLocalFileCache(LocalFileCacheConfig{
		Dir:             dir,
		TTL:             time.Hour,
		CleanupInterval: time.Hour,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_ = cache.Close()
	})
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatalf("initial full scan did not remove expired entry: %v", err)
	}
}

func TestCleanupIgnoresFilesItDoesNotOwn(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "notes.cache")
	if err := os.WriteFile(path, []byte("keep"), 0o600); err != nil {
		t.Fatal(err)
	}
	old := time.Now().Add(-2 * time.Hour)
	if err := os.Chtimes(path, old, old); err != nil {
		t.Fatal(err)
	}

	cache, err := NewLocalFileCache(LocalFileCacheConfig{
		Dir:             dir,
		TTL:             time.Hour,
		CleanupInterval: time.Hour,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_ = cache.Close()
	})
	if data, err := os.ReadFile(path); err != nil || string(data) != "keep" {
		t.Fatalf("unowned file changed: data=%q err=%v", data, err)
	}
}

func TestMaxBytesEvictsLeastRecentlyUsedFile(t *testing.T) {
	cache := newTestCache(t, 8, time.Hour)
	if err := cache.Set("oldest", []byte("1234")); err != nil {
		t.Fatal(err)
	}
	if err := cache.Set("newest", []byte("5678")); err != nil {
		t.Fatal(err)
	}
	old := time.Now().Add(-30 * time.Minute)
	if err := os.Chtimes(cache.pathForKey("oldest"), old, old); err != nil {
		t.Fatal(err)
	}
	if err := cache.Set("incoming", []byte("abcd")); err != nil {
		t.Fatal(err)
	}

	if _, ok, err := cache.Get("oldest"); err != nil || ok {
		t.Fatalf("oldest entry should be evicted: ok=%v err=%v", ok, err)
	}
	for _, key := range []string{"newest", "incoming"} {
		if _, ok, err := cache.Get(key); err != nil || !ok {
			t.Fatalf("%s entry unavailable: ok=%v err=%v", key, ok, err)
		}
	}
}

func TestZeroMaxBytesLeavesCapacityUnlimited(t *testing.T) {
	cache := newTestCache(t, 0, time.Hour)
	for _, key := range []string{"one", "two", "three"} {
		if err := cache.Set(key, make([]byte, 1024)); err != nil {
			t.Fatal(err)
		}
	}
	result, err := cache.Cleanup()
	if err != nil {
		t.Fatal(err)
	}
	if result.EntryCount != 3 || result.UsedBytes != 3*1024 {
		t.Fatalf("Cleanup() = %+v; want 3 entries and 3072 bytes", result)
	}
}

func TestNewRejectsInvalidConfiguration(t *testing.T) {
	tests := []LocalFileCacheConfig{
		{TTL: time.Minute, CleanupInterval: time.Minute},
		{Dir: t.TempDir(), CleanupInterval: time.Minute},
		{Dir: t.TempDir(), TTL: time.Minute},
		{Dir: t.TempDir(), TTL: time.Minute, CleanupInterval: time.Minute, MaxBytes: -1},
	}
	for _, config := range tests {
		if cache, err := NewLocalFileCache(config); err == nil {
			_ = cache.Close()
			t.Fatalf("New(%+v) unexpectedly succeeded", config)
		}
	}
}

func newTestCache(t *testing.T, maxBytes int64, cleanupInterval time.Duration) *LocalFileCache {
	t.Helper()
	cache, err := NewLocalFileCache(LocalFileCacheConfig{
		Dir:             t.TempDir(),
		TTL:             time.Hour,
		CleanupInterval: cleanupInterval,
		MaxBytes:        maxBytes,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := cache.Close(); err != nil {
			t.Errorf("Close() error = %v", err)
		}
	})
	return cache
}
