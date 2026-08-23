package sqliteinspectionimages_test

import (
	"bytes"
	"context"
	"image"
	"os"
	"path/filepath"
	"testing"
	"time"

	"image-parser/internal/artifactcache"
	"image-parser/internal/equipment"
	"image-parser/internal/equipment/sqliteinspectionimages"
	"image-parser/internal/imagestream"
)

type sqliteInspectionSource struct {
	database  []byte
	revision  string
	downloads int
}

func (s *sqliteInspectionSource) Describe(context.Context, equipment.Inspection) (sqliteinspectionimages.Artifact, error) {
	return sqliteinspectionimages.Artifact{SourceIdentity: "fixtures/inspection-images.sqlite", Revision: s.revision}, nil
}

func (s *sqliteInspectionSource) Download(_ context.Context, _ sqliteinspectionimages.Artifact, destination string) error {
	s.downloads++
	return os.WriteFile(destination, s.database, 0o600)
}

func TestEntryProfilesAndResolvesMultipleReferenceDifferenceImages(t *testing.T) {
	fixture, err := os.ReadFile(filepath.Join("testdata", "multi-reference-difference-12bit.sqlite"))
	if err != nil {
		t.Fatal(err)
	}
	source := &sqliteInspectionSource{database: fixture, revision: "mtime:fixture-1"}
	cache, err := artifactcache.New(filepath.Join(t.TempDir(), "display"), artifactcache.Options{
		TTL: time.Hour, CleanupInterval: time.Hour, MaxBytes: 1 << 30,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(cache.Close)
	factory, err := sqliteinspectionimages.NewFactory(source, 2)
	if err != nil {
		t.Fatal(err)
	}
	inspection := equipment.Inspection{
		InspectionTime: "2026-08-23T00:00:00Z", WaferKey: 9, EquipmentID: "EQ-SQLITE-12BIT",
	}

	profile, err := factory.Profile(context.Background(), equipment.ProfileParams{Inspection: inspection, Cache: cache})
	if err != nil {
		t.Fatal(err)
	}
	if len(profile.Patches) != 6 {
		t.Fatalf("patch count = %d, want 6: %#v", len(profile.Patches), profile.Patches)
	}
	want := []struct {
		imageType string
		imageID   *int
		bitDepth  int
		zMin      uint16
		zMax      uint16
	}{
		{imageType: "Defective", imageID: nil, bitDepth: 12, zMin: 100, zMax: 3500},
		{imageType: "Reference", imageID: intPtr(0), bitDepth: 12, zMin: 200, zMax: 3000},
		{imageType: "Reference", imageID: intPtr(1), bitDepth: 12, zMin: 300, zMax: 3200},
		{imageType: "Difference", imageID: intPtr(0), bitDepth: 12, zMin: 10, zMax: 1000},
		{imageType: "Difference", imageID: intPtr(1), bitDepth: 12, zMin: 20, zMax: 2000},
		{imageType: "Mask", imageID: intPtr(0), bitDepth: 8, zMin: 0, zMax: 1},
	}
	for index, expected := range want {
		got := profile.Patches[index]
		if got.ImageType != expected.imageType || !equalOptionalInt(got.ImageID, expected.imageID) ||
			got.BitDepth != expected.bitDepth || got.ZMin != expected.zMin || got.ZMax != expected.zMax {
			t.Fatalf("patch[%d] = %#v, want %#v", index, got, expected)
		}
	}

	opened, err := factory.Open(context.Background(), equipment.OpenParams{
		UseCase: imagestream.UseCaseDisplay, Inspection: inspection, Cache: cache,
		Roles: []string{"patch_defective", "patch_reference:0", "patch_reference:1", "patch_difference:0", "patch_difference:1", "patch_mask:0"},
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = opened.Close() })
	results, err := opened.Resolve(context.Background(), []imagestream.SampleRequest{{Sequence: 1, SampleID: "sample-42", DefectID: "42"}})
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 1 || len(results[0].Images) != 6 {
		t.Fatalf("results = %#v", results)
	}
	for index, result := range results[0].Images {
		if result.Err != nil {
			t.Fatalf("image[%d] error: %v", index, result.Err)
		}
		if result.ContentType != "image/png" {
			t.Fatalf("image[%d] content type = %q", index, result.ContentType)
		}
		if _, _, err := image.Decode(bytes.NewReader(result.Data)); err != nil {
			t.Fatalf("image[%d] is not a PNG: %v", index, err)
		}
	}
	if source.downloads != 1 {
		t.Fatalf("downloads = %d, want shared artifact cache download", source.downloads)
	}
	if _, err := factory.Profile(context.Background(), equipment.ProfileParams{Inspection: inspection, Cache: cache}); err != nil {
		t.Fatal(err)
	}
	if source.downloads != 1 {
		t.Fatalf("cached profile downloaded artifact again: %d", source.downloads)
	}
}

func intPtr(value int) *int { return &value }

func equalOptionalInt(left, right *int) bool {
	if left == nil || right == nil {
		return left == right
	}
	return *left == *right
}
