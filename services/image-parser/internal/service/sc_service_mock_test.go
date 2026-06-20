package service

import (
	"bytes"
	"context"
	"image"
	"testing"

	imageparserv1 "image-parser/gen/go/imageparser/v1"
	"image-parser/internal/resolve"
)

func TestScImageServiceMockSourceReturnsPatchPNG(t *testing.T) {
	svc := NewScImageService(resolve.NewMockImageSource())

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
		t.Fatalf("mock image did not decode: %v", err)
	} else if format != "png" {
		t.Fatalf("format = %q, want png", format)
	}
}
