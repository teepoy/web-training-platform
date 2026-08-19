package sourcecache

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"image-parser/internal/filesource"
)

func TestCleanupAppliesTTLAndSizeOnlyToSharedCache(t *testing.T) {
	root := t.TempDir()
	oldPath := filepath.Join(root, "old.bin")
	newPath := filepath.Join(root, "new.bin")
	if err := os.WriteFile(oldPath, []byte("old"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(newPath, []byte("newer"), 0o600); err != nil {
		t.Fatal(err)
	}
	now := time.Now()
	if err := os.Chtimes(oldPath, now.Add(-2*time.Hour), now.Add(-2*time.Hour)); err != nil {
		t.Fatal(err)
	}
	if err := os.Chtimes(newPath, now, now); err != nil {
		t.Fatal(err)
	}
	source, err := filesource.Open(root, filesource.KindDirectory, filesource.OwnershipSharedCache)
	if err != nil {
		t.Fatal(err)
	}
	janitor, err := New(source, time.Hour, 0)
	if err != nil {
		t.Fatal(err)
	}
	result, err := janitor.Cleanup(now)
	if err != nil {
		t.Fatal(err)
	}
	if result.Expired != 1 || result.RemainingFiles != 1 {
		t.Fatalf("unexpected cleanup result: %#v", result)
	}
	if _, err := os.Stat(oldPath); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("expired file still exists: %v", err)
	}
	if _, err := os.Stat(newPath); err != nil {
		t.Fatalf("fresh file was removed: %v", err)
	}
}

func TestCleanupRejectsBorrowedAndJobOwnedSources(t *testing.T) {
	for _, ownership := range []filesource.Ownership{
		filesource.OwnershipBorrowed,
		filesource.OwnershipJobOwned,
	} {
		source, err := filesource.Open(t.TempDir(), filesource.KindDirectory, ownership)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := New(source, time.Hour, 0); err == nil {
			t.Fatalf("ownership %q unexpectedly accepted", ownership)
		}
	}
}

func TestCleanupEvictsLeastRecentlyUsedFilesToSizeLimit(t *testing.T) {
	root := t.TempDir()
	now := time.Now()
	paths := []string{
		filepath.Join(root, "old.bin"),
		filepath.Join(root, "middle.bin"),
		filepath.Join(root, "new.bin"),
	}
	for index, path := range paths {
		if err := os.WriteFile(path, []byte("four"), 0o600); err != nil {
			t.Fatal(err)
		}
		usedAt := now.Add(time.Duration(index-3) * time.Minute)
		if err := os.Chtimes(path, usedAt, usedAt); err != nil {
			t.Fatal(err)
		}
	}
	source, err := filesource.Open(root, filesource.KindDirectory, filesource.OwnershipSharedCache)
	if err != nil {
		t.Fatal(err)
	}
	janitor, err := New(source, time.Hour, 8)
	if err != nil {
		t.Fatal(err)
	}
	result, err := janitor.Cleanup(now)
	if err != nil {
		t.Fatal(err)
	}
	if result.Evicted != 1 || result.RemainingFiles != 2 || result.RemainingBytes != 8 {
		t.Fatalf("unexpected cleanup result: %#v", result)
	}
	if _, err := os.Stat(paths[0]); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("least recently used file still exists: %v", err)
	}
	for _, path := range paths[1:] {
		if _, err := os.Stat(path); err != nil {
			t.Fatalf("newer file was removed: %v", err)
		}
	}
}

func TestCleanupDoesNotRemoveInProgressStageFiles(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, ".stage-active")
	if err := os.WriteFile(path, []byte("staging"), 0o600); err != nil {
		t.Fatal(err)
	}
	now := time.Now()
	if err := os.Chtimes(path, now.Add(-2*time.Hour), now.Add(-2*time.Hour)); err != nil {
		t.Fatal(err)
	}
	source, err := filesource.Open(root, filesource.KindDirectory, filesource.OwnershipSharedCache)
	if err != nil {
		t.Fatal(err)
	}
	janitor, err := New(source, time.Hour, 1)
	if err != nil {
		t.Fatal(err)
	}
	result, err := janitor.Cleanup(now)
	if err != nil {
		t.Fatal(err)
	}
	if result.Expired != 0 || result.Evicted != 0 {
		t.Fatalf("in-progress stage file was counted: %#v", result)
	}
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("in-progress stage file was removed: %v", err)
	}
}
