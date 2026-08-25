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
	resizeNearestInto(target, target.Bounds(), source)
}

func resizeNearestInto(target *image.NRGBA, destination image.Rectangle, source image.Image) {
	sourceBounds := source.Bounds()
	sourceWidth := sourceBounds.Dx()
	sourceHeight := sourceBounds.Dy()
	for targetY := destination.Min.Y; targetY < destination.Max.Y; targetY++ {
		sourceY := sourceBounds.Min.Y + (targetY-destination.Min.Y)*sourceHeight/destination.Dy()
		for targetX := destination.Min.X; targetX < destination.Max.X; targetX++ {
			sourceX := sourceBounds.Min.X + (targetX-destination.Min.X)*sourceWidth/destination.Dx()
			target.SetNRGBA(targetX, targetY, nrgbaAt(source, sourceX, sourceY))
		}
	}
}

func resizeBilinear(target *image.NRGBA, source image.Image) {
	resizeBilinearInto(target, target.Bounds(), source)
}

func resizeBilinearInto(target *image.NRGBA, destination image.Rectangle, source image.Image) {
	sourceBounds := source.Bounds()
	sourceWidth := sourceBounds.Dx()
	sourceHeight := sourceBounds.Dy()
	for targetY := destination.Min.Y; targetY < destination.Max.Y; targetY++ {
		sourceY := (float64(targetY-destination.Min.Y)+0.5)*float64(sourceHeight)/float64(destination.Dy()) - 0.5
		y0, y1, yWeight := interpolationPoints(sourceY, sourceHeight)
		for targetX := destination.Min.X; targetX < destination.Max.X; targetX++ {
			sourceX := (float64(targetX-destination.Min.X)+0.5)*float64(sourceWidth)/float64(destination.Dx()) - 0.5
			x0, x1, xWeight := interpolationPoints(sourceX, sourceWidth)
			upperLeft := nrgbaAt(source, sourceBounds.Min.X+x0, sourceBounds.Min.Y+y0)
			upperRight := nrgbaAt(source, sourceBounds.Min.X+x1, sourceBounds.Min.Y+y0)
			lowerLeft := nrgbaAt(source, sourceBounds.Min.X+x0, sourceBounds.Min.Y+y1)
			lowerRight := nrgbaAt(source, sourceBounds.Min.X+x1, sourceBounds.Min.Y+y1)
			target.SetNRGBA(targetX, targetY, color.NRGBA{
				R: bilinearChannel(upperLeft.R, upperRight.R, lowerLeft.R, lowerRight.R, xWeight, yWeight),
				G: bilinearChannel(upperLeft.G, upperRight.G, lowerLeft.G, lowerRight.G, xWeight, yWeight),
				B: bilinearChannel(upperLeft.B, upperRight.B, lowerLeft.B, lowerRight.B, xWeight, yWeight),
				A: bilinearChannel(upperLeft.A, upperRight.A, lowerLeft.A, lowerRight.A, xWeight, yWeight),
			})
		}
	}
}

func nrgbaAt(source image.Image, x, y int) color.NRGBA {
	switch typed := source.(type) {
	case *image.NRGBA:
		offset := typed.PixOffset(x, y)
		return color.NRGBA{
			R: typed.Pix[offset],
			G: typed.Pix[offset+1],
			B: typed.Pix[offset+2],
			A: typed.Pix[offset+3],
		}
	case *image.RGBA:
		offset := typed.PixOffset(x, y)
		alpha := typed.Pix[offset+3]
		if alpha == 0 || alpha == 255 {
			return color.NRGBA{
				R: typed.Pix[offset],
				G: typed.Pix[offset+1],
				B: typed.Pix[offset+2],
				A: alpha,
			}
		}
		return color.NRGBA{
			R: uint8(min(uint32(typed.Pix[offset])*255/uint32(alpha), 255)),
			G: uint8(min(uint32(typed.Pix[offset+1])*255/uint32(alpha), 255)),
			B: uint8(min(uint32(typed.Pix[offset+2])*255/uint32(alpha), 255)),
			A: alpha,
		}
	case *image.Gray:
		value := typed.Pix[typed.PixOffset(x, y)]
		return color.NRGBA{R: value, G: value, B: value, A: 255}
	case *image.Gray16:
		offset := typed.PixOffset(x, y)
		value := typed.Pix[offset]
		return color.NRGBA{R: value, G: value, B: value, A: 255}
	case *image.YCbCr:
		value := typed.YCbCrAt(x, y)
		red, green, blue := color.YCbCrToRGB(value.Y, value.Cb, value.Cr)
		return color.NRGBA{R: red, G: green, B: blue, A: 255}
	default:
		return color.NRGBAModel.Convert(source.At(x, y)).(color.NRGBA)
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
	drawBlankCell(canvas, canvas.Bounds())
	var buf bytes.Buffer
	if err := png.Encode(&buf, canvas); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

func drawBlankCell(canvas interface{ Set(int, int, color.Color) }, destination image.Rectangle) {
	background := color.RGBA{R: 48, G: 52, B: 60, A: 255}
	alternate := color.RGBA{R: 68, G: 74, B: 84, A: 255}
	marker := color.RGBA{R: 142, G: 151, B: 166, A: 255}
	size := destination.Dx()
	tileSize := max(4, size/4)
	for y := destination.Min.Y; y < destination.Max.Y; y++ {
		for x := destination.Min.X; x < destination.Max.X; x++ {
			pixel := background
			if ((x-destination.Min.X)/tileSize+(y-destination.Min.Y)/tileSize)%2 == 1 {
				pixel = alternate
			}
			canvas.Set(x, y, pixel)
		}
	}
	markerWidth := max(1, size/32)
	for offset := -markerWidth; offset <= markerWidth; offset++ {
		for position := 0; position < size; position++ {
			if x := position + offset; x >= 0 && x < size {
				canvas.Set(destination.Min.X+x, destination.Min.Y+position, marker)
				canvas.Set(destination.Min.X+size-1-x, destination.Min.Y+position, marker)
			}
		}
	}
}
