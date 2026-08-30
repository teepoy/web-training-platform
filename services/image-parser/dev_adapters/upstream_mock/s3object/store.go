//go:build upstream_mock

// Package s3object implements the upstream mock's S3 object locator.
package s3object

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"image-parser/internal/artifactsource"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

type Store struct {
	client *s3.Client
}

func NewFromEnvironment() (*Store, error) {
	storeConfig, err := configFromEnvironment()
	if err != nil {
		return nil, err
	}
	client, err := newS3Client(storeConfig)
	if err != nil {
		return nil, err
	}
	return &Store{client: client}, nil
}

func (s *Store) Describe(ctx context.Context, sourceRef string) (artifactsource.Revision, error) {
	bucket, key, err := ObjectLocation(sourceRef)
	if err != nil {
		return artifactsource.Revision{}, err
	}
	if s == nil || s.client == nil {
		return artifactsource.Revision{}, fmt.Errorf("upstream mock S3 object store is not configured")
	}
	head, err := s.client.HeadObject(ctx, &s3.HeadObjectInput{Bucket: aws.String(bucket), Key: aws.String(key)})
	if err != nil {
		return artifactsource.Revision{}, fmt.Errorf("head upstream mock S3 object: %w", err)
	}
	revision, err := sourceRevision(head)
	if err != nil {
		return artifactsource.Revision{}, err
	}
	return artifactsource.Revision{
		Identity: "s3://" + bucket + "/" + key,
		Revision: revision,
		Size:     aws.ToInt64(head.ContentLength),
	}, nil
}

func (s *Store) Download(ctx context.Context, sourceRef, destination string) (resultErr error) {
	bucket, key, err := ObjectLocation(sourceRef)
	if err != nil {
		return err
	}
	if s == nil || s.client == nil {
		return fmt.Errorf("upstream mock S3 object store is not configured")
	}
	response, err := s.client.GetObject(ctx, &s3.GetObjectInput{Bucket: aws.String(bucket), Key: aws.String(key)})
	if err != nil {
		return fmt.Errorf("get upstream mock S3 object: %w", err)
	}
	defer func() {
		if err := response.Body.Close(); err != nil {
			resultErr = errors.Join(resultErr, fmt.Errorf("close upstream mock S3 object: %w", err))
		}
	}()
	file, err := os.OpenFile(destination, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return fmt.Errorf("create downloaded upstream mock S3 object: %w", err)
	}
	defer func() {
		if err := file.Close(); err != nil {
			resultErr = errors.Join(resultErr, fmt.Errorf("close downloaded upstream mock S3 object: %w", err))
		}
		if resultErr != nil {
			_ = os.Remove(destination)
		}
	}()
	buffer := make([]byte, 256*1024)
	if _, err := io.CopyBuffer(file, response.Body, buffer); err != nil {
		return fmt.Errorf("stream upstream mock S3 object: %w", err)
	}
	if err := file.Sync(); err != nil {
		return fmt.Errorf("sync downloaded upstream mock S3 object: %w", err)
	}
	return nil
}

func ObjectLocation(sourceRef string) (string, string, error) {
	value := strings.TrimSpace(sourceRef)
	withoutScheme, ok := strings.CutPrefix(value, "s3://")
	if !ok {
		return "", "", fmt.Errorf("upstream mock object reference must use s3://")
	}
	bucket, key, ok := strings.Cut(withoutScheme, "/")
	bucket = strings.TrimSpace(bucket)
	key = strings.TrimSpace(key)
	if !ok || bucket == "" || key == "" {
		return "", "", fmt.Errorf("upstream mock S3 object reference requires bucket and key")
	}
	return bucket, key, nil
}

func sourceRevision(head *s3.HeadObjectOutput) (string, error) {
	if head == nil {
		return "", fmt.Errorf("upstream mock S3 object metadata is required")
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
	return "", fmt.Errorf("upstream mock S3 object has no reliable source revision")
}

type storeConfig struct {
	endpoint  string
	region    string
	accessKey string
	secretKey string
}

func configFromEnvironment() (storeConfig, error) {
	endpoint := strings.TrimSpace(os.Getenv("UPSTREAM_MOCK_S3_ENDPOINT"))
	if endpoint == "" {
		return storeConfig{}, fmt.Errorf("UPSTREAM_MOCK_S3_ENDPOINT is required")
	}
	if !strings.Contains(endpoint, "://") {
		endpoint = "http://" + endpoint
	}
	region := strings.TrimSpace(os.Getenv("UPSTREAM_MOCK_S3_REGION"))
	if region == "" {
		return storeConfig{}, fmt.Errorf("UPSTREAM_MOCK_S3_REGION is required")
	}
	accessKey := strings.TrimSpace(os.Getenv("UPSTREAM_MOCK_S3_ACCESS_KEY"))
	if accessKey == "" {
		return storeConfig{}, fmt.Errorf("UPSTREAM_MOCK_S3_ACCESS_KEY is required")
	}
	secretKey := strings.TrimSpace(os.Getenv("UPSTREAM_MOCK_S3_SECRET_KEY"))
	if secretKey == "" {
		return storeConfig{}, fmt.Errorf("UPSTREAM_MOCK_S3_SECRET_KEY is required")
	}
	return storeConfig{endpoint: endpoint, region: region, accessKey: accessKey, secretKey: secretKey}, nil
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
		return nil, fmt.Errorf("configure upstream mock S3 object store: %w", err)
	}
	return s3.NewFromConfig(configuration, func(options *s3.Options) {
		options.UsePathStyle = true
	}), nil
}

var _ artifactsource.Source = (*Store)(nil)
