// Package display adapts the governed image engine to browser image and sprite reads.
package display

import (
	"context"
	"fmt"
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

type ReviewObjectStore interface {
	ReadObject(ctx context.Context, bucket, key string) ([]byte, error)
}

func New(upstream UpstreamSource, reviewObjects ReviewObjectStore, streams imagestream.Engine) (*Service, error) {
	if upstream == nil {
		return nil, fmt.Errorf("display upstream source is required")
	}
	if reviewObjects == nil {
		return nil, fmt.Errorf("display review object store is required")
	}
	if streams == nil {
		return nil, fmt.Errorf("display image stream engine is required")
	}
	return &Service{upstream: upstream, reviewObjects: reviewObjects, streams: streams}, nil
}

func NormalizeImageType(imageType string) string {
	lower := strings.ToLower(strings.TrimSpace(imageType))
	switch lower {
	case "patch_template", "patchtemplate", "patch_reference", "patchreference", "template", "reference":
		return "Reference"
	case "patch_defective", "patchdefective", "defective":
		return "Defective"
	case "patch_difference", "patchdifference", "difference":
		return "Difference"
	case "review", "review_high_mag":
		return "review"
	default:
		return strings.TrimSpace(imageType)
	}
}
