package sprite

import (
	"bytes"
	"fmt"
	"image"
	"image/draw"
	"image/png"
	"strconv"

	"github.com/h2non/bimg"
)

func CreateSprite(pngs [][]byte, size int) ([]byte, error) {
	count := len(pngs)
	if count == 0 {
		return nil, nil
	}

	canvas := image.NewRGBA(image.Rect(0, 0, size*count, size))

	for i, raw := range pngs {
		resized, err := ResizeSquarePNG(raw, size)
		if err != nil {
			return nil, err
		}

		img, _, err := image.Decode(bytes.NewReader(resized))
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

func ResizeSquarePNG(raw []byte, size int) ([]byte, error) {
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

func ParseSize(raw string) (int, error) {
	if raw == "" {
		return 64, nil
	}
	s, err := strconv.Atoi(raw)
	if err != nil {
		return 0, err
	}
	if s < 1 {
		return 0, fmt.Errorf("size must be >= 1")
	}
	if s > 4096 {
		s = 4096
	}
	return s, nil
}

func CreateSpriteFromResized(pngs [][]byte, size int) ([]byte, error) {
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
