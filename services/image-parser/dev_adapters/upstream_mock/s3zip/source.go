//go:build upstream_mock

// Package s3zip adapts the standalone upstream mock's S3 ZIP fixtures to the
// production-owned patch archive source interface.
package s3zip

import (
	"context"
	"fmt"
	"strings"

	"image-parser/dev_adapters/upstream_mock/s3object"
	scv1 "image-parser/gen/go/sc/v1"
	"image-parser/internal/equipment/legacyrangezip"
)

type Source struct {
	objects *s3object.Store
}

func NewFromEnvironment() (*Source, error) {
	objects, err := s3object.NewFromEnvironment()
	if err != nil {
		return nil, fmt.Errorf("configure upstream mock ZIP source: %w", err)
	}
	return &Source{objects: objects}, nil
}

func (s *Source) DescribeArchive(ctx context.Context, ref *scv1.ZipRef) (legacyrangezip.ArchiveDescriptor, error) {
	bucket, key, err := objectLocation(ref)
	if err != nil {
		return legacyrangezip.ArchiveDescriptor{}, err
	}
	sourceRef := "s3://" + bucket + "/" + key
	revision, err := s.objects.Describe(ctx, sourceRef)
	if err != nil {
		return legacyrangezip.ArchiveDescriptor{}, err
	}
	return legacyrangezip.ArchiveDescriptor{
		Identity: revision.Identity,
		Revision: revision.Revision,
		Size:     revision.Size,
	}, nil
}

func (s *Source) DownloadArchive(ctx context.Context, ref *scv1.ZipRef, destination string) error {
	bucket, key, err := objectLocation(ref)
	if err != nil {
		return err
	}
	return s.objects.Download(ctx, "s3://"+bucket+"/"+key, destination)
}

func objectLocation(ref *scv1.ZipRef) (string, string, error) {
	if ref == nil {
		return "", "", fmt.Errorf("upstream mock ZIP reference is required")
	}
	bucket := strings.TrimSpace(ref.S3Bucket)
	key := strings.TrimSpace(ref.S3Key)
	if bucket == "" || key == "" {
		return "", "", fmt.Errorf("upstream mock ZIP reference requires S3 bucket and key")
	}
	return bucket, key, nil
}

var _ legacyrangezip.ArchiveSource = (*Source)(nil)
