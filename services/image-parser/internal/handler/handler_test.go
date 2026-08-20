package handler

import (
	"context"
	"testing"

	"image-parser/internal/display"
)

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
