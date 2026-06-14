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
	client   *s3.Client
	once     sync.Once
	MaxConns int32 = 1000
)

func Get() *s3.Client {
	once.Do(func() {
		maxConns := int(atomic.LoadInt32(&MaxConns))

		customTransport := &http.Transport{
			MaxIdleConns:        maxConns,
			MaxIdleConnsPerHost: maxConns,
			IdleConnTimeout:     90 * time.Second,
		}

		endpoint := envOrDefault("S3_ENDPOINT", "http://localhost:9000")
		accessKey := envOrDefault("S3_ACCESS_KEY", "minioadmin")
		secretKey := envOrDefault("S3_SECRET_KEY", "minioadmin")
		region := envOrDefault("S3_REGION", "us-east-1")

		customResolver := aws.EndpointResolverWithOptionsFunc(func(service, region string, options ...interface{}) (aws.Endpoint, error) {
			return aws.Endpoint{
				URL:               endpoint,
				HostnameImmutable: true,
				SigningRegion:     region,
			}, nil
		})

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

		client = s3.NewFromConfig(cfg, func(o *s3.Options) {
			o.UsePathStyle = usePathStyle
		})
	})
	return client
}

func envOrDefault(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}
