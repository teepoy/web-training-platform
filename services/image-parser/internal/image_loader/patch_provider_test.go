package image_loader

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"image-parser/internal/image_loader/cache"
)

func TestFolderPatchArchiveProviderUsesStableFiveHundredDefectLayout(t *testing.T) {
	root := t.TempDir()
	provider, err := NewFolderPatchArchiveProvider(root)
	if err != nil {
		t.Fatal(err)
	}

	for _, tc := range []struct {
		defectID int
		wantName string
	}{
		{defectID: 1, wantName: "000001-000500.zip"},
		{defectID: 500, wantName: "000001-000500.zip"},
		{defectID: 501, wantName: "000501-001000.zip"},
		{defectID: 1000, wantName: "000501-001000.zip"},
	} {
		archives, resolveErr := provider.ResolveArchives(
			context.Background(),
			InspectionKey{InspectionTime: "2026-08-16T10:11:12+08:00", WaferKey: 42},
			[]int{zipIndexForDefect(tc.defectID)},
		)
		if resolveErr != nil {
			t.Fatalf("defect %d: %v", tc.defectID, resolveErr)
		}
		archive := archives[zipIndexForDefect(tc.defectID)]
		if got := filepath.Base(archive.Path); got != tc.wantName {
			t.Fatalf("defect %d archive = %q, want %q", tc.defectID, got, tc.wantName)
		}
		wantSuffix := filepath.Join("20260816_101112", "42", tc.wantName)
		if !strings.HasSuffix(archive.Path, wantSuffix) {
			t.Fatalf("archive path %q does not end in %q", archive.Path, wantSuffix)
		}
	}
}

func TestFolderPatchArchiveProviderRejectsEscapeAndSymlink(t *testing.T) {
	root := t.TempDir()
	outside := t.TempDir()
	if _, err := secureJoinedPath(root, filepath.Join("..", "escape.zip")); err == nil {
		t.Fatal("secureJoinedPath accepted directory traversal")
	}
	if err := os.WriteFile(filepath.Join(outside, "archive.zip"), []byte("zip"), 0o600); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(root, "escape.zip")
	if err := os.Symlink(filepath.Join(outside, "archive.zip"), link); err != nil {
		t.Fatal(err)
	}
	if _, err := secureExistingPath(root, link); err == nil || !strings.Contains(err.Error(), "symlink escapes") {
		t.Fatalf("secureExistingPath error = %v, want symlink escape", err)
	}
}

func TestPatchArchiveRegistryRejectsUnknownProfile(t *testing.T) {
	provider, err := NewFolderPatchArchiveProvider(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	registry, err := NewPatchArchiveProviderRegistry(map[string]PatchArchiveProvider{"folder": provider})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := registry.Get("unknown"); err == nil || !strings.Contains(err.Error(), "unknown image source profile") {
		t.Fatalf("registry.Get error = %v", err)
	}
}

func TestUpstreamAndFolderProfilesResolveIdenticalFixtureBytes(t *testing.T) {
	zipBytes := seedPatchZip(t, 1)
	root := t.TempDir()
	archiveDir := filepath.Join(root, "20260816_020000", "42")
	if err := os.MkdirAll(archiveDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(archiveDir, "000001-000500.zip"), zipBytes, 0o600); err != nil {
		t.Fatal(err)
	}
	folder, err := NewFolderPatchArchiveProvider(root)
	if err != nil {
		t.Fatal(err)
	}
	loader := seededImageLoader{patchZip: zipBytes}
	registry, err := NewPatchArchiveProviderRegistry(map[string]PatchArchiveProvider{
		"upstream": newUpstreamPatchArchiveProvider(seededLoaderUpstream{}, loader),
		"folder":   folder,
	})
	if err != nil {
		t.Fatal(err)
	}
	zipCache, err := cache.New(64, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	resolver := newResolverWithProfiles(
		seededLoaderUpstream{}, loader, registry, "upstream", zipCache, nil,
	)
	key := ImageKey{
		Kind: ImageKindPatch,
		InspectionKey: InspectionKey{
			InspectionTime: "2026-08-16T02:00:00Z",
			WaferKey:       42,
		},
		DefectID:  "1",
		ImageType: "patch_defective",
	}
	upstream, err := resolver.ResolvePatchImageBytes(context.Background(), "upstream", []ImageKey{key})
	if err != nil {
		t.Fatal(err)
	}
	folderResult, err := resolver.ResolvePatchImageBytes(context.Background(), "folder", []ImageKey{key})
	if err != nil {
		t.Fatal(err)
	}
	if upstream[0].Err != nil || folderResult[0].Err != nil {
		t.Fatalf("resolve errors: upstream=%v folder=%v", upstream[0].Err, folderResult[0].Err)
	}
	if !bytes.Equal(upstream[0].Data, folderResult[0].Data) {
		t.Fatal("upstream and folder fixture bytes differ")
	}
}

func TestFolderProfileReturnsStableItemErrorsForMissingBadZipAndRole(t *testing.T) {
	root := t.TempDir()
	provider, err := NewFolderPatchArchiveProvider(root)
	if err != nil {
		t.Fatal(err)
	}
	registry, err := NewPatchArchiveProviderRegistry(map[string]PatchArchiveProvider{"folder": provider})
	if err != nil {
		t.Fatal(err)
	}
	zipCache, err := cache.New(64, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	resolver := newResolverWithProfiles(
		seededLoaderUpstream{}, seededImageLoader{}, registry, "folder", zipCache, nil,
	)
	key := ImageKey{
		Kind: ImageKindPatch,
		InspectionKey: InspectionKey{
			InspectionTime: "2026-08-16T02:00:00Z",
			WaferKey:       42,
		},
		DefectID:  "1",
		ImageType: "patch_defective",
	}
	missing, err := resolver.ResolvePatchImageBytes(context.Background(), "folder", []ImageKey{key})
	if err != nil {
		t.Fatal(err)
	}
	if missing[0].Err == nil || !strings.Contains(missing[0].Err.Error(), "not found") {
		t.Fatalf("missing archive error = %v", missing[0].Err)
	}

	archiveDir := filepath.Join(root, "20260816_020000", "42")
	if err := os.MkdirAll(archiveDir, 0o755); err != nil {
		t.Fatal(err)
	}
	archivePath := filepath.Join(archiveDir, "000001-000500.zip")
	if err := os.WriteFile(archivePath, []byte("not a zip"), 0o600); err != nil {
		t.Fatal(err)
	}
	bad, err := resolver.ResolvePatchImageBytes(context.Background(), "folder", []ImageKey{key})
	if err != nil {
		t.Fatal(err)
	}
	if bad[0].Err == nil {
		t.Fatal("corrupt archive unexpectedly resolved")
	}
	zipCache.Evict("folder\x00" + archivePath)

	if err := os.WriteFile(archivePath, seedPatchZip(t, 2), 0o600); err != nil {
		t.Fatal(err)
	}
	roleMissing, err := resolver.ResolvePatchImageBytes(context.Background(), "folder", []ImageKey{key})
	if err != nil {
		t.Fatal(err)
	}
	if roleMissing[0].Err == nil {
		t.Fatal("missing role unexpectedly resolved")
	}
}
