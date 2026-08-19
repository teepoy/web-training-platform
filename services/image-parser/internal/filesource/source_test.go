package filesource

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestDirectorySourceReadsOnlyInsideRoot(t *testing.T) {
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "patch.png"), []byte("patch"), 0o600); err != nil {
		t.Fatal(err)
	}
	outside := filepath.Join(t.TempDir(), "secret.png")
	if err := os.WriteFile(outside, []byte("secret"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, filepath.Join(root, "escape.png")); err != nil {
		t.Fatal(err)
	}

	source, err := Open(root, KindDirectory, OwnershipBorrowed)
	if err != nil {
		t.Fatal(err)
	}
	data, err := source.ReadFile("patch.png")
	if err != nil {
		t.Fatal(err)
	}
	if string(data) != "patch" {
		t.Fatalf("unexpected data %q", data)
	}
	for _, candidate := range []string{"../secret.png", "escape.png", outside} {
		if _, err := source.ReadFile(candidate); err == nil {
			t.Fatalf("expected %q to be rejected", candidate)
		}
	}
}

func TestFileSourceReadsTheConfiguredFileOnly(t *testing.T) {
	path := filepath.Join(t.TempDir(), "image.tiff")
	if err := os.WriteFile(path, []byte("image"), 0o600); err != nil {
		t.Fatal(err)
	}
	source, err := Open(path, KindFile, OwnershipBorrowed)
	if err != nil {
		t.Fatal(err)
	}
	data, err := source.ReadFile("")
	if err != nil {
		t.Fatal(err)
	}
	if string(data) != "image" {
		t.Fatalf("unexpected data %q", data)
	}
	if _, err := source.ReadFile("another.tiff"); err == nil {
		t.Fatal("file source accepted a different path")
	}
}

func TestCleanupOnlyRemovesJobOwnedSource(t *testing.T) {
	for _, ownership := range []Ownership{OwnershipBorrowed, OwnershipSharedCache} {
		root := t.TempDir()
		source, err := Open(root, KindDirectory, ownership)
		if err != nil {
			t.Fatal(err)
		}
		if err := source.Cleanup(); !errors.Is(err, ErrNotJobOwned) {
			t.Fatalf("ownership %q: expected ErrNotJobOwned, got %v", ownership, err)
		}
		if _, err := os.Stat(root); err != nil {
			t.Fatalf("ownership %q was removed: %v", ownership, err)
		}
	}

	parent := t.TempDir()
	root := filepath.Join(parent, "job")
	if err := os.Mkdir(root, 0o700); err != nil {
		t.Fatal(err)
	}
	source, err := Open(root, KindDirectory, OwnershipJobOwned)
	if err != nil {
		t.Fatal(err)
	}
	if err := source.Cleanup(); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(root); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("job-owned root still exists: %v", err)
	}
}

func TestOnlyOwnedOrSharedSourcesCanBeStaged(t *testing.T) {
	borrowed, err := Open(t.TempDir(), KindDirectory, OwnershipBorrowed)
	if err != nil {
		t.Fatal(err)
	}
	if err := borrowed.WriteFile("folder/asset.bin", []byte("asset")); !errors.Is(err, ErrReadOnlySource) {
		t.Fatalf("expected borrowed source to reject staging, got %v", err)
	}

	parent := t.TempDir()
	root := filepath.Join(parent, "job")
	if err := os.Mkdir(root, 0o700); err != nil {
		t.Fatal(err)
	}
	owned, err := Open(root, KindDirectory, OwnershipJobOwned)
	if err != nil {
		t.Fatal(err)
	}
	if err := owned.WriteFile("folder/asset.bin", []byte("asset")); err != nil {
		t.Fatal(err)
	}
	data, err := owned.ReadFile("folder/asset.bin")
	if err != nil || string(data) != "asset" {
		t.Fatalf("unexpected staged file data=%q err=%v", data, err)
	}
}
