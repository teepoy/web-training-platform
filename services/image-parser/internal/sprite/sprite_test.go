package sprite

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

func TestCreateSprite_Single(t *testing.T) {
	pngs := [][]byte{
		generateTestPNG(color.RGBA{255, 0, 0, 255}, 32, 32),
	}

	result, err := CreateSprite(pngs, 64)
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
}

func TestCreateSprite_Multi(t *testing.T) {
	pngs := [][]byte{
		generateTestPNG(color.RGBA{255, 0, 0, 255}, 32, 32),
		generateTestPNG(color.RGBA{0, 255, 0, 255}, 16, 16),
		generateTestPNG(color.RGBA{0, 0, 255, 255}, 64, 64),
	}

	result, err := CreateSprite(pngs, 48)
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

func TestCreateSprite_Empty(t *testing.T) {
	result, err := CreateSprite([][]byte{}, 64)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != nil {
		t.Errorf("expected nil for empty input")
	}
}

func TestParseSize(t *testing.T) {
	tests := []struct {
		raw  string
		want int
	}{
		{"", 64},
		{"128", 128},
		{"5000", 4096},
		{"0", 0},
		{"-1", 0},
	}

	for _, tc := range tests {
		got, err := ParseSize(tc.raw)
		if tc.want == 0 && err == nil {
			t.Errorf("ParseSize(%q) expected error", tc.raw)
			continue
		}
		if got != tc.want {
			t.Errorf("ParseSize(%q) = %d, want %d", tc.raw, got, tc.want)
		}
	}
}
