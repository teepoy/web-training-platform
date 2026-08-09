package handler

import (
	"bytes"
	"image"
	"image/color"
	"image/draw"
	"image/png"

	"github.com/h2non/bimg"
)

func resizeSquarePNG(raw []byte, size int) ([]byte, error) {
	opts := bimg.Options{
		Width:  size,
		Height: size,
		Force:  true,
		Type:   bimg.PNG,
	}

	metadata, err := bimg.Metadata(raw)
	if err != nil {
		return nil, err
	}
	if metadata.Size.Width < size || metadata.Size.Height < size {
		opts.Interpolator = bimg.Nearest
	}

	return bimg.Resize(raw, opts)
}

func createSpriteFromResized(pngs [][]byte, size int) ([]byte, error) {
	count := len(pngs)
	if count == 0 {
		return nil, nil
	}

	canvas := image.NewRGBA(image.Rect(0, 0, size*count, size))

	for i, raw := range pngs {
		img, _, err := image.Decode(bytes.NewReader(raw))
		if err != nil {
			return nil, err
		}

		draw.Draw(canvas,
			image.Rect(i*size, 0, (i+1)*size, size),
			img,
			image.Point{},
			draw.Src,
		)
	}

	var buf bytes.Buffer
	if err := png.Encode(&buf, canvas); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

func blankSquarePNG(size int) ([]byte, error) {
	canvas := image.NewRGBA(image.Rect(0, 0, size, size))
	background := color.RGBA{R: 48, G: 52, B: 60, A: 255}
	alternate := color.RGBA{R: 68, G: 74, B: 84, A: 255}
	marker := color.RGBA{R: 142, G: 151, B: 166, A: 255}
	tileSize := max(4, size/4)
	for y := 0; y < size; y++ {
		for x := 0; x < size; x++ {
			pixel := background
			if (x/tileSize+y/tileSize)%2 == 1 {
				pixel = alternate
			}
			canvas.SetRGBA(x, y, pixel)
		}
	}
	markerWidth := max(1, size/32)
	for offset := -markerWidth; offset <= markerWidth; offset++ {
		for position := 0; position < size; position++ {
			if x := position + offset; x >= 0 && x < size {
				canvas.SetRGBA(x, position, marker)
				canvas.SetRGBA(size-1-x, position, marker)
			}
		}
	}
	var buf bytes.Buffer
	if err := png.Encode(&buf, canvas); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}
