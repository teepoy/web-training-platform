package handler

import (
	"bytes"
	"context"
	"image"
	"image/color"
	"testing"

	"image-parser/internal/display"
)

type mappedSpriteLoader struct {
	patch  []byte
	review []byte
}

func (l mappedSpriteLoader) GetImageBytes(_ context.Context, keys []display.ImageKey) []display.ImageBytes {
	results := make([]display.ImageBytes, len(keys))
	for index, key := range keys {
		data := l.patch
		if key.Kind == display.ImageKindReview {
			data = l.review
		}
		results[index] = display.ImageBytes{Key: key, Data: data, ContentType: "image/png"}
	}
	return results
}

type recordingCompatibilityLoader struct {
	keys []display.ImageKey
}

func (l *recordingCompatibilityLoader) GetImageBytes(_ context.Context, keys []display.ImageKey) []display.ImageBytes {
	l.keys = append(l.keys, keys...)
	results := make([]display.ImageBytes, len(keys))
	for index, key := range keys {
		results[index] = display.ImageBytes{Key: key, Data: []byte("image"), ContentType: "image/png"}
	}
	return results
}

func TestSCCompatibilityRouteDelegatesPatchResolution(t *testing.T) {
	loader := &recordingCompatibilityLoader{}
	routes := NewSCRoutes(loader)

	if _, err := routes.GetSCImage(context.Background(), SCImageRequest{
		Inspection: display.InspectionKey{InspectionTime: "2026-08-20T00:00:00Z", WaferKey: 1},
		DefectID:   "1",
		ImageType:  "patch_defective",
	}); err != nil {
		t.Fatal(err)
	}
	if len(loader.keys) != 1 {
		t.Fatalf("received %d image keys, want 1", len(loader.keys))
	}
	if got := loader.keys[0].ImageType; got != "Defective" {
		t.Fatalf("image role = %q, want Defective", got)
	}
}

func TestSCSpriteGrayMappingTransformsPatchButNotReviewCells(t *testing.T) {
	patch := image.NewGray16(image.Rect(0, 0, 1, 1))
	patch.SetGray16(0, 0, color.Gray16{Y: 32768})
	review := image.NewNRGBA(image.Rect(0, 0, 1, 1))
	review.SetNRGBA(0, 0, color.NRGBA{R: 220, G: 30, B: 10, A: 255})
	routes := NewSCRoutes(mappedSpriteLoader{
		patch:  encodeTestPNG(t, patch),
		review: encodeTestPNG(t, review),
	})

	response, err := routes.GetSCSprite(context.Background(), SCSpriteRequest{
		Inspection: display.InspectionKey{InspectionTime: "2026-08-20T00:00:00Z", WaferKey: 1},
		DefectID:   "1",
		CellSize:   1,
		Images: []SCSpriteImage{
			{Kind: display.ImageKindPatch, ImageType: "Defective"},
			{Kind: display.ImageKindReview, ReviewImageID: 1},
		},
		GrayMapping: &GrayMapping{LUT: GrayLUTViridis, ZMin: 0, ZMax: 1},
	})
	if err != nil {
		t.Fatal(err)
	}
	decoded, _, err := image.Decode(bytes.NewReader(response.Data))
	if err != nil {
		t.Fatal(err)
	}
	mappedPatch := color.NRGBAModel.Convert(decoded.At(0, 0)).(color.NRGBA)
	if mappedPatch.R == mappedPatch.G && mappedPatch.G == mappedPatch.B {
		t.Fatalf("patch cell stayed grayscale: %#v", mappedPatch)
	}
	gotReview := color.NRGBAModel.Convert(decoded.At(1, 0)).(color.NRGBA)
	if gotReview != (color.NRGBA{R: 220, G: 30, B: 10, A: 255}) {
		t.Fatalf("review cell was transformed: %#v", gotReview)
	}
}
