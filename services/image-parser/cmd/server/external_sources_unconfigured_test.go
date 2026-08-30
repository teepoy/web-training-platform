//go:build !upstream_mock

package main

import (
	"strings"
	"testing"
)

func TestProductionBuildRequiresExplicitImageSourceAdapters(t *testing.T) {
	_, err := newPatchArchiveSource()
	if err == nil || !strings.Contains(err.Error(), "production patch archive source adapter") {
		t.Fatalf("newPatchArchiveSource error = %v", err)
	}
	_, err = newReviewImageSource(nil)
	if err == nil || !strings.Contains(err.Error(), "production review image source adapter") {
		t.Fatalf("newReviewImageSource error = %v", err)
	}
}
