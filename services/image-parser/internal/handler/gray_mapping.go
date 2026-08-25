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
type GrayMappingMode string

const (
	GrayLUTGrayscale         GrayLUT         = "gray"
	GrayLUTInvertedGrayscale GrayLUT         = "gray-inverted"
	GrayLUTViridis           GrayLUT         = "viridis"
	GrayLUTInferno           GrayLUT         = "inferno"
	GrayLUTTurbo             GrayLUT         = "turbo"
	GrayMappingModeGlobal    GrayMappingMode = "global"
	GrayMappingModeAdaptive  GrayMappingMode = "adaptive"
)

var ErrUnsupportedGrayImage = errors.New("gray mapping supports only 8-bit or 16-bit grayscale images")

type GrayMapping struct {
	Mode     GrayMappingMode
	LUT      GrayLUT
	ZMin     float64
	ZMax     float64
	BitDepth int
}

type grayWindow struct {
	min float64
	max float64
}

// PatchGrayMappings keeps the two user-facing SC tone-mapping groups explicit.
// Defective and Reference/Template share one mapping; Difference is independent.
type PatchGrayMappings struct {
	DefectiveReference *GrayMapping
	Difference         *GrayMapping
}

func (m PatchGrayMappings) ForImageType(imageType string) *GrayMapping {
	displayImageType := strings.ToLower(strings.TrimSpace(imageType))
	if strings.HasPrefix(displayImageType, "mask") || strings.HasPrefix(displayImageType, "patch_mask") || strings.HasPrefix(displayImageType, "patchmask") {
		return nil
	}
	if strings.HasPrefix(displayImageType, "difference") || strings.HasPrefix(displayImageType, "patch_difference") || strings.HasPrefix(displayImageType, "patchdifference") {
		return m.Difference
	}
	return m.DefectiveReference
}

func ParseGrayLUT(raw string) (GrayLUT, error) {
	lut := GrayLUT(strings.TrimSpace(strings.ToLower(raw)))
	if _, ok := grayLUTs[lut]; !ok {
		return "", fmt.Errorf("unsupported gray_lut %q", raw)
	}
	return lut, nil
}

func ParseGrayMappingMode(raw string) (GrayMappingMode, error) {
	mode := GrayMappingMode(strings.TrimSpace(strings.ToLower(raw)))
	if mode != GrayMappingModeGlobal && mode != GrayMappingModeAdaptive {
		return "", fmt.Errorf("unsupported gray_mode %q", raw)
	}
	return mode, nil
}

func (m GrayMapping) Validate() error {
	if m.Mode != GrayMappingModeGlobal && m.Mode != GrayMappingModeAdaptive {
		return fmt.Errorf("unsupported gray_mode %q", m.Mode)
	}
	if _, ok := grayLUTs[m.LUT]; !ok {
		return fmt.Errorf("unsupported gray_lut %q", m.LUT)
	}
	if m.Mode == GrayMappingModeGlobal {
		if math.IsNaN(m.ZMin) || math.IsInf(m.ZMin, 0) || math.IsNaN(m.ZMax) || math.IsInf(m.ZMax, 0) ||
			m.ZMin < 0 || m.ZMin > 1 || m.ZMax < 0 || m.ZMax > 1 {
			return fmt.Errorf("z_min and z_max must be normalized values between 0 and 1")
		}
		if m.ZMin >= m.ZMax {
			return fmt.Errorf("z_min must be less than z_max")
		}
	}
	if m.BitDepth != 0 && m.BitDepth != 8 && m.BitDepth != 12 && m.BitDepth != 16 {
		return fmt.Errorf("bit_depth must be 8, 12, or 16")
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
	return renderPNGWithGrayMapping(raw, size, size, mapping, nil)
}

func originalSizePNGWithGrayMapping(raw []byte, mapping GrayMapping) ([]byte, error) {
	return originalSizePNGWithGrayMappingWindow(raw, mapping, nil)
}

func originalSizePNGWithGrayMappingWindow(raw []byte, mapping GrayMapping, window *grayWindow) ([]byte, error) {
	source, _, err := image.Decode(bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	return renderDecodedPNGWithGrayMapping(source, source.Bounds().Dx(), source.Bounds().Dy(), mapping, window)
}

func renderPNGWithGrayMapping(raw []byte, width, height int, mapping GrayMapping, window *grayWindow) ([]byte, error) {
	if err := mapping.Validate(); err != nil {
		return nil, err
	}
	source, _, err := image.Decode(bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	return renderDecodedPNGWithGrayMapping(source, width, height, mapping, window)
}

func renderDecodedPNGWithGrayMapping(source image.Image, width, height int, mapping GrayMapping, override *grayWindow) ([]byte, error) {
	if err := mapping.Validate(); err != nil {
		return nil, err
	}
	if width <= 0 || height <= 0 {
		return nil, fmt.Errorf("mapped image dimensions must be positive")
	}
	target := image.NewNRGBA(image.Rect(0, 0, width, height))
	if err := renderDecodedGrayMappingInto(target, target.Bounds(), source, mapping, override); err != nil {
		return nil, err
	}

	var output bytes.Buffer
	if err := png.Encode(&output, target); err != nil {
		return nil, err
	}
	return output.Bytes(), nil
}

func renderDecodedGrayMappingInto(target *image.NRGBA, destination image.Rectangle, source image.Image, mapping GrayMapping, override *grayWindow) error {
	if err := mapping.Validate(); err != nil {
		return err
	}
	if destination.Empty() {
		return fmt.Errorf("mapped image dimensions must be positive")
	}
	if !destination.In(target.Bounds()) {
		return fmt.Errorf("mapped image destination exceeds target bounds")
	}
	sample, detectedBitDepth, err := graySampler(source)
	if err != nil {
		return err
	}
	window, err := grayMappingWindow([]image.Image{source}, mapping, override)
	if err != nil {
		return err
	}

	lut := grayLUTs[mapping.LUT]
	sourceBounds := source.Bounds()
	sourceWidth := sourceBounds.Dx()
	sourceHeight := sourceBounds.Dy()
	for targetY := destination.Min.Y; targetY < destination.Max.Y; targetY++ {
		sourceY := sourceBounds.Min.Y + (targetY-destination.Min.Y)*sourceHeight/destination.Dy()
		for targetX := destination.Min.X; targetX < destination.Max.X; targetX++ {
			sourceX := sourceBounds.Min.X + (targetX-destination.Min.X)*sourceWidth/destination.Dx()
			value := sample(sourceX, sourceY)
			target.SetNRGBA(targetX, targetY, lut[grayLUTIndex(value, mapping, detectedBitDepth, window)])
		}
	}
	return nil
}

func adaptiveGrayWindowForImages(rawImages [][]byte, mapping GrayMapping) (grayWindow, error) {
	if err := mapping.Validate(); err != nil {
		return grayWindow{}, err
	}
	if mapping.Mode != GrayMappingModeAdaptive {
		return grayWindow{}, fmt.Errorf("adaptive range requires adaptive gray mapping mode")
	}
	images := make([]image.Image, 0, len(rawImages))
	for _, raw := range rawImages {
		source, _, err := image.Decode(bytes.NewReader(raw))
		if err != nil {
			return grayWindow{}, err
		}
		images = append(images, source)
	}
	return adaptiveGrayWindowForDecodedImages(images, mapping)
}

func adaptiveGrayWindowForDecodedImages(images []image.Image, mapping GrayMapping) (grayWindow, error) {
	if err := mapping.Validate(); err != nil {
		return grayWindow{}, err
	}
	if mapping.Mode != GrayMappingModeAdaptive {
		return grayWindow{}, fmt.Errorf("adaptive range requires adaptive gray mapping mode")
	}
	return grayMappingWindow(images, mapping, nil)
}

func grayMappingWindow(images []image.Image, mapping GrayMapping, override *grayWindow) (grayWindow, error) {
	if override != nil {
		return *override, nil
	}
	if mapping.Mode == GrayMappingModeGlobal {
		return grayWindow{min: mapping.ZMin, max: mapping.ZMax}, nil
	}
	if len(images) == 0 {
		return grayWindow{}, fmt.Errorf("adaptive gray mapping requires at least one image")
	}
	window := grayWindow{min: math.Inf(1), max: math.Inf(-1)}
	for _, source := range images {
		minimum, maximum, err := normalizedGrayRange(source, mapping.BitDepth)
		if err != nil {
			return grayWindow{}, err
		}
		window.min = math.Min(window.min, minimum)
		window.max = math.Max(window.max, maximum)
	}
	return window, nil
}

func normalizedGrayRange(source image.Image, requestedBitDepth int) (float64, float64, error) {
	sample, detectedBitDepth, err := graySampler(source)
	if err != nil {
		return 0, 0, err
	}
	bitDepth := requestedBitDepth
	if bitDepth == 0 {
		bitDepth = detectedBitDepth
	}
	maximum := float64((uint64(1) << uint(bitDepth)) - 1)
	minimumValue, maximumValue := math.Inf(1), math.Inf(-1)
	bounds := source.Bounds()
	for y := bounds.Min.Y; y < bounds.Max.Y; y++ {
		for x := bounds.Min.X; x < bounds.Max.X; x++ {
			value := float64(sample(x, y)) / maximum
			minimumValue = math.Min(minimumValue, value)
			maximumValue = math.Max(maximumValue, value)
		}
	}
	return minimumValue, maximumValue, nil
}

func graySampler(source image.Image) (func(int, int) uint16, int, error) {
	switch typed := source.(type) {
	case *image.Gray:
		return func(x, y int) uint16 {
			return uint16(typed.GrayAt(x, y).Y)
		}, 8, nil
	case *image.Gray16:
		return func(x, y int) uint16 {
			return typed.Gray16At(x, y).Y
		}, 16, nil
	default:
		bounds := source.Bounds()
		for y := bounds.Min.Y; y < bounds.Max.Y; y++ {
			for x := bounds.Min.X; x < bounds.Max.X; x++ {
				red, green, blue, alpha := source.At(x, y).RGBA()
				if red != green || green != blue || alpha != 65535 {
					return nil, 0, ErrUnsupportedGrayImage
				}
			}
		}
		return func(x, y int) uint16 {
			red, _, _, _ := source.At(x, y).RGBA()
			return uint16(red)
		}, 16, nil
	}
}

func grayLUTIndex(value uint16, mapping GrayMapping, detectedBitDepth int, window grayWindow) int {
	bitDepth := mapping.BitDepth
	if bitDepth == 0 {
		bitDepth = detectedBitDepth
	}
	maximum := float64((uint64(1) << uint(bitDepth)) - 1)
	normalized := float64(value) / maximum
	if window.max <= window.min {
		return 0
	}
	windowed := (normalized - window.min) / (window.max - window.min)
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
