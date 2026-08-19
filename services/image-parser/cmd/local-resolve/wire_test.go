package main

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	imageloader "image-parser/internal/image_loader"
	"image-parser/internal/sourceformat/directfiles"
)

func TestLocalResolverUsesBorrowedFilesystemWithoutRemoteDependencies(t *testing.T) {
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "defective.png"), []byte("image"), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("IMAGE_SOURCE_ROOT", root)
	t.Setenv("IMAGE_SOURCE_FORMAT", directfiles.FormatID)
	t.Setenv("IMAGE_SOURCE_KIND", "directory")

	images, closeImages, err := initializeImageLoader()
	if err != nil {
		t.Fatal(err)
	}
	closeImages()
	results := images.GetImageBytes(context.Background(), []imageloader.ImageKey{{
		Kind:         imageloader.ImageKindPatch,
		SourceFormat: directfiles.FormatID,
		ImageType:    "Defective",
		RolePaths:    map[string]string{"Defective": "defective.png"},
	}})
	if len(results) != 1 || results[0].Err != nil || string(results[0].Data) != "image" {
		t.Fatalf("unexpected results: %#v", results)
	}
	if _, err := os.Stat(root); err != nil {
		t.Fatalf("borrowed source was removed: %v", err)
	}
}
