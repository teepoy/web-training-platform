package image_loader

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"image-parser/internal/mocksource"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

func downloadObject(ctx context.Context, client *s3.Client, bucket, key string) ([]byte, error) {
	resp, err := client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return nil, fmt.Errorf("get object: %w", err)
	}
	defer resp.Body.Close()

	buffer := new(bytes.Buffer)
	if _, err := io.Copy(buffer, resp.Body); err != nil {
		return nil, fmt.Errorf("read object: %w", err)
	}
	return buffer.Bytes(), nil
}

var (
	zipsClient   *s3.Client
	zipsOnce     sync.Once
	reviewClient *s3.Client
	reviewOnce   sync.Once
)

func getZips() *s3.Client {
	zipsOnce.Do(func() {
		zipsClient = newObjectStoreClient(
			objectStoreConfigFromEnvironment("SC_PATCH_S3"),
		)
	})
	return zipsClient
}

func getReview() *s3.Client {
	reviewOnce.Do(func() {
		reviewClient = newObjectStoreClient(
			objectStoreConfigFromEnvironment("SC_REVIEW_S3"),
		)
	})
	return reviewClient
}

type objectStoreClientConfig struct {
	endpoint  string
	region    string
	accessKey string
	secretKey string
}

func objectStoreConfigFromEnvironment(prefix string) objectStoreClientConfig {
	endpoint := firstEnvironment(
		prefix+"_ENDPOINT",
		"MINIO_ENDPOINT",
	)
	if endpoint == "" {
		endpoint = mocksource.ObjectStoreEndpoint
	}
	if !strings.Contains(endpoint, "://") {
		endpoint = "http://" + endpoint
	}
	region := firstEnvironment(prefix+"_REGION", "MINIO_REGION")
	if region == "" {
		region = mocksource.ObjectStoreRegion
	}
	accessKey := firstEnvironment(prefix+"_ACCESS_KEY", "MINIO_ACCESS_KEY")
	if accessKey == "" {
		accessKey = mocksource.ObjectStoreAccessKey
	}
	secretKey := firstEnvironment(prefix+"_SECRET_KEY", "MINIO_SECRET_KEY")
	if secretKey == "" {
		secretKey = mocksource.ObjectStoreSecretKey
	}
	return objectStoreClientConfig{
		endpoint:  endpoint,
		region:    region,
		accessKey: accessKey,
		secretKey: secretKey,
	}
}

func firstEnvironment(names ...string) string {
	for _, name := range names {
		if value := strings.TrimSpace(os.Getenv(name)); value != "" {
			return value
		}
	}
	return ""
}

func newObjectStoreClient(source objectStoreClientConfig) *s3.Client {
	customTransport := &http.Transport{
		MaxIdleConns:        mocksource.ObjectStoreMaxConnections,
		MaxIdleConnsPerHost: mocksource.ObjectStoreMaxConnections,
		IdleConnTimeout:     90 * time.Second,
	}

	customResolver := aws.EndpointResolverWithOptionsFunc(func(service, region string, options ...interface{}) (aws.Endpoint, error) {
		return aws.Endpoint{
			URL:               source.endpoint,
			HostnameImmutable: true,
			SigningRegion:     source.region,
		}, nil
	})

	cfg, err := config.LoadDefaultConfig(context.TODO(),
		config.WithRegion(source.region),
		config.WithCredentialsProvider(credentials.NewStaticCredentialsProvider(
			source.accessKey,
			source.secretKey,
			"",
		)),
		config.WithHTTPClient(&http.Client{
			Transport: customTransport,
		}),
		config.WithEndpointResolverWithOptions(customResolver),
	)
	if err != nil {
		panic("failed to load AWS config: " + err.Error())
	}

	return s3.NewFromConfig(cfg, func(o *s3.Options) {
		o.UsePathStyle = mocksource.ObjectStoreUsePathStyle
	})
}
