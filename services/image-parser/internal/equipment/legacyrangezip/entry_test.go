package legacyrangezip_test

import (
	"archive/zip"
	"bytes"
	"context"
	"image"
	"image/color"
	"image/png"
	"os"
	"path/filepath"
	"testing"
	"time"

	scv1 "image-parser/gen/go/sc/v1"
	"image-parser/internal/artifactcache"
	"image-parser/internal/equipment"
	"image-parser/internal/equipment/legacyrangezip"
	"image-parser/internal/imagestream"
)

type catalog struct{}

func (catalog) GetInspectionPatchZips(context.Context, string, string, string, string, string) (*scv1.GetInspectionPatchZipsResponse, error) {
	return &scv1.GetInspectionPatchZipsResponse{Zips: []*scv1.ZipRef{{S3Bucket: "patches", S3Key: "inspection/000001-000500.zip"}}}, nil
}

type objects struct {
	archive   []byte
	downloads int
}

func (o *objects) DescribePatchObject(context.Context, string, string) (legacyrangezip.ObjectRevision, error) {
	return legacyrangezip.ObjectRevision{Revision: "etag-1", Size: int64(len(o.archive))}, nil
}

func (o *objects) DownloadPatchObject(_ context.Context, _, _, destination string) error {
	o.downloads++
	return os.WriteFile(destination, o.archive, 0o600)
}

func TestEntryDownloadsRangeArchiveOnceAndParsesOrderedSampleRoles(t *testing.T) {
	cache, err := artifactcache.New(filepath.Join(t.TempDir(), "prediction"), artifactcache.Options{
		TTL: time.Hour, CleanupInterval: time.Hour, MaxBytes: 1 << 30,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(cache.Close)
	store := &objects{archive: makeArchive(t, map[string]string{
		"000001_PatchDefective.png": "defective-1",
		"000001_PatchReference.png": "reference-1",
		"000002_PatchDefective.png": "defective-2",
		"000002_PatchReference.png": "reference-2",
	})}
	factory, err := legacyrangezip.NewFactory(catalog{}, store, 8)
	if err != nil {
		t.Fatal(err)
	}
	params := equipment.OpenParams{
		UseCase: imagestream.UseCasePrediction,
		Inspection: equipment.Inspection{
			InspectionTime: "2026-08-21T00:00:00Z", WaferKey: 7, EquipmentID: "EQP01",
			LotID: "LOT", WaferID: "W01", Device: "DEVICE", LayerID: "LAYER",
		},
		Roles: []string{"patch_defective", "patch_template"}, Cache: cache,
	}
	opened, err := factory.Open(context.Background(), params)
	if err != nil {
		t.Fatal(err)
	}
	results, err := opened.Resolve(context.Background(), []imagestream.SampleRequest{
		{Sequence: 1, SampleID: "sample-1", DefectID: "1"},
		{Sequence: 2, SampleID: "sample-2", DefectID: "2"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 2 || len(results[0].Images) != 2 {
		t.Fatalf("results = %#v", results)
	}
	if got := string(results[0].Images[0].Data); got != "defective-1" {
		t.Fatalf("first image = %q", got)
	}
	if got := string(results[1].Images[1].Data); got != "reference-2" {
		t.Fatalf("last image = %q", got)
	}
	if store.downloads != 1 {
		t.Fatalf("downloads = %d", store.downloads)
	}

	second, err := factory.Open(context.Background(), params)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := second.Resolve(context.Background(), []imagestream.SampleRequest{{Sequence: 3, SampleID: "sample-1", DefectID: "1"}}); err != nil {
		t.Fatal(err)
	}
	if store.downloads != 1 {
		t.Fatalf("cache was not reused; downloads = %d", store.downloads)
	}
	removed, err := cache.Cleanup(time.Now().Add(2 * time.Hour))
	if err != nil {
		t.Fatal(err)
	}
	if removed != 1 {
		t.Fatalf("removed = %d, want 1 after ZIP parser released its artifact lease", removed)
	}
}

func TestEntryProfilesMultiplePatchInstancesAndNativeGrayRange(t *testing.T) {
	cache, err := artifactcache.New(filepath.Join(t.TempDir(), "display"), artifactcache.Options{
		TTL: time.Hour, CleanupInterval: time.Hour, MaxBytes: 1 << 30,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(cache.Close)
	store := &objects{archive: makeBinaryArchive(t, map[string][]byte{
		"000001_PatchDefective.png":   gray12PNG(t, 100, 3500),
		"000001_PatchReference0.png":  gray12PNG(t, 200, 3000),
		"000001_PatchReference1.png":  gray12PNG(t, 300, 3200),
		"000001_PatchDifference0.png": gray12PNG(t, 10, 1000),
		"000001_PatchDifference1.png": gray12PNG(t, 20, 2000),
		"000001_PatchMask0.png":       gray8PNG(t, 0, 1),
	})}
	factory, err := legacyrangezip.NewFactory(catalog{}, store, 8)
	if err != nil {
		t.Fatal(err)
	}
	profile, err := factory.Profile(context.Background(), equipment.ProfileParams{
		Inspection: equipment.Inspection{
			InspectionTime: "2026-08-21T00:00:00Z", WaferKey: 7, EquipmentID: "EQP01",
			LotID: "LOT", WaferID: "W01", Device: "DEVICE", LayerID: "LAYER",
		},
		Cache: cache,
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(profile.Patches) != 6 {
		t.Fatalf("profile = %#v", profile)
	}
	wantTypes := []string{"Defective", "Reference", "Reference", "Difference", "Difference", "Mask"}
	wantIDs := []*int{nil, intPointer(0), intPointer(1), intPointer(0), intPointer(1), intPointer(0)}
	for index, patch := range profile.Patches {
		if patch.ImageType != wantTypes[index] || !sameOptionalInt(patch.ImageID, wantIDs[index]) {
			t.Fatalf("patch[%d] = %#v", index, patch)
		}
		if index < 5 && patch.BitDepth != 12 {
			t.Fatalf("patch[%d] bit depth = %d", index, patch.BitDepth)
		}
	}
	if profile.Patches[0].ZMin != 100 || profile.Patches[0].ZMax != 3500 {
		t.Fatalf("defective range = %#v", profile.Patches[0])
	}
	if profile.Patches[5].BitDepth != 8 || profile.Patches[5].ZMin != 0 || profile.Patches[5].ZMax != 1 {
		t.Fatalf("mask profile = %#v", profile.Patches[5])
	}
	opened, err := factory.Open(context.Background(), equipment.OpenParams{
		UseCase: imagestream.UseCaseDisplay,
		Inspection: equipment.Inspection{
			InspectionTime: "2026-08-21T00:00:00Z", WaferKey: 7, EquipmentID: "EQP01",
			LotID: "LOT", WaferID: "W01", Device: "DEVICE", LayerID: "LAYER",
		},
		Roles: []string{"patch_reference:0", "patch_reference:1", "patch_difference:0", "patch_difference:1", "patch_mask:0"},
		Cache: cache,
	})
	if err != nil {
		t.Fatal(err)
	}
	resolved, err := opened.Resolve(context.Background(), []imagestream.SampleRequest{{Sequence: 1, SampleID: "sample-1", DefectID: "1"}})
	if err != nil {
		t.Fatal(err)
	}
	if err := opened.Close(); err != nil {
		t.Fatal(err)
	}
	if len(resolved) != 1 || len(resolved[0].Images) != 5 {
		t.Fatalf("resolved = %#v", resolved)
	}
	for index, result := range resolved[0].Images {
		if result.Err != nil {
			t.Fatalf("resolved image %d: %v", index, result.Err)
		}
	}
	if store.downloads != 1 {
		t.Fatalf("downloads = %d", store.downloads)
	}
	if _, err := factory.Profile(context.Background(), equipment.ProfileParams{
		Inspection: equipment.Inspection{
			InspectionTime: "2026-08-21T00:00:00Z", WaferKey: 7, EquipmentID: "EQP01",
			LotID: "LOT", WaferID: "W01", Device: "DEVICE", LayerID: "LAYER",
		},
		Cache: cache,
	}); err != nil {
		t.Fatal(err)
	}
	if store.downloads != 1 {
		t.Fatalf("cached profile redownloaded archive: %d", store.downloads)
	}
}

func TestEntryProfilesEightAndSixteenBitDefectiveImages(t *testing.T) {
	tests := []struct {
		name     string
		image    func(*testing.T) []byte
		bitDepth int
		maximum  uint16
	}{
		{name: "8-bit", image: func(t *testing.T) []byte { return gray8PNG(t, 0, 255) }, bitDepth: 8, maximum: 255},
		{name: "16-bit", image: func(t *testing.T) []byte { return gray16PNG(t, 0, 65535) }, bitDepth: 16, maximum: 65535},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			cache, err := artifactcache.New(filepath.Join(t.TempDir(), "display"), artifactcache.Options{
				TTL: time.Hour, CleanupInterval: time.Hour, MaxBytes: 1 << 30,
			})
			if err != nil {
				t.Fatal(err)
			}
			t.Cleanup(cache.Close)
			store := &objects{archive: makeBinaryArchive(t, map[string][]byte{
				"000001_PatchDefective.png": test.image(t),
			})}
			factory, err := legacyrangezip.NewFactory(catalog{}, store, 8)
			if err != nil {
				t.Fatal(err)
			}
			profile, err := factory.Profile(context.Background(), equipment.ProfileParams{
				Inspection: equipment.Inspection{
					InspectionTime: "2026-08-21T00:00:00Z", WaferKey: 7, EquipmentID: "EQP01",
					LotID: "LOT", WaferID: "W01", Device: "DEVICE", LayerID: "LAYER",
				},
				Cache: cache,
			})
			if err != nil {
				t.Fatal(err)
			}
			if len(profile.Patches) != 1 || profile.Patches[0].BitDepth != test.bitDepth ||
				profile.Patches[0].ZMin != 0 || profile.Patches[0].ZMax != test.maximum {
				t.Fatalf("profile = %#v", profile)
			}
		})
	}
}

func makeArchive(t *testing.T, members map[string]string) []byte {
	t.Helper()
	var buffer bytes.Buffer
	writer := zip.NewWriter(&buffer)
	for name, value := range members {
		member, err := writer.Create(name)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := member.Write([]byte(value)); err != nil {
			t.Fatal(err)
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	return buffer.Bytes()
}

func makeBinaryArchive(t *testing.T, members map[string][]byte) []byte {
	t.Helper()
	var buffer bytes.Buffer
	writer := zip.NewWriter(&buffer)
	for name, value := range members {
		member, err := writer.Create(name)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := member.Write(value); err != nil {
			t.Fatal(err)
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	return buffer.Bytes()
}

func gray12PNG(t *testing.T, minimum, maximum uint16) []byte {
	t.Helper()
	gray := image.NewGray16(image.Rect(0, 0, 2, 1))
	gray.SetGray16(0, 0, color.Gray16{Y: minimum})
	gray.SetGray16(1, 0, color.Gray16{Y: maximum})
	var buffer bytes.Buffer
	if err := png.Encode(&buffer, gray); err != nil {
		t.Fatal(err)
	}
	return buffer.Bytes()
}

func gray16PNG(t *testing.T, minimum, maximum uint16) []byte {
	t.Helper()
	gray := image.NewGray16(image.Rect(0, 0, 2, 1))
	gray.SetGray16(0, 0, color.Gray16{Y: minimum})
	gray.SetGray16(1, 0, color.Gray16{Y: maximum})
	var buffer bytes.Buffer
	if err := png.Encode(&buffer, gray); err != nil {
		t.Fatal(err)
	}
	return buffer.Bytes()
}

func gray8PNG(t *testing.T, minimum, maximum uint8) []byte {
	t.Helper()
	gray := image.NewGray(image.Rect(0, 0, 2, 1))
	gray.SetGray(0, 0, color.Gray{Y: minimum})
	gray.SetGray(1, 0, color.Gray{Y: maximum})
	var buffer bytes.Buffer
	if err := png.Encode(&buffer, gray); err != nil {
		t.Fatal(err)
	}
	return buffer.Bytes()
}

func intPointer(value int) *int { return &value }

func sameOptionalInt(left, right *int) bool {
	if left == nil || right == nil {
		return left == right
	}
	return *left == *right
}
