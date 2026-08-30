//go:build upstream_mock

// Package s3review adapts upstream mock review-image references to the
// production-owned review image source interface.
package s3review

import (
	"context"
	"fmt"

	"image-parser/internal/artifactcache"
	"image-parser/internal/artifactsource"
	"image-parser/internal/display"

	"image-parser/dev_adapters/upstream_mock/s3object"
)

type Source struct {
	reader *artifactsource.CachedReader
}

func New(cache artifactcache.Cache) (*Source, error) {
	objects, err := s3object.NewFromEnvironment()
	if err != nil {
		return nil, fmt.Errorf("configure upstream mock review image source: %w", err)
	}
	reader, err := artifactsource.NewCachedReader(objects, cache, "upstream-mock.review-image.s3.v1")
	if err != nil {
		return nil, err
	}
	return &Source{reader: reader}, nil
}

func (s *Source) ReadReviewImage(ctx context.Context, sourceRef string) ([]byte, error) {
	if s == nil || s.reader == nil {
		return nil, fmt.Errorf("upstream mock review image source is not configured")
	}
	return s.reader.Read(ctx, sourceRef)
}

var _ display.ReviewImageSource = (*Source)(nil)
