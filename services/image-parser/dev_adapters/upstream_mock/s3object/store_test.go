//go:build upstream_mock

package s3object

import (
	"strings"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

func TestObjectLocationRequiresExplicitS3Reference(t *testing.T) {
	bucket, key, err := ObjectLocation("s3:// fixtures / inspection/review.jpg ")
	if err != nil {
		t.Fatal(err)
	}
	if bucket != "fixtures" || key != "inspection/review.jpg" {
		t.Fatalf("ObjectLocation = %q/%q", bucket, key)
	}
	if _, _, err := ObjectLocation("fixtures/inspection/review.jpg"); err == nil {
		t.Fatal("expected non-S3 source reference to fail")
	}
}

func TestSourceRevisionPrefersVersionThenETagThenMtimeAndSize(t *testing.T) {
	modified := time.Date(2026, 8, 21, 1, 2, 3, 4, time.UTC)
	tests := []struct {
		name string
		head s3.HeadObjectOutput
		want string
	}{
		{name: "version", head: s3.HeadObjectOutput{VersionId: aws.String("version-2"), ETag: aws.String("etag")}, want: "version:version-2"},
		{name: "etag", head: s3.HeadObjectOutput{ETag: aws.String("\"etag-2\"")}, want: "etag:etag-2"},
		{name: "mtime-size", head: s3.HeadObjectOutput{LastModified: &modified, ContentLength: aws.Int64(9)}, want: "mtime-size:1787274123000000004:9"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			got, err := sourceRevision(&test.head)
			if err != nil {
				t.Fatal(err)
			}
			if got != test.want {
				t.Fatalf("revision = %q, want %q", got, test.want)
			}
		})
	}
}

func TestConfigurationDoesNotInventCredentials(t *testing.T) {
	for _, name := range []string{
		"UPSTREAM_MOCK_S3_ENDPOINT", "UPSTREAM_MOCK_S3_REGION",
		"UPSTREAM_MOCK_S3_ACCESS_KEY", "UPSTREAM_MOCK_S3_SECRET_KEY",
	} {
		t.Setenv(name, "")
	}
	_, err := configFromEnvironment()
	if err == nil || !strings.Contains(err.Error(), "ENDPOINT") {
		t.Fatalf("configuration error = %v, want explicit endpoint requirement", err)
	}
}
