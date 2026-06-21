package image_loader

import (
	"archive/zip"
	"bytes"
	"context"
	"image"
	"image/color"
	"image/png"
	"testing"
	"time"

	scv1 "image-parser/gen/go/sc/v1"
	"image-parser/internal/image_loader/cache"
)

type seededImageLoader struct {
	patchZip []byte
	review   []byte
}

func (l seededImageLoader) LoadPatchZip(ctx context.Context, bucket, key string) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return l.patchZip, nil
}

func (l seededImageLoader) LoadReviewObject(ctx context.Context, bucket, key string) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return l.review, nil
}

type seededLoaderUpstream struct{}

func (seededLoaderUpstream) GetInspection(context.Context, string, int32) (*scv1.GetInspectionResponse, error) {
	return &scv1.GetInspectionResponse{
		LotId:   "lot",
		WaferId: "wafer",
		Device:  "device",
		LayerId: "layer",
	}, nil
}

func (seededLoaderUpstream) GetInspectionPatchZips(context.Context, string, string, string, string, string) (*scv1.GetInspectionPatchZipsResponse, error) {
	return &scv1.GetInspectionPatchZipsResponse{
		Zips: []*scv1.ZipRef{{S3Bucket: "seeded", S3Key: "patch-0000.zip"}},
	}, nil
}

func (seededLoaderUpstream) GetReviewImageFileSpec(context.Context, string, int32, int32, int32) (*scv1.GetReviewImageFileSpecResponse, error) {
	return &scv1.GetReviewImageFileSpecResponse{ImageFilespec: "s3://seeded/review/1.png"}, nil
}

func TestSeededImageLoaderIsSwappableAtResolverBoundary(t *testing.T) {
	zipCache, err := cache.New(64, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	resolver := newResolver(
		seededLoaderUpstream{},
		seededImageLoader{
			patchZip: seedPatchZip(t, 456),
			review:   seedPNG(t, color.Gray{Y: 180}),
		},
		zipCache,
		nil,
	)

	results := resolver.GetImageBytes(context.Background(), []ImageKey{{
		Kind:          ImageKindPatch,
		InspectionKey: InspectionKey{InspectionTime: "2026-01-01T00:00:00Z", WaferKey: 1},
		DefectID:      "456",
		ImageType:     "Defective",
	}})
	if results[0].Err != nil {
		t.Fatalf("GetImageBytes returned error: %v", results[0].Err)
	}
	if _, format, err := image.Decode(bytes.NewReader(results[0].Data)); err != nil {
		t.Fatalf("seeded patch image did not decode: %v", err)
	} else if format != "png" {
		t.Fatalf("format = %q, want png", format)
	}

	review, err := resolver.getReviewImageBytes(context.Background(), "2026-01-01T00:00:00Z", 1, "456", 1)
	if err != nil {
		t.Fatalf("getReviewImageBytes returned error: %v", err)
	}
	if _, format, err := image.Decode(bytes.NewReader(review)); err != nil {
		t.Fatalf("seeded review image did not decode: %v", err)
	} else if format != "png" {
		t.Fatalf("format = %q, want png", format)
	}
}

func seedPatchZip(t *testing.T, defectID int) []byte {
	t.Helper()
	var buf bytes.Buffer
	zw := zip.NewWriter(&buf)
	for _, entry := range []struct {
		name string
		fill color.Gray
	}{
		{patchImagePrefixMust(defectID, "Reference") + ".png", color.Gray{Y: 96}},
		{patchImagePrefixMust(defectID, "Defective") + ".png", color.Gray{Y: 128}},
		{patchImagePrefixMust(defectID, "Difference") + ".png", color.Gray{Y: 160}},
	} {
		w, err := zw.Create(entry.name)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := w.Write(seedPNG(t, entry.fill)); err != nil {
			t.Fatal(err)
		}
	}
	if err := zw.Close(); err != nil {
		t.Fatal(err)
	}
	return buf.Bytes()
}

func seedPNG(t *testing.T, fill color.Gray) []byte {
	t.Helper()
	img := image.NewGray(image.Rect(0, 0, 8, 8))
	for y := 0; y < 8; y++ {
		for x := 0; x < 8; x++ {
			img.SetGray(x, y, fill)
		}
	}
	var buf bytes.Buffer
	if err := png.Encode(&buf, img); err != nil {
		t.Fatal(err)
	}
	return buf.Bytes()
}

func patchImagePrefixMust(defectID int, imageType string) string {
	prefix, ok := patchImagePrefix(defectID, imageType)
	if !ok {
		panic("invalid test image type")
	}
	return prefix
}
