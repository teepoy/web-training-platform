// Package display adapts the governed image engine to browser image and sprite reads.
package display

import (
	"context"
	"fmt"
	"strconv"
	"strings"

	scv1 "image-parser/gen/go/sc/v1"
	"image-parser/internal/imagestream"
)

type ImageKind string

const (
	ImageKindPatch  ImageKind = "patch"
	ImageKindReview ImageKind = "review"
)

type InspectionKey struct {
	InspectionTime string
	WaferKey       int
}

type ImageKey struct {
	Kind ImageKind
	InspectionKey
	DefectID      string
	ImageType     string
	ReviewImageID int
}

type ImageBytes struct {
	Key         ImageKey
	Data        []byte
	ContentType string
	Err         error
}

type Reader interface {
	GetImageBytes(ctx context.Context, keys []ImageKey) []ImageBytes
}

type UpstreamSource interface {
	GetInspection(ctx context.Context, inspectionTime string, waferKey int32) (*scv1.GetInspectionResponse, error)
	GetReviewImageFileSpec(ctx context.Context, inspectionTime string, waferKey, defectID, imageID int32) (*scv1.GetReviewImageFileSpecResponse, error)
}

type ReviewImageSource interface {
	ReadReviewImage(ctx context.Context, sourceRef string) ([]byte, error)
}

func New(upstream UpstreamSource, reviewImages ReviewImageSource, streams imagestream.Engine) (*Service, error) {
	return NewForUseCase(upstream, reviewImages, streams, imagestream.UseCaseDisplay)
}

func NewForUseCase(upstream UpstreamSource, reviewImages ReviewImageSource, streams imagestream.Engine, useCase imagestream.UseCase) (*Service, error) {
	if upstream == nil {
		return nil, fmt.Errorf("display upstream source is required")
	}
	if reviewImages == nil {
		return nil, fmt.Errorf("display review image source is required")
	}
	if streams == nil {
		return nil, fmt.Errorf("display image stream engine is required")
	}
	limits := streams.Limits(useCase)
	if limits.MaxBatchItems == 0 {
		return nil, fmt.Errorf("%s image stream batch limit must be positive", useCase)
	}
	return &Service{upstream: upstream, reviewImages: reviewImages, streams: streams, useCase: useCase}, nil
}

func NormalizeImageType(imageType string) string {
	lower := strings.ToLower(strings.TrimSpace(imageType))
	base, imageID, hasImageID := strings.Cut(lower, ":")
	var normalized string
	switch base {
	case "patch_template", "patchtemplate", "patch_reference", "patchreference", "template", "reference":
		normalized = "Reference"
	case "patch_defective", "patchdefective", "defective":
		normalized = "Defective"
	case "patch_difference", "patchdifference", "difference":
		normalized = "Difference"
	case "patch_mask", "patchmask", "mask":
		normalized = "Mask"
	case "review", "review_high_mag":
		return "review"
	default:
		return strings.TrimSpace(imageType)
	}
	if !hasImageID {
		return normalized
	}
	if normalized == "Defective" {
		return strings.TrimSpace(imageType)
	}
	parsed, err := strconv.Atoi(strings.TrimSpace(imageID))
	if err != nil || parsed < 0 {
		return strings.TrimSpace(imageType)
	}
	return fmt.Sprintf("%s:%d", normalized, parsed)
}
