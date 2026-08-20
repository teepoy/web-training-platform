// Package objectstore provides streaming access to image source artifacts.
package objectstore

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"

	"image-parser/internal/equipment/legacyrangezip"
)

type PatchStore struct {
	client *s3.Client
}

func NewPatchStoreFromEnvironment() (*PatchStore, error) {
	return newStoreFromEnvironment("SC_PATCH_S3")
}

func NewReviewStoreFromEnvironment() (*PatchStore, error) {
	return newStoreFromEnvironment("SC_REVIEW_S3")
}

func newStoreFromEnvironment(prefix string) (*PatchStore, error) {
	storeConfig, err := configFromEnvironment(prefix)
	if err != nil {
		return nil, err
	}
	client, err := newS3Client(storeConfig)
	if err != nil {
		return nil, err
	}
	return &PatchStore{client: client}, nil
}

func (s *PatchStore) DescribePatchObject(ctx context.Context, bucket, key string) (legacyrangezip.ObjectRevision, error) {
	if s == nil || s.client == nil {
		return legacyrangezip.ObjectRevision{}, fmt.Errorf("patch object store is not configured")
	}
	head, err := s.client.HeadObject(ctx, &s3.HeadObjectInput{Bucket: aws.String(bucket), Key: aws.String(key)})
	if err != nil {
		return legacyrangezip.ObjectRevision{}, fmt.Errorf("head patch object: %w", err)
	}
	revision, err := sourceRevision(head)
	if err != nil {
		return legacyrangezip.ObjectRevision{}, err
	}
	return legacyrangezip.ObjectRevision{Revision: revision, Size: aws.ToInt64(head.ContentLength)}, nil
}

func (s *PatchStore) DownloadPatchObject(ctx context.Context, bucket, key, destination string) (resultErr error) {
	if s == nil || s.client == nil {
		return fmt.Errorf("patch object store is not configured")
	}
	response, err := s.client.GetObject(ctx, &s3.GetObjectInput{Bucket: aws.String(bucket), Key: aws.String(key)})
	if err != nil {
		return fmt.Errorf("get patch object: %w", err)
	}
	defer func() {
		if err := response.Body.Close(); err != nil {
			resultErr = errors.Join(resultErr, fmt.Errorf("close patch object: %w", err))
		}
	}()
	file, err := os.OpenFile(destination, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return fmt.Errorf("create downloaded patch object: %w", err)
	}
	defer func() {
		if err := file.Close(); err != nil {
			resultErr = errors.Join(resultErr, fmt.Errorf("close downloaded patch object: %w", err))
		}
		if resultErr != nil {
			_ = os.Remove(destination)
		}
	}()
	buffer := make([]byte, 256*1024)
	if _, err := io.CopyBuffer(file, response.Body, buffer); err != nil {
		return fmt.Errorf("stream patch object: %w", err)
	}
	if err := file.Sync(); err != nil {
		return fmt.Errorf("sync downloaded patch object: %w", err)
	}
	return nil
}

func sourceRevision(head *s3.HeadObjectOutput) (string, error) {
	if head == nil {
		return "", fmt.Errorf("patch object metadata is required")
	}
	if version := strings.TrimSpace(aws.ToString(head.VersionId)); version != "" {
		return "version:" + version, nil
	}
	if etag := strings.Trim(strings.TrimSpace(aws.ToString(head.ETag)), "\""); etag != "" {
		return "etag:" + etag, nil
	}
	if head.LastModified != nil && head.ContentLength != nil && *head.ContentLength >= 0 {
		return fmt.Sprintf("mtime-size:%d:%d", head.LastModified.UnixNano(), *head.ContentLength), nil
	}
	return "", fmt.Errorf("patch object has no reliable source revision")
}

type storeConfig struct {
	endpoint  string
	region    string
	accessKey string
	secretKey string
}

func configFromEnvironment(prefix string) (storeConfig, error) {
	endpoint := firstEnvironment(prefix+"_ENDPOINT", "MINIO_ENDPOINT")
	if endpoint == "" {
		return storeConfig{}, fmt.Errorf("%s_ENDPOINT or MINIO_ENDPOINT is required", prefix)
	}
	if !strings.Contains(endpoint, "://") {
		endpoint = "http://" + endpoint
	}
	region := firstEnvironment(prefix+"_REGION", "MINIO_REGION")
	if region == "" {
		return storeConfig{}, fmt.Errorf("%s_REGION or MINIO_REGION is required", prefix)
	}
	accessKey := firstEnvironment(prefix+"_ACCESS_KEY", "MINIO_ACCESS_KEY")
	if accessKey == "" {
		return storeConfig{}, fmt.Errorf("%s_ACCESS_KEY or MINIO_ACCESS_KEY is required", prefix)
	}
	secretKey := firstEnvironment(prefix+"_SECRET_KEY", "MINIO_SECRET_KEY")
	if secretKey == "" {
		return storeConfig{}, fmt.Errorf("%s_SECRET_KEY or MINIO_SECRET_KEY is required", prefix)
	}
	return storeConfig{endpoint: endpoint, region: region, accessKey: accessKey, secretKey: secretKey}, nil
}

func firstEnvironment(names ...string) string {
	for _, name := range names {
		if value := strings.TrimSpace(os.Getenv(name)); value != "" {
			return value
		}
	}
	return ""
}

func newS3Client(source storeConfig) (*s3.Client, error) {
	transport := &http.Transport{
		MaxIdleConns:        128,
		MaxIdleConnsPerHost: 128,
		IdleConnTimeout:     90 * time.Second,
	}
	resolver := aws.EndpointResolverWithOptionsFunc(func(service, region string, options ...interface{}) (aws.Endpoint, error) {
		return aws.Endpoint{URL: source.endpoint, HostnameImmutable: true, SigningRegion: source.region}, nil
	})
	configuration, err := config.LoadDefaultConfig(
		context.Background(),
		config.WithRegion(source.region),
		config.WithCredentialsProvider(credentials.NewStaticCredentialsProvider(source.accessKey, source.secretKey, "")),
		config.WithHTTPClient(&http.Client{Transport: transport}),
		config.WithEndpointResolverWithOptions(resolver),
	)
	if err != nil {
		return nil, fmt.Errorf("configure patch object store: %w", err)
	}
	return s3.NewFromConfig(configuration, func(options *s3.Options) {
		options.UsePathStyle = true
	}), nil
}

var _ legacyrangezip.ObjectStore = (*PatchStore)(nil)
