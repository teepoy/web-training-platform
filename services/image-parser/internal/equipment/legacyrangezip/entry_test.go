package legacyrangezip_test

import (
	"archive/zip"
	"bytes"
	"context"
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
	factory := legacyrangezip.NewFactory(catalog{}, store)
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
