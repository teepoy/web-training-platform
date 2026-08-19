package image_loader

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	scv1 "image-parser/gen/go/sc/v1"
	"image-parser/internal/filesource"
	"image-parser/internal/sourcecache"
	"image-parser/internal/sourceformat"
	"image-parser/internal/sourceformat/directfiles"
	"image-parser/internal/sourceformat/legacyrangezip"
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
	SourceFormat  string
	DefectID      string
	ImageType     string
	ReviewImageID int
	RolePaths     map[string]string
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
	CacheTTL             time.Duration
	CacheCleanupInterval time.Duration
	CacheMaxBytes        int64
	PatchSource          PatchSourceConfig
}

type PatchSourceStager string

const (
	PatchSourceStagerNone       PatchSourceStager = "none"
	PatchSourceStagerScUpstream PatchSourceStager = "sc_upstream"
)

type PatchSourceConfig struct {
	Format    string
	Root      string
	Kind      filesource.Kind
	Ownership filesource.Ownership
	Stager    PatchSourceStager
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
	loader := s3ImageLoader{}
	patches, source, err := initializePatchSource(opts, loader)
	if err != nil {
		return nil, nil, err
	}
	var janitor *sourcecache.Janitor
	if source.Ownership() == filesource.OwnershipSharedCache {
		janitor, err = sourcecache.Start(
			source,
			opts.CacheTTL,
			opts.CacheCleanupInterval,
			opts.CacheMaxBytes,
		)
		if err != nil {
			return nil, nil, err
		}
	}
	return newResolver(opts.Upstream, loader, patches), func() {
		if janitor != nil {
			janitor.Close()
		}
		if source.Ownership() == filesource.OwnershipJobOwned {
			_ = source.Cleanup()
		}
	}, nil
}

type patchObjectLoader struct{ loader objectLoader }

func (l patchObjectLoader) LoadPatchObject(ctx context.Context, bucket, key string) ([]byte, error) {
	return l.loader.LoadPatchZip(ctx, bucket, key)
}

func initializePatchSource(opts Options, loader objectLoader) (*sourceformat.Resolver, *filesource.Source, error) {
	config := opts.PatchSource
	if strings.TrimSpace(config.Format) == "" {
		return nil, nil, fmt.Errorf("patch source format is required")
	}
	if strings.TrimSpace(config.Root) == "" {
		return nil, nil, fmt.Errorf("patch filesystem source root is required")
	}
	if config.Kind == "" {
		config.Kind = filesource.KindDirectory
	}
	if config.Ownership == "" {
		config.Ownership = filesource.OwnershipBorrowed
	}
	if config.Ownership != filesource.OwnershipBorrowed && config.Kind == filesource.KindDirectory {
		if err := os.MkdirAll(config.Root, 0o750); err != nil {
			return nil, nil, fmt.Errorf("create patch filesystem source root: %w", err)
		}
	}
	source, err := filesource.Open(config.Root, config.Kind, config.Ownership)
	if err != nil {
		return nil, nil, err
	}
	var driver sourceformat.Driver
	switch config.Format {
	case directfiles.FormatID:
		driver = directfiles.Driver{}
	case legacyrangezip.FormatID:
		driver = legacyrangezip.Driver{}
	default:
		return nil, nil, fmt.Errorf("unsupported patch source format %q", config.Format)
	}
	var stager sourceformat.Stager
	switch config.Stager {
	case "", PatchSourceStagerNone:
	case PatchSourceStagerScUpstream:
		if config.Format != legacyrangezip.FormatID {
			return nil, nil, fmt.Errorf("SC upstream stager requires source format %q", legacyrangezip.FormatID)
		}
		if opts.Upstream == nil {
			return nil, nil, fmt.Errorf("SC upstream stager requires an upstream client")
		}
		stager = legacyrangezip.NewUpstreamStager(opts.Upstream, patchObjectLoader{loader: loader})
	default:
		return nil, nil, fmt.Errorf("unsupported patch source stager %q", config.Stager)
	}
	resolver, err := sourceformat.NewResolver(source, driver, stager)
	if err != nil {
		return nil, nil, err
	}
	return resolver, source, nil
}

func (r s3ImageLoader) LoadPatchZip(ctx context.Context, bucket, key string) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return downloadObject(ctx, getZips(), bucket, key)
}

func (r s3ImageLoader) LoadReviewObject(ctx context.Context, bucket, key string) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return downloadObject(ctx, getReview(), bucket, key)
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
