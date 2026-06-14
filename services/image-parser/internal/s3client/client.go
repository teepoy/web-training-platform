package s3client

import (
	"context"
	"net/http"
	"os"
	"sync"
	"sync/atomic"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

var (
	zipsClient   *s3.Client
	zipsOnce     sync.Once
	reviewClient *s3.Client
	reviewOnce   sync.Once
	MaxConns     int32 = 1000
)

func GetZips() *s3.Client {
	zipsOnce.Do(func() {
		zipsClient = newClient(
			envOrDefault("S3_ZIPS_ACCESS_KEY", os.Getenv("S3_ACCESS_KEY")),
			envOrDefault("S3_ZIPS_SECRET_KEY", os.Getenv("S3_SECRET_KEY")),
		)
	})
	return zipsClient
}

func GetReview() *s3.Client {
	reviewOnce.Do(func() {
		reviewClient = newClient(
			envOrDefault("S3_REVIEW_ACCESS_KEY", os.Getenv("S3_ACCESS_KEY")),
			envOrDefault("S3_REVIEW_SECRET_KEY", os.Getenv("S3_SECRET_KEY")),
		)
	})
	return reviewClient
}

func Get() *s3.Client { return GetZips() }

func newClient(accessKey, secretKey string) *s3.Client {
	maxConns := int(atomic.LoadInt32(&MaxConns))

	customTransport := &http.Transport{
		MaxIdleConns:        maxConns,
		MaxIdleConnsPerHost: maxConns,
		IdleConnTimeout:     90 * time.Second,
	}

	endpoint := envOrDefault("S3_ENDPOINT", "http://localhost:9000")
	region := envOrDefault("S3_REGION", "us-east-1")

	customResolver := aws.EndpointResolverWithOptionsFunc(func(service, region string, options ...interface{}) (aws.Endpoint, error) {
		return aws.Endpoint{
			URL:               endpoint,
			HostnameImmutable: true,
			SigningRegion:     region,
		}, nil
	})

	if accessKey == "" {
		accessKey = "minioadmin"
	}
	if secretKey == "" {
		secretKey = "minioadmin"
	}

	cfg, err := config.LoadDefaultConfig(context.TODO(),
		config.WithRegion(region),
		config.WithCredentialsProvider(credentials.NewStaticCredentialsProvider(accessKey, secretKey, "")),
		config.WithHTTPClient(&http.Client{
			Transport: customTransport,
		}),
		config.WithEndpointResolverWithOptions(customResolver),
	)
	if err != nil {
		panic("failed to load AWS config: " + err.Error())
	}

	usePathStyle := os.Getenv("S3_USE_PATH_STYLE") == "true"

	return s3.NewFromConfig(cfg, func(o *s3.Options) {
		o.UsePathStyle = usePathStyle
	})
}

func envOrDefault(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}
