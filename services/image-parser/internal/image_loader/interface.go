package image_loader

import (
	"context"
	"strings"
	"time"

	scv1 "image-parser/gen/go/sc/v1"
	"image-parser/internal/image_loader/cache"
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

type ImageLoader interface {
	GetImageBytes(ctx context.Context, keys []ImageKey) []ImageBytes
	WarmInspection(ctx context.Context, inspection InspectionKey, defectIDs []string, recordPrefix string) (int, error)
}

type Options struct {
	Upstream             UpstreamSource
	CacheSizeMB          int
	CacheDir             string
	CacheTTL             time.Duration
	CacheCleanupInterval time.Duration
	CacheMaxBytes        int64
}

type UpstreamSource interface {
	GetInspection(ctx context.Context, inspectionTime string, waferKey int32) (*scv1.GetInspectionResponse, error)
	GetInspectionPatchZips(ctx context.Context, inspectionTime, lotID, waferID, device, layerID string) (*scv1.GetInspectionPatchZipsResponse, error)
	GetReviewImageFileSpec(ctx context.Context, inspectionTime string, waferKey, defectID, imageID int32) (*scv1.GetReviewImageFileSpecResponse, error)
}

type objectLoader interface {
	LoadPatchZip(ctx context.Context, bucket, key string) ([]byte, error)
	LoadReviewObject(ctx context.Context, bucket, key string) ([]byte, error)
}

type s3ImageLoader struct{}

func Initialize(opts Options) (ImageLoader, func(), error) {
	if opts.CacheSizeMB <= 0 {
		opts.CacheSizeMB = 1024
	}
	_ = getZips()
	_ = getReview()

	localFileCache, err := cache.NewLocalFileCache(cache.LocalFileCacheConfig{
		Dir:             opts.CacheDir,
		TTL:             opts.CacheTTL,
		CleanupInterval: opts.CacheCleanupInterval,
		MaxBytes:        opts.CacheMaxBytes,
	})
	if err != nil {
		return nil, nil, err
	}
	zipCache, err := cache.New(
		opts.CacheSizeMB,
		opts.CacheTTL,
		cache.WithLocalFileCache(localFileCache),
	)
	if err != nil {
		_ = localFileCache.Close()
		return nil, nil, err
	}

	loader := s3ImageLoader{}
	warmer := cache.NewWarmer(zipCache, func(bucket, key string) ([]byte, error) {
		return loader.LoadPatchZip(context.Background(), bucket, key)
	})

	return newResolver(opts.Upstream, loader, zipCache, warmer), func() {
		_ = zipCache.Close()
	}, nil
}

func (r s3ImageLoader) LoadPatchZip(ctx context.Context, bucket, key string) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return downloadFullZip(getZips(), bucket, key)
}

func (r s3ImageLoader) LoadReviewObject(ctx context.Context, bucket, key string) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return downloadFullZip(getReview(), bucket, key)
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
