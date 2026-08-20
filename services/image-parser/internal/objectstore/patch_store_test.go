package objectstore

import (
	"strings"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

func TestSourceRevisionPrefersVersionThenETagThenMtimeAndSize(t *testing.T) {
	modified := time.Date(2026, 8, 21, 1, 2, 3, 4, time.UTC)
	tests := []struct {
		name string
		head s3.HeadObjectOutput
		want string
	}{
		{
			name: "version",
			head: s3.HeadObjectOutput{VersionId: aws.String("version-2"), ETag: aws.String("etag"), LastModified: &modified, ContentLength: aws.Int64(9)},
			want: "version:version-2",
		},
		{
			name: "etag",
			head: s3.HeadObjectOutput{ETag: aws.String("\"etag-2\""), LastModified: &modified, ContentLength: aws.Int64(9)},
			want: "etag:etag-2",
		},
		{
			name: "mtime-size",
			head: s3.HeadObjectOutput{LastModified: &modified, ContentLength: aws.Int64(9)},
			want: "mtime-size:1787274123000000004:9",
		},
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

func TestSourceRevisionRejectsMissingFreshnessMetadata(t *testing.T) {
	if _, err := sourceRevision(&s3.HeadObjectOutput{}); err == nil {
		t.Fatal("expected missing source revision error")
	}
}

func TestPatchStoreConfigurationDoesNotInventObjectStoreCredentials(t *testing.T) {
	for _, name := range []string{
		"SC_PATCH_S3_ENDPOINT", "SC_PATCH_S3_REGION", "SC_PATCH_S3_ACCESS_KEY", "SC_PATCH_S3_SECRET_KEY",
		"MINIO_ENDPOINT", "MINIO_REGION", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY",
	} {
		t.Setenv(name, "")
	}
	_, err := configFromEnvironment("SC_PATCH_S3")
	if err == nil || !strings.Contains(err.Error(), "ENDPOINT") {
		t.Fatalf("configuration error = %v, want explicit endpoint requirement", err)
	}
}
