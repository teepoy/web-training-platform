package handler

import (
	"bytes"
	"context"
	"image"
	"image/color"
	"image/png"
	"runtime"
	"testing"

	"image-parser/internal/display"
)

var benchmarkSpriteSink []byte

type benchmarkImageReader struct {
	data []byte
}

func (r benchmarkImageReader) GetImageBytes(_ context.Context, keys []display.ImageKey) []display.ImageBytes {
	results := make([]display.ImageBytes, len(keys))
	for index, key := range keys {
		results[index] = display.ImageBytes{
			Key:         key,
			Data:        r.data,
			ContentType: "image/png",
		}
	}
	return results
}

func BenchmarkResizeSquarePNG128To64(b *testing.B) {
	raw := benchmarkPatternPNG(b, 128)
	b.SetBytes(int64(len(raw)))
	b.ReportAllocs()
	b.ResetTimer()
	for range b.N {
		resized, err := resizeSquarePNG(raw, 64)
		if err != nil {
			b.Fatal(err)
		}
		benchmarkSpriteSink = resized
	}
}

func BenchmarkResizeSquarePNGGray16Viridis128To64(b *testing.B) {
	img := image.NewGray16(image.Rect(0, 0, 128, 128))
	for y := range 128 {
		for x := range 128 {
			img.SetGray16(x, y, color.Gray16{Y: uint16((x*257 + y*509) % 65536)})
		}
	}
	var encoded bytes.Buffer
	if err := png.Encode(&encoded, img); err != nil {
		b.Fatal(err)
	}
	raw := encoded.Bytes()
	mapping := GrayMapping{Mode: GrayMappingModeGlobal, LUT: GrayLUTViridis, ZMin: 0.05, ZMax: 0.95}
	b.SetBytes(int64(len(raw)))
	b.ReportAllocs()
	b.ResetTimer()
	for range b.N {
		resized, err := resizeSquarePNGWithGrayMapping(raw, 64, mapping)
		if err != nil {
			b.Fatal(err)
		}
		benchmarkSpriteSink = resized
	}
}

func BenchmarkCreateSpriteThreeCells64(b *testing.B) {
	raw := benchmarkPatternPNG(b, 64)
	cells := [][]byte{raw, raw, raw}
	b.SetBytes(int64(len(raw) * len(cells)))
	b.ReportAllocs()
	b.ResetTimer()
	for range b.N {
		sprite, err := createSpriteFromResized(cells, 64)
		if err != nil {
			b.Fatal(err)
		}
		benchmarkSpriteSink = sprite
	}
}

func BenchmarkGetSCSpriteThreePatchCells64(b *testing.B) {
	raw := benchmarkPatternPNG(b, 128)
	routes, request := benchmarkSpriteFixture(raw)
	b.SetBytes(int64(len(raw) * len(request.Images)))
	b.ReportAllocs()
	b.ResetTimer()
	for range b.N {
		response, err := routes.GetSCSprite(context.Background(), request)
		if err != nil {
			b.Fatal(err)
		}
		benchmarkSpriteSink = response.Data
	}
}

func BenchmarkGetSCSpriteThreePatchCells64Parallel(b *testing.B) {
	raw := benchmarkPatternPNG(b, 128)
	routes, request := benchmarkSpriteFixture(raw)
	b.SetBytes(int64(len(raw) * len(request.Images)))
	b.ReportAllocs()
	b.ResetTimer()
	b.RunParallel(func(pb *testing.PB) {
		var result []byte
		for pb.Next() {
			response, err := routes.GetSCSprite(context.Background(), request)
			if err != nil {
				b.Error(err)
				return
			}
			result = response.Data
		}
		runtime.KeepAlive(result)
	})
}

func benchmarkSpriteFixture(raw []byte) (*scRoutes, SCSpriteRequest) {
	return NewSCRoutes(benchmarkImageReader{data: raw}), SCSpriteRequest{
		Inspection: display.InspectionKey{
			InspectionTime: "2026-08-21 00:00:00.000000",
			WaferKey:       1,
		},
		DefectID: "1",
		CellSize: 64,
		Images: []SCSpriteImage{
			{Kind: display.ImageKindPatch, ImageType: "Defective"},
			{Kind: display.ImageKindPatch, ImageType: "Reference"},
			{Kind: display.ImageKindPatch, ImageType: "Difference"},
		},
	}
}

func benchmarkPatternPNG(tb testing.TB, size int) []byte {
	tb.Helper()
	img := image.NewNRGBA(image.Rect(0, 0, size, size))
	for y := range size {
		for x := range size {
			img.SetNRGBA(x, y, color.NRGBA{
				R: uint8((x*17 + y*3) % 256),
				G: uint8((x*5 + y*11) % 256),
				B: uint8((x*7 + y*13) % 256),
				A: 255,
			})
		}
	}
	var output bytes.Buffer
	if err := png.Encode(&output, img); err != nil {
		tb.Fatal(err)
	}
	return output.Bytes()
}
