//go:build !upstream_mock

package main

import (
	"fmt"

	"image-parser/internal/artifactcache"
	"image-parser/internal/display"
	"image-parser/internal/equipment/legacyrangezip"
)

func newPatchArchiveSource() (legacyrangezip.ArchiveSource, error) {
	return nil, fmt.Errorf("production patch archive source adapter is not linked")
}

func newReviewImageSource(artifactcache.Cache) (display.ReviewImageSource, error) {
	return nil, fmt.Errorf("production review image source adapter is not linked")
}
