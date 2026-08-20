package artifactcache_test

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"image-parser/internal/artifactcache"
	"image-parser/internal/artifactcache/entrylock"
)

func TestManagerPublishesOneArtifactForConcurrentCacheMisses(t *testing.T) {
	manager := newManager(t)
	ref := artifactcache.Ref{EntryID: "legacy", SourceIdentity: "patches/1.zip", Revision: "etag-1", Kind: artifactcache.KindFile}
	started := make(chan struct{})
	release := make(chan struct{})
	var calls atomic.Int32
	download := func(ctx context.Context, destination string) error {
		if calls.Add(1) == 1 {
			close(started)
		}
		select {
		case <-release:
		case <-ctx.Done():
			return ctx.Err()
		}
		return os.WriteFile(destination, []byte("archive"), 0o600)
	}

	paths := make([]string, 2)
	errorsByCall := make([]error, 2)
	var wait sync.WaitGroup
	for index := range paths {
		wait.Add(1)
		go func(index int) {
			defer wait.Done()
			paths[index], errorsByCall[index] = manager.GetOrDownload(context.Background(), ref, download)
		}(index)
	}
	<-started
	close(release)
	wait.Wait()

	if errorsByCall[0] != nil || errorsByCall[1] != nil {
		t.Fatalf("errors = %#v", errorsByCall)
	}
	if calls.Load() != 1 {
		t.Fatalf("download calls = %d, want 1", calls.Load())
	}
	if paths[0] != paths[1] {
		t.Fatalf("paths differ: %#v", paths)
	}
	data, err := os.ReadFile(paths[0])
	if err != nil {
		t.Fatal(err)
	}
	if string(data) != "archive" {
		t.Fatalf("artifact = %q", data)
	}
}

func TestManagerDoesNotPublishFailedDownloadAndSeparatesSourceRevisions(t *testing.T) {
	manager := newManager(t)
	base := artifactcache.Ref{EntryID: "legacy", SourceIdentity: "patches/1.zip", Revision: "etag-1", Kind: artifactcache.KindFile}
	_, err := manager.GetOrDownload(context.Background(), base, func(context.Context, string) error {
		return errors.New("download failed")
	})
	if err == nil {
		t.Fatal("expected download error")
	}
	entries, err := os.ReadDir(filepath.Join(manager.Root(), "objects"))
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 0 {
		t.Fatalf("failed download left cache entries: %#v", entries)
	}

	pathOne, err := manager.GetOrDownload(context.Background(), base, writeArtifact("one"))
	if err != nil {
		t.Fatal(err)
	}
	updated := base
	updated.Revision = "etag-2"
	pathTwo, err := manager.GetOrDownload(context.Background(), updated, writeArtifact("two"))
	if err != nil {
		t.Fatal(err)
	}
	if pathOne == pathTwo {
		t.Fatal("different source revisions reused one cache path")
	}
}

func TestManagerPublishesDirectoryArtifactWithoutFollowingSymlinks(t *testing.T) {
	manager := newManager(t)
	ref := artifactcache.Ref{EntryID: "folder-entry", SourceIdentity: "inspection/folder", Revision: "generation-7", Kind: artifactcache.KindDirectory}
	path, err := manager.GetOrDownload(context.Background(), ref, func(_ context.Context, destination string) error {
		if err := os.MkdirAll(filepath.Join(destination, "nested"), 0o750); err != nil {
			return err
		}
		return os.WriteFile(filepath.Join(destination, "nested", "image.png"), []byte("image"), 0o600)
	})
	if err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(filepath.Join(path, "nested", "image.png"))
	if err != nil {
		t.Fatal(err)
	}
	if string(data) != "image" {
		t.Fatalf("directory artifact data = %q", data)
	}

	updated := ref
	updated.Revision = "generation-8"
	_, err = manager.GetOrDownload(context.Background(), updated, func(_ context.Context, destination string) error {
		if err := os.MkdirAll(destination, 0o750); err != nil {
			return err
		}
		return os.Symlink("/tmp/outside", filepath.Join(destination, "escape"))
	})
	if err == nil {
		t.Fatal("directory artifact containing a symlink was accepted")
	}
}

func TestCleanupDefersEvictionWhileArtifactTargetIsLocked(t *testing.T) {
	manager := newManager(t)
	ref := artifactcache.Ref{EntryID: "legacy", SourceIdentity: "patches/locked.zip", Revision: "etag-1", Kind: artifactcache.KindFile}
	path, err := manager.GetOrDownload(context.Background(), ref, writeArtifact("locked"))
	if err != nil {
		t.Fatal(err)
	}
	old := time.Now().Add(-2 * time.Hour)
	if err := os.Chtimes(path, old, old); err != nil {
		t.Fatal(err)
	}
	relative, err := filepath.Rel(manager.Root(), path)
	if err != nil {
		t.Fatal(err)
	}
	lock, err := entrylock.Acquire(context.Background(), manager.Root(), relative)
	if err != nil {
		t.Fatal(err)
	}
	removed, err := manager.Cleanup(time.Now().Add(2 * time.Hour))
	if err != nil {
		t.Fatal(err)
	}
	if removed != 0 {
		t.Fatalf("removed = %d, want 0 while target is locked", removed)
	}
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("locked artifact was removed: %v", err)
	}
	if err := lock.Release(); err != nil {
		t.Fatal(err)
	}
	removed, err = manager.Cleanup(time.Now().Add(2 * time.Hour))
	if err != nil {
		t.Fatal(err)
	}
	if removed != 1 {
		t.Fatalf("removed = %d, want 1 after release", removed)
	}
}

func newManager(t *testing.T) *artifactcache.Manager {
	t.Helper()
	manager, err := artifactcache.New(filepath.Join(t.TempDir(), "cache"), artifactcache.Options{
		TTL:             time.Hour,
		CleanupInterval: time.Hour,
		MaxBytes:        1 << 30,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(manager.Close)
	return manager
}

func writeArtifact(value string) artifactcache.DownloadFunc {
	return func(_ context.Context, destination string) error {
		return os.WriteFile(destination, []byte(value), 0o600)
	}
}
