package image_loader

import (
	"context"
	"net/http"
	"sync"
	"time"

	"image-parser/internal/mocksource"

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
)

func getZips() *s3.Client {
	zipsOnce.Do(func() {
		zipsClient = newMockClient()
	})
	return zipsClient
}

func getReview() *s3.Client {
	reviewOnce.Do(func() {
		reviewClient = newMockClient()
	})
	return reviewClient
}

func newMockClient() *s3.Client {
	customTransport := &http.Transport{
		MaxIdleConns:        mocksource.ObjectStoreMaxConnections,
		MaxIdleConnsPerHost: mocksource.ObjectStoreMaxConnections,
		IdleConnTimeout:     90 * time.Second,
	}

	customResolver := aws.EndpointResolverWithOptionsFunc(func(service, region string, options ...interface{}) (aws.Endpoint, error) {
		return aws.Endpoint{
			URL:               mocksource.ObjectStoreEndpoint,
			HostnameImmutable: true,
			SigningRegion:     mocksource.ObjectStoreRegion,
		}, nil
	})

	cfg, err := config.LoadDefaultConfig(context.TODO(),
		config.WithRegion(mocksource.ObjectStoreRegion),
		config.WithCredentialsProvider(credentials.NewStaticCredentialsProvider(
			mocksource.ObjectStoreAccessKey,
			mocksource.ObjectStoreSecretKey,
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
