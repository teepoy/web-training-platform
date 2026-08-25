package handler

import (
	"bytes"
	"image"
	"image/color"
	"image/draw"
	_ "image/jpeg"
	"image/png"
)

func resizeSquarePNG(raw []byte, size int) ([]byte, error) {
	return resizeSquarePNGWith(raw, size, resizeBilinear)
}

func resizeSquarePNGPixelFill(raw []byte, size int) ([]byte, error) {
	return resizeSquarePNGWith(raw, size, resizeNearest)
}

func resizeSquarePNGWith(raw []byte, size int, resize func(*image.NRGBA, image.Image)) ([]byte, error) {
	source, _, err := image.Decode(bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	if source.Bounds().Dx() == size && source.Bounds().Dy() == size {
		var output bytes.Buffer
		if err := png.Encode(&output, source); err != nil {
			return nil, err
		}
		return output.Bytes(), nil
	}

	target := image.NewNRGBA(image.Rect(0, 0, size, size))
	resize(target, source)
	var output bytes.Buffer
	if err := png.Encode(&output, target); err != nil {
		return nil, err
	}
	return output.Bytes(), nil
}

func resizeNearest(target *image.NRGBA, source image.Image) {
	sourceBounds := source.Bounds()
	sourceWidth := sourceBounds.Dx()
	sourceHeight := sourceBounds.Dy()
	targetWidth := target.Bounds().Dx()
	targetHeight := target.Bounds().Dy()
	for targetY := range targetHeight {
		sourceY := sourceBounds.Min.Y + targetY*sourceHeight/targetHeight
		for targetX := range targetWidth {
			sourceX := sourceBounds.Min.X + targetX*sourceWidth/targetWidth
			target.SetNRGBA(targetX, targetY, color.NRGBAModel.Convert(source.At(sourceX, sourceY)).(color.NRGBA))
		}
	}
}

func resizeBilinear(target *image.NRGBA, source image.Image) {
	sourceBounds := source.Bounds()
	sourceWidth := sourceBounds.Dx()
	sourceHeight := sourceBounds.Dy()
	targetWidth := target.Bounds().Dx()
	targetHeight := target.Bounds().Dy()
	for targetY := range targetHeight {
		sourceY := (float64(targetY)+0.5)*float64(sourceHeight)/float64(targetHeight) - 0.5
		y0, y1, yWeight := interpolationPoints(sourceY, sourceHeight)
		for targetX := range targetWidth {
			sourceX := (float64(targetX)+0.5)*float64(sourceWidth)/float64(targetWidth) - 0.5
			x0, x1, xWeight := interpolationPoints(sourceX, sourceWidth)
			upperLeft := color.NRGBAModel.Convert(source.At(sourceBounds.Min.X+x0, sourceBounds.Min.Y+y0)).(color.NRGBA)
			upperRight := color.NRGBAModel.Convert(source.At(sourceBounds.Min.X+x1, sourceBounds.Min.Y+y0)).(color.NRGBA)
			lowerLeft := color.NRGBAModel.Convert(source.At(sourceBounds.Min.X+x0, sourceBounds.Min.Y+y1)).(color.NRGBA)
			lowerRight := color.NRGBAModel.Convert(source.At(sourceBounds.Min.X+x1, sourceBounds.Min.Y+y1)).(color.NRGBA)
			target.SetNRGBA(targetX, targetY, color.NRGBA{
				R: bilinearChannel(upperLeft.R, upperRight.R, lowerLeft.R, lowerRight.R, xWeight, yWeight),
				G: bilinearChannel(upperLeft.G, upperRight.G, lowerLeft.G, lowerRight.G, xWeight, yWeight),
				B: bilinearChannel(upperLeft.B, upperRight.B, lowerLeft.B, lowerRight.B, xWeight, yWeight),
				A: bilinearChannel(upperLeft.A, upperRight.A, lowerLeft.A, lowerRight.A, xWeight, yWeight),
			})
		}
	}
}

func interpolationPoints(position float64, length int) (int, int, float64) {
	if position <= 0 {
		return 0, min(1, length-1), 0
	}
	left := int(position)
	if left >= length-1 {
		return length - 1, length - 1, 0
	}
	return left, left + 1, position - float64(left)
}

func bilinearChannel(upperLeft, upperRight, lowerLeft, lowerRight uint8, xWeight, yWeight float64) uint8 {
	upper := float64(upperLeft)*(1-xWeight) + float64(upperRight)*xWeight
	lower := float64(lowerLeft)*(1-xWeight) + float64(lowerRight)*xWeight
	value := upper*(1-yWeight) + lower*yWeight
	return uint8(value + 0.5)
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
