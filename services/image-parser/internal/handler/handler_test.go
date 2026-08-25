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

type mappedSpriteByRoleLoader map[string][]byte

type recordingSpriteBatchLoader struct {
	data  []byte
	calls [][]display.ImageKey
}

func (l *recordingSpriteBatchLoader) GetImageBytes(_ context.Context, keys []display.ImageKey) []display.ImageBytes {
	l.calls = append(l.calls, append([]display.ImageKey(nil), keys...))
	results := make([]display.ImageBytes, len(keys))
	for index, key := range keys {
		results[index] = display.ImageBytes{Key: key, Data: l.data, ContentType: "image/png"}
	}
	return results
}

func (l mappedSpriteByRoleLoader) GetImageBytes(_ context.Context, keys []display.ImageKey) []display.ImageBytes {
	results := make([]display.ImageBytes, len(keys))
	for index, key := range keys {
		results[index] = display.ImageBytes{Key: key, Data: l[key.ImageType], ContentType: "image/png"}
	}
	return results
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
		GrayMappings: PatchGrayMappings{DefectiveReference: &GrayMapping{Mode: GrayMappingModeGlobal, LUT: GrayLUTViridis, ZMin: 0, ZMax: 1}},
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

func TestSCSpriteResolvesAllCellsInOneReaderBatch(t *testing.T) {
	patch := image.NewGray(image.Rect(0, 0, 2, 2))
	loader := &recordingSpriteBatchLoader{data: encodeTestPNG(t, patch)}
	routes := NewSCRoutes(loader)

	_, err := routes.GetSCSprite(context.Background(), SCSpriteRequest{
		Inspection: display.InspectionKey{InspectionTime: "2026-08-25T00:00:00Z", WaferKey: 1},
		DefectID:   "1",
		CellSize:   4,
		Images: []SCSpriteImage{
			{Kind: display.ImageKindPatch, ImageType: "Defective"},
			{Kind: display.ImageKindPatch, ImageType: "Reference"},
			{Kind: display.ImageKindReview, ReviewImageID: 1},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(loader.calls) != 1 {
		t.Fatalf("reader calls = %d, want one batched read", len(loader.calls))
	}
	if len(loader.calls[0]) != 3 {
		t.Fatalf("batched keys = %d, want 3", len(loader.calls[0]))
	}
}

func TestSCSpriteAvoidsPerPixelIntermediateImageAllocations(t *testing.T) {
	patch := image.NewNRGBA(image.Rect(0, 0, 128, 128))
	for y := range 128 {
		for x := range 128 {
			patch.SetNRGBA(x, y, color.NRGBA{
				R: uint8((x*17 + y*3) % 256),
				G: uint8((x*5 + y*11) % 256),
				B: uint8((x*7 + y*13) % 256),
				A: 255,
			})
		}
	}
	routes := NewSCRoutes(mappedSpriteLoader{patch: encodeTestPNG(t, patch)})
	request := SCSpriteRequest{
		Inspection: display.InspectionKey{InspectionTime: "2026-08-25T00:00:00Z", WaferKey: 1},
		DefectID:   "1",
		CellSize:   64,
		Images: []SCSpriteImage{
			{Kind: display.ImageKindPatch, ImageType: "Defective"},
			{Kind: display.ImageKindPatch, ImageType: "Reference"},
			{Kind: display.ImageKindPatch, ImageType: "Difference"},
		},
	}
	var renderErr error
	allocations := testing.AllocsPerRun(5, func() {
		_, renderErr = routes.GetSCSprite(context.Background(), request)
	})
	if renderErr != nil {
		t.Fatal(renderErr)
	}
	if allocations >= 1000 {
		t.Fatalf("sprite allocations = %.0f, want fewer than 1000", allocations)
	}
}

func TestSCSpriteUsesDefectiveReferenceAndDifferenceMappings(t *testing.T) {
	patch := image.NewGray16(image.Rect(0, 0, 1, 1))
	patch.SetGray16(0, 0, color.Gray16{Y: 32768})
	routes := NewSCRoutes(mappedSpriteLoader{patch: encodeTestPNG(t, patch)})

	response, err := routes.GetSCSprite(context.Background(), SCSpriteRequest{
		Inspection: display.InspectionKey{InspectionTime: "2026-08-20T00:00:00Z", WaferKey: 1},
		DefectID:   "1",
		CellSize:   1,
		Images: []SCSpriteImage{
			{Kind: display.ImageKindPatch, ImageType: "Defective"},
			{Kind: display.ImageKindPatch, ImageType: "Reference"},
			{Kind: display.ImageKindPatch, ImageType: "Difference"},
		},
		GrayMappings: PatchGrayMappings{
			DefectiveReference: &GrayMapping{Mode: GrayMappingModeGlobal, LUT: GrayLUTViridis, ZMin: 0, ZMax: 1},
			Difference:         &GrayMapping{Mode: GrayMappingModeGlobal, LUT: GrayLUTInferno, ZMin: 0, ZMax: 1},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	decoded, _, err := image.Decode(bytes.NewReader(response.Data))
	if err != nil {
		t.Fatal(err)
	}
	defective := color.NRGBAModel.Convert(decoded.At(0, 0)).(color.NRGBA)
	reference := color.NRGBAModel.Convert(decoded.At(1, 0)).(color.NRGBA)
	difference := color.NRGBAModel.Convert(decoded.At(2, 0)).(color.NRGBA)
	if defective != reference {
		t.Fatalf("defective = %#v, reference = %#v; want shared mapping", defective, reference)
	}
	if difference == defective {
		t.Fatalf("difference = %#v, want independent mapping from %#v", difference, defective)
	}
}

func TestSCSpritePatchUpscaleReplicatesPixelsWithoutInterpolation(t *testing.T) {
	tests := []struct {
		name     string
		patch    image.Image
		mappings PatchGrayMappings
	}{
		{
			name: "original color",
			patch: func() image.Image {
				value := image.NewNRGBA(image.Rect(0, 0, 2, 2))
				value.SetNRGBA(0, 0, color.NRGBA{R: 255, A: 255})
				value.SetNRGBA(1, 0, color.NRGBA{G: 255, A: 255})
				value.SetNRGBA(0, 1, color.NRGBA{B: 255, A: 255})
				value.SetNRGBA(1, 1, color.NRGBA{R: 255, G: 255, B: 255, A: 255})
				return value
			}(),
		},
		{
			name: "grayscale LUT",
			patch: func() image.Image {
				value := image.NewGray(image.Rect(0, 0, 2, 2))
				value.SetGray(0, 0, color.Gray{Y: 0})
				value.SetGray(1, 0, color.Gray{Y: 64})
				value.SetGray(0, 1, color.Gray{Y: 128})
				value.SetGray(1, 1, color.Gray{Y: 255})
				return value
			}(),
			mappings: PatchGrayMappings{DefectiveReference: &GrayMapping{
				Mode: GrayMappingModeGlobal, LUT: GrayLUTGrayscale, ZMin: 0, ZMax: 1, BitDepth: 8,
			}},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			routes := NewSCRoutes(mappedSpriteLoader{patch: encodeTestPNG(t, test.patch)})
			response, err := routes.GetSCSprite(context.Background(), SCSpriteRequest{
				Inspection:   display.InspectionKey{InspectionTime: "2026-08-24T00:00:00Z", WaferKey: 1},
				DefectID:     "1",
				CellSize:     4,
				Images:       []SCSpriteImage{{Kind: display.ImageKindPatch, ImageType: "Defective"}},
				GrayMappings: test.mappings,
			})
			if err != nil {
				t.Fatal(err)
			}
			decoded, _, err := image.Decode(bytes.NewReader(response.Data))
			if err != nil {
				t.Fatal(err)
			}
			for y := 0; y < 4; y++ {
				for x := 0; x < 4; x++ {
					want := color.NRGBAModel.Convert(test.patch.At(x/2, y/2)).(color.NRGBA)
					got := color.NRGBAModel.Convert(decoded.At(x, y)).(color.NRGBA)
					if got != want {
						t.Fatalf("pixel (%d,%d) = %#v, want replicated source pixel %#v", x, y, got, want)
					}
				}
			}
		})
	}
}

func TestSCSpriteAdaptiveMappingSharesDefectiveReferenceWindowPerDefect(t *testing.T) {
	gray16 := func(left, right uint16) []byte {
		patch := image.NewGray16(image.Rect(0, 0, 2, 1))
		patch.SetGray16(0, 0, color.Gray16{Y: left})
		patch.SetGray16(1, 0, color.Gray16{Y: right})
		return encodeTestPNG(t, patch)
	}
	routes := NewSCRoutes(mappedSpriteByRoleLoader{
		"Defective":  gray16(100, 200),
		"Reference":  gray16(300, 400),
		"Difference": gray16(1000, 2000),
	})

	response, err := routes.GetSCSprite(context.Background(), SCSpriteRequest{
		Inspection: display.InspectionKey{InspectionTime: "2026-08-24T00:00:00Z", WaferKey: 1},
		DefectID:   "1",
		CellSize:   2,
		Images: []SCSpriteImage{
			{Kind: display.ImageKindPatch, ImageType: "Defective"},
			{Kind: display.ImageKindPatch, ImageType: "Reference"},
			{Kind: display.ImageKindPatch, ImageType: "Difference"},
		},
		GrayMappings: PatchGrayMappings{
			DefectiveReference: &GrayMapping{Mode: GrayMappingModeAdaptive, LUT: GrayLUTGrayscale, BitDepth: 12},
			Difference:         &GrayMapping{Mode: GrayMappingModeAdaptive, LUT: GrayLUTGrayscale, BitDepth: 12},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	decoded, _, err := image.Decode(bytes.NewReader(response.Data))
	if err != nil {
		t.Fatal(err)
	}
	grayAt := func(x int) uint8 { return color.GrayModel.Convert(decoded.At(x, 0)).(color.Gray).Y }
	if got := grayAt(1); got < 84 || got > 86 {
		t.Fatalf("defective max = %d, want shared T/R normalization near 85", got)
	}
	if got := grayAt(2); got < 169 || got > 171 {
		t.Fatalf("reference min = %d, want shared T/R normalization near 170", got)
	}
	if got := grayAt(4); got != 0 {
		t.Fatalf("difference min = %d, want independently normalized 0", got)
	}
	if got := grayAt(5); got != 255 {
		t.Fatalf("difference max = %d, want independently normalized 255", got)
	}
}

func TestSCSpriteUsesExplicitTwelveBitNativeDomain(t *testing.T) {
	patch := image.NewGray16(image.Rect(0, 0, 1, 1))
	patch.SetGray16(0, 0, color.Gray16{Y: 2048})
	routes := NewSCRoutes(mappedSpriteLoader{patch: encodeTestPNG(t, patch)})

	response, err := routes.GetSCSprite(context.Background(), SCSpriteRequest{
		Inspection: display.InspectionKey{InspectionTime: "2026-08-23T00:00:00Z", WaferKey: 1},
		DefectID:   "1",
		CellSize:   1,
		Images:     []SCSpriteImage{{Kind: display.ImageKindPatch, ImageType: "Reference:0"}},
		GrayMappings: PatchGrayMappings{DefectiveReference: &GrayMapping{
			Mode: GrayMappingModeGlobal, LUT: GrayLUTGrayscale, ZMin: 0, ZMax: 1, BitDepth: 12,
		}},
	})
	if err != nil {
		t.Fatal(err)
	}
	decoded, _, err := image.Decode(bytes.NewReader(response.Data))
	if err != nil {
		t.Fatal(err)
	}
	gray := color.GrayModel.Convert(decoded.At(0, 0)).(color.Gray).Y
	if gray < 127 || gray > 129 {
		t.Fatalf("mapped 12-bit midpoint = %d, want approximately 128", gray)
	}
}

func TestSCSpriteUsesEightAndSixteenBitNativeDomains(t *testing.T) {
	tests := []struct {
		name     string
		patch    image.Image
		bitDepth int
	}{
		{name: "8-bit", patch: gray8Midpoint(), bitDepth: 8},
		{name: "16-bit", patch: gray16Midpoint(), bitDepth: 16},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			routes := NewSCRoutes(mappedSpriteLoader{patch: encodeTestPNG(t, test.patch)})
			response, err := routes.GetSCSprite(context.Background(), SCSpriteRequest{
				Inspection: display.InspectionKey{InspectionTime: "2026-08-23T00:00:00Z", WaferKey: 1},
				DefectID:   "1",
				CellSize:   1,
				Images:     []SCSpriteImage{{Kind: display.ImageKindPatch, ImageType: "Defective"}},
				GrayMappings: PatchGrayMappings{DefectiveReference: &GrayMapping{
					Mode: GrayMappingModeGlobal, LUT: GrayLUTGrayscale, ZMin: 0, ZMax: 1, BitDepth: test.bitDepth,
				}},
			})
			if err != nil {
				t.Fatal(err)
			}
			decoded, _, err := image.Decode(bytes.NewReader(response.Data))
			if err != nil {
				t.Fatal(err)
			}
			gray := color.GrayModel.Convert(decoded.At(0, 0)).(color.Gray).Y
			if gray < 127 || gray > 129 {
				t.Fatalf("mapped %s midpoint = %d, want approximately 128", test.name, gray)
			}
		})
	}
}

func gray8Midpoint() image.Image {
	patch := image.NewGray(image.Rect(0, 0, 1, 1))
	patch.SetGray(0, 0, color.Gray{Y: 128})
	return patch
}

func gray16Midpoint() image.Image {
	patch := image.NewGray16(image.Rect(0, 0, 1, 1))
	patch.SetGray16(0, 0, color.Gray16{Y: 32768})
	return patch
}
