//go:build upstream_mock

package s3zip

import (
	"strings"
	"testing"

	scv1 "image-parser/gen/go/sc/v1"
)

func TestObjectLocationRejectsNonS3MockReference(t *testing.T) {
	_, _, err := objectLocation(&scv1.ZipRef{})
	if err == nil || !strings.Contains(err.Error(), "S3 bucket and key") {
		t.Fatalf("objectLocation error = %v, want explicit S3 locator error", err)
	}
}

func TestObjectLocationNormalizesMockReference(t *testing.T) {
	bucket, key, err := objectLocation(&scv1.ZipRef{S3Bucket: " fixtures ", S3Key: " inspection/a.zip "})
	if err != nil {
		t.Fatal(err)
	}
	if bucket != "fixtures" || key != "inspection/a.zip" {
		t.Fatalf("objectLocation = %q/%q", bucket, key)
	}
}
