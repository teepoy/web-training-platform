//go:build upstream_mock

package main

import (
	"image-parser/dev_adapters/upstream_mock/s3review"
	"image-parser/dev_adapters/upstream_mock/s3zip"
	"image-parser/internal/artifactcache"
	"image-parser/internal/display"
	"image-parser/internal/equipment/legacyrangezip"
)

func newPatchArchiveSource() (legacyrangezip.ArchiveSource, error) {
	return s3zip.NewFromEnvironment()
}

func newReviewImageSource(cache artifactcache.Cache) (display.ReviewImageSource, error) {
	return s3review.New(cache)
}
