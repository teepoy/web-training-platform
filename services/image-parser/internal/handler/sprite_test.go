package handler

import (
	"bytes"
	"image"
	"image/color"
	"image/png"
	"testing"
)

func generateTestPNG(c color.Color, w, h int) []byte {
	img := image.NewRGBA(image.Rect(0, 0, w, h))
	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			img.Set(x, y, c)
		}
	}
	var buf bytes.Buffer
	_ = png.Encode(&buf, img)
	return buf.Bytes()
}

func TestCreateSpriteFromResized_Single(t *testing.T) {
	raw := generateTestPNG(color.RGBA{255, 0, 0, 255}, 32, 32)
	resized, err := resizeSquarePNG(raw, 64)
	if err != nil {
		t.Fatalf("resize: %v", err)
	}

	result, err := createSpriteFromResized([][]byte{resized}, 64)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	img, _, err := image.Decode(bytes.NewReader(result))
	if err != nil {
		t.Fatalf("decode output: %v", err)
	}

	bounds := img.Bounds()
	if bounds.Dx() != 64 {
		t.Errorf("width = %d, want 64", bounds.Dx())
	}
	if bounds.Dy() != 64 {
		t.Errorf("height = %d, want 64", bounds.Dy())
	}

	got := color.RGBAModel.Convert(img.At(63, 63)).(color.RGBA)
	if got != (color.RGBA{255, 0, 0, 255}) {
		t.Errorf("bottom-right pixel = %#v, want solid red", got)
	}
}

func TestCreateSpriteFromResized_Multi(t *testing.T) {
	pngs := make([][]byte, 0, 3)
	for _, raw := range [][]byte{
		generateTestPNG(color.RGBA{255, 0, 0, 255}, 32, 32),
		generateTestPNG(color.RGBA{0, 255, 0, 255}, 16, 16),
		generateTestPNG(color.RGBA{0, 0, 255, 255}, 64, 64),
	} {
		resized, err := resizeSquarePNG(raw, 48)
		if err != nil {
			t.Fatalf("resize: %v", err)
		}
		pngs = append(pngs, resized)
	}

	result, err := createSpriteFromResized(pngs, 48)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	img, _, err := image.Decode(bytes.NewReader(result))
	if err != nil {
		t.Fatalf("decode output: %v", err)
	}

	bounds := img.Bounds()
	if bounds.Dx() != 48*3 {
		t.Errorf("width = %d, want %d", bounds.Dx(), 48*3)
	}
	if bounds.Dy() != 48 {
		t.Errorf("height = %d, want %d", bounds.Dy(), 48)
	}
}

func TestCreateSpriteFromResized_Empty(t *testing.T) {
	result, err := createSpriteFromResized([][]byte{}, 64)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != nil {
		t.Errorf("expected nil for empty input")
	}
}

func TestBlankSquarePNG_IsVisibleMissingImagePlaceholder(t *testing.T) {
	result, err := blankSquarePNG(64)
	if err != nil {
		t.Fatalf("blank square: %v", err)
	}

	img, _, err := image.Decode(bytes.NewReader(result))
	if err != nil {
		t.Fatalf("decode output: %v", err)
	}
	if img.Bounds() != image.Rect(0, 0, 64, 64) {
		t.Fatalf("bounds = %v, want 64x64", img.Bounds())
	}

	background := color.RGBAModel.Convert(img.At(8, 16)).(color.RGBA)
	center := color.RGBAModel.Convert(img.At(32, 32)).(color.RGBA)
	if background == (color.RGBA{0, 0, 0, 255}) {
		t.Fatalf("background stayed opaque black: %#v", background)
	}
	if center == background {
		t.Fatalf(
			"placeholder marker is not visible: center=%#v background=%#v",
			center,
			background,
		)
	}
}
