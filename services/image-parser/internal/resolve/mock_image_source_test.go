package resolve

import (
	"bytes"
	"context"
	"errors"
	"image"
	"testing"
)

type failingImageSource struct{}

func (failingImageSource) ResolveMetadataForWarm(ctx context.Context, inspectionTime string, waferKey int) (string, string, string, string, error) {
	return "", "", "", "", errors.New("boom")
}

func (failingImageSource) ResolvePatchZipsForWarm(ctx context.Context, inspectionTime, lotID, waferID, device, layerID string) ([]CacheZipRef, error) {
	return nil, errors.New("boom")
}

func (failingImageSource) GetMetaAndZips(ctx context.Context, inspectionTime string, waferKey int) (string, string, string, string, []CacheZipRef, error) {
	return "", "", "", "", nil, errors.New("boom")
}

func (failingImageSource) GetPatchImageBytes(ctx context.Context, inspectionTime string, waferKey int, defectIDStr string, imageType string) ([]byte, error) {
	return nil, errors.New("boom")
}

func (failingImageSource) GetPatchImageBytesFromZips(ctx context.Context, zips []CacheZipRef, defectIDStr string, imageType string) ([]byte, error) {
	return nil, errors.New("boom")
}

func (failingImageSource) GetPatchImageBytesBatchFromZips(ctx context.Context, zips []CacheZipRef, lookups []PatchImageLookup) []PatchImageLookupResult {
	results := make([]PatchImageLookupResult, len(lookups))
	for i, lookup := range lookups {
		results[i] = PatchImageLookupResult{
			Index:     lookup.Index,
			DefectID:  lookup.DefectID,
			ImageType: lookup.ImageType,
			Err:       errors.New("boom"),
		}
	}
	return results
}

func (failingImageSource) GetReviewImageBytes(ctx context.Context, inspectionTime string, waferKey int, defectIDStr string, reviewImageID int) ([]byte, error) {
	return nil, errors.New("boom")
}

func (failingImageSource) GetReviewImages(ctx context.Context, inspectionTime string, waferKey int, defectIDStr string) ([]string, error) {
	return nil, errors.New("boom")
}

func (failingImageSource) GetReviewObjectBytes(ctx context.Context, bucket, key string) ([]byte, error) {
	return nil, errors.New("boom")
}

func (failingImageSource) WarmAsync(record, bucket string, keys []string) {}

type emptyZipImageSource struct {
	failingImageSource
}

func (emptyZipImageSource) ResolvePatchZipsForWarm(ctx context.Context, inspectionTime, lotID, waferID, device, layerID string) ([]CacheZipRef, error) {
	return nil, nil
}

func (emptyZipImageSource) GetMetaAndZips(ctx context.Context, inspectionTime string, waferKey int) (string, string, string, string, []CacheZipRef, error) {
	return "lot", "wafer", "device", "layer", nil, nil
}

func TestFallbackImageSourceReturnsMockPatchPNG(t *testing.T) {
	source := NewFallbackImageSource(failingImageSource{})

	data, err := source.GetPatchImageBytes(context.Background(), "2026-01-01T00:00:00Z", 1, "75015", "defective")
	if err != nil {
		t.Fatalf("GetPatchImageBytes returned error: %v", err)
	}
	img, format, err := image.Decode(bytes.NewReader(data))
	if err != nil {
		t.Fatalf("fallback image did not decode: %v", err)
	}
	if format != "png" {
		t.Fatalf("format = %q, want png", format)
	}
	if got := img.Bounds().Dx(); got != fallbackImageSize {
		t.Fatalf("width = %d, want %d", got, fallbackImageSize)
	}
	if got := img.Bounds().Dy(); got != fallbackImageSize {
		t.Fatalf("height = %d, want %d", got, fallbackImageSize)
	}
}

func TestFallbackImageSourceFillsBatchErrors(t *testing.T) {
	source := NewFallbackImageSource(failingImageSource{})

	results := source.GetPatchImageBytesBatchFromZips(
		context.Background(),
		nil,
		[]PatchImageLookup{{Index: 0, DefectID: "1", ImageType: "template"}},
	)
	if len(results) != 1 {
		t.Fatalf("len(results) = %d, want 1", len(results))
	}
	if results[0].Err != nil {
		t.Fatalf("batch result error = %v, want nil", results[0].Err)
	}
	if _, _, err := image.Decode(bytes.NewReader(results[0].Data)); err != nil {
		t.Fatalf("batch fallback image did not decode: %v", err)
	}
}

func TestFallbackImageSourceTreatsEmptyZipListAsMock(t *testing.T) {
	source := NewFallbackImageSource(emptyZipImageSource{})

	lot, wafer, device, layer, zips, err := source.GetMetaAndZips(context.Background(), "2026-01-01T00:00:00Z", 1)
	if err != nil {
		t.Fatalf("GetMetaAndZips returned error: %v", err)
	}
	if lot == "lot" || wafer == "wafer" || device == "device" || layer == "layer" {
		t.Fatalf("expected mock metadata, got lot=%q wafer=%q device=%q layer=%q", lot, wafer, device, layer)
	}
	if len(zips) != 1 {
		t.Fatalf("len(zips) = %d, want 1 mock zip", len(zips))
	}

	warmZips, err := source.ResolvePatchZipsForWarm(context.Background(), "2026-01-01T00:00:00Z", lot, wafer, device, layer)
	if err != nil {
		t.Fatalf("ResolvePatchZipsForWarm returned error: %v", err)
	}
	if len(warmZips) != 1 {
		t.Fatalf("len(warmZips) = %d, want 1 mock zip", len(warmZips))
	}
}
