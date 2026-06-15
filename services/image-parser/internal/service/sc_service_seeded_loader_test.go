package service

import (
	"bytes"
	"context"
	"image"
	"image/color"
	"image/png"
	"testing"

	imageparserv1 "image-parser/gen/go/imageparser/v1"
	imageloader "image-parser/internal/image_loader"
)

type seededServiceImageLoader struct {
	image []byte
}

func (l seededServiceImageLoader) GetImageBytes(ctx context.Context, keys []imageloader.ImageKey) []imageloader.ImageBytes {
	results := make([]imageloader.ImageBytes, len(keys))
	for i, key := range keys {
		results[i] = imageloader.ImageBytes{
			Key:         key,
			Data:        l.image,
			ContentType: "image/png",
		}
	}
	return results
}

func (l seededServiceImageLoader) WarmInspection(context.Context, imageloader.InspectionKey, []string, string) (int, error) {
	return 0, nil
}

func TestScImageServiceSeededLoaderReturnsPatchPNG(t *testing.T) {
	svc := NewScImageService(seededServiceImageLoader{
		image: seedServicePNG(t, color.Gray{Y: 128}),
	})

	resp, err := svc.GetScImage(context.Background(), &imageparserv1.GetScImageRequest{
		InspectionTime: "2026-05-26T08:00:00+00:00",
		WaferKey:       1,
		DefectId:       "456",
		ImageType:      "patch_defective",
	})
	if err != nil {
		t.Fatalf("GetScImage returned error: %v", err)
	}
	if resp.ContentType != "image/png" {
		t.Fatalf("ContentType = %q, want image/png", resp.ContentType)
	}
	if _, format, err := image.Decode(bytes.NewReader(resp.ImageData)); err != nil {
		t.Fatalf("seeded image did not decode: %v", err)
	} else if format != "png" {
		t.Fatalf("format = %q, want png", format)
	}
}

func seedServicePNG(t *testing.T, fill color.Gray) []byte {
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
