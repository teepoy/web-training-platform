package handler

import (
	"bytes"
	"errors"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"math"
	"strings"
)

type GrayLUT string

const (
	GrayLUTGrayscale         GrayLUT = "gray"
	GrayLUTInvertedGrayscale GrayLUT = "gray-inverted"
	GrayLUTViridis           GrayLUT = "viridis"
	GrayLUTInferno           GrayLUT = "inferno"
	GrayLUTTurbo             GrayLUT = "turbo"
)

var ErrUnsupportedGrayImage = errors.New("gray mapping supports only 8-bit or 16-bit grayscale images")

type GrayMapping struct {
	LUT  GrayLUT
	ZMin float64
	ZMax float64
}

func ParseGrayLUT(raw string) (GrayLUT, error) {
	lut := GrayLUT(strings.TrimSpace(strings.ToLower(raw)))
	if _, ok := grayLUTs[lut]; !ok {
		return "", fmt.Errorf("unsupported gray_lut %q", raw)
	}
	return lut, nil
}

func (m GrayMapping) Validate() error {
	if _, ok := grayLUTs[m.LUT]; !ok {
		return fmt.Errorf("unsupported gray_lut %q", m.LUT)
	}
	if math.IsNaN(m.ZMin) || math.IsInf(m.ZMin, 0) || math.IsNaN(m.ZMax) || math.IsInf(m.ZMax, 0) ||
		m.ZMin < 0 || m.ZMin > 1 || m.ZMax < 0 || m.ZMax > 1 {
		return fmt.Errorf("z_min and z_max must be normalized values between 0 and 1")
	}
	if m.ZMin >= m.ZMax {
		return fmt.Errorf("z_min must be less than z_max")
	}
	return nil
}

type lutStop struct {
	position float64
	color    color.NRGBA
}

var grayLUTs = map[GrayLUT][256]color.NRGBA{
	GrayLUTGrayscale: buildGrayLUT([]lutStop{
		{position: 0, color: color.NRGBA{R: 0, G: 0, B: 0, A: 255}},
		{position: 1, color: color.NRGBA{R: 255, G: 255, B: 255, A: 255}},
	}),
	GrayLUTInvertedGrayscale: buildGrayLUT([]lutStop{
		{position: 0, color: color.NRGBA{R: 255, G: 255, B: 255, A: 255}},
		{position: 1, color: color.NRGBA{R: 0, G: 0, B: 0, A: 255}},
	}),
	GrayLUTViridis: buildGrayLUT([]lutStop{
		{position: 0, color: color.NRGBA{R: 68, G: 1, B: 84, A: 255}},
		{position: 0.25, color: color.NRGBA{R: 59, G: 82, B: 139, A: 255}},
		{position: 0.5, color: color.NRGBA{R: 33, G: 145, B: 140, A: 255}},
		{position: 0.75, color: color.NRGBA{R: 94, G: 201, B: 98, A: 255}},
		{position: 1, color: color.NRGBA{R: 253, G: 231, B: 37, A: 255}},
	}),
	GrayLUTInferno: buildGrayLUT([]lutStop{
		{position: 0, color: color.NRGBA{R: 0, G: 0, B: 4, A: 255}},
		{position: 0.2, color: color.NRGBA{R: 66, G: 10, B: 104, A: 255}},
		{position: 0.4, color: color.NRGBA{R: 147, G: 38, B: 103, A: 255}},
		{position: 0.6, color: color.NRGBA{R: 221, G: 81, B: 58, A: 255}},
		{position: 0.8, color: color.NRGBA{R: 252, G: 165, B: 10, A: 255}},
		{position: 1, color: color.NRGBA{R: 252, G: 255, B: 164, A: 255}},
	}),
	GrayLUTTurbo: buildGrayLUT([]lutStop{
		{position: 0, color: color.NRGBA{R: 48, G: 18, B: 59, A: 255}},
		{position: 0.17, color: color.NRGBA{R: 70, G: 98, B: 215, A: 255}},
		{position: 0.33, color: color.NRGBA{R: 26, G: 228, B: 182, A: 255}},
		{position: 0.5, color: color.NRGBA{R: 164, G: 252, B: 60, A: 255}},
		{position: 0.67, color: color.NRGBA{R: 249, G: 186, B: 56, A: 255}},
		{position: 0.83, color: color.NRGBA{R: 233, G: 75, B: 24, A: 255}},
		{position: 1, color: color.NRGBA{R: 122, G: 4, B: 3, A: 255}},
	}),
}

func resizeSquarePNGWithGrayMapping(raw []byte, size int, mapping GrayMapping) ([]byte, error) {
	if err := mapping.Validate(); err != nil {
		return nil, err
	}
	source, _, err := image.Decode(bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	sample, err := gray16Sampler(source)
	if err != nil {
		return nil, err
	}

	lut := grayLUTs[mapping.LUT]
	target := image.NewNRGBA(image.Rect(0, 0, size, size))
	sourceBounds := source.Bounds()
	for targetY := range size {
		sourceY := (float64(targetY)+0.5)*float64(sourceBounds.Dy())/float64(size) - 0.5
		y0, y1, yWeight := interpolationPoints(sourceY, sourceBounds.Dy())
		for targetX := range size {
			sourceX := (float64(targetX)+0.5)*float64(sourceBounds.Dx())/float64(size) - 0.5
			x0, x1, xWeight := interpolationPoints(sourceX, sourceBounds.Dx())
			value := bilinearGray16(
				sample(sourceBounds.Min.X+x0, sourceBounds.Min.Y+y0),
				sample(sourceBounds.Min.X+x1, sourceBounds.Min.Y+y0),
				sample(sourceBounds.Min.X+x0, sourceBounds.Min.Y+y1),
				sample(sourceBounds.Min.X+x1, sourceBounds.Min.Y+y1),
				xWeight,
				yWeight,
			)
			target.SetNRGBA(targetX, targetY, lut[grayLUTIndex(value, mapping)])
		}
	}

	var output bytes.Buffer
	if err := png.Encode(&output, target); err != nil {
		return nil, err
	}
	return output.Bytes(), nil
}

func gray16Sampler(source image.Image) (func(int, int) uint16, error) {
	switch typed := source.(type) {
	case *image.Gray:
		return func(x, y int) uint16 {
			return uint16(typed.GrayAt(x, y).Y) * 257
		}, nil
	case *image.Gray16:
		return func(x, y int) uint16 {
			return typed.Gray16At(x, y).Y
		}, nil
	default:
		bounds := source.Bounds()
		for y := bounds.Min.Y; y < bounds.Max.Y; y++ {
			for x := bounds.Min.X; x < bounds.Max.X; x++ {
				red, green, blue, alpha := source.At(x, y).RGBA()
				if red != green || green != blue || alpha != 65535 {
					return nil, ErrUnsupportedGrayImage
				}
			}
		}
		return func(x, y int) uint16 {
			red, _, _, _ := source.At(x, y).RGBA()
			return uint16(red)
		}, nil
	}
}

func bilinearGray16(upperLeft, upperRight, lowerLeft, lowerRight uint16, xWeight, yWeight float64) uint16 {
	upper := float64(upperLeft)*(1-xWeight) + float64(upperRight)*xWeight
	lower := float64(lowerLeft)*(1-xWeight) + float64(lowerRight)*xWeight
	return uint16(upper*(1-yWeight) + lower*yWeight + 0.5)
}

func grayLUTIndex(value uint16, mapping GrayMapping) int {
	normalized := float64(value) / 65535
	windowed := (normalized - mapping.ZMin) / (mapping.ZMax - mapping.ZMin)
	if windowed <= 0 {
		return 0
	}
	if windowed >= 1 {
		return 255
	}
	return int(windowed*255 + 0.5)
}

func buildGrayLUT(stops []lutStop) [256]color.NRGBA {
	var lut [256]color.NRGBA
	for index := range lut {
		position := float64(index) / 255
		left, right := stops[0], stops[len(stops)-1]
		for stopIndex := 1; stopIndex < len(stops); stopIndex++ {
			if position <= stops[stopIndex].position {
				left = stops[stopIndex-1]
				right = stops[stopIndex]
				break
			}
		}
		span := right.position - left.position
		weight := 0.0
		if span > 0 {
			weight = (position - left.position) / span
		}
		lut[index] = color.NRGBA{
			R: interpolateLUTChannel(left.color.R, right.color.R, weight),
			G: interpolateLUTChannel(left.color.G, right.color.G, weight),
			B: interpolateLUTChannel(left.color.B, right.color.B, weight),
			A: 255,
		}
	}
	return lut
}

func interpolateLUTChannel(left, right uint8, weight float64) uint8 {
	return uint8(float64(left)*(1-weight) + float64(right)*weight + 0.5)
}
