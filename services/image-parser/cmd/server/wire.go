package main

import (
	"flag"
	"fmt"
	"log"
	"net"
	"os"
	"strconv"
	"time"

	imageparserv1 "image-parser/gen/go/imageparser/v1"
	"image-parser/internal/client"
	"image-parser/internal/handler"
	"image-parser/internal/metrics"

	"github.com/gin-gonic/gin"
	"google.golang.org/grpc"

	imageloader "image-parser/internal/image_loader"
	"image-parser/internal/service"
)

type serverApp struct {
	router        *gin.Engine
	cacheSizeMB   int
	cacheDir      string
	cacheTTL      time.Duration
	cacheMaxBytes int64
	s3MaxConns    int
	close         func()
}

func wire() *serverApp {
	cacheSizeMB := flag.Int("cache-size-mb", 1024, "in-memory LRU cache size in MB")
	cacheDir := flag.String("cache-dir", "/tmp/image-parser-cache", "local file cache directory")
	cacheTTL := flag.Duration("cache-ttl", 10*time.Minute, "cache entry TTL since its last successful read")
	cacheCleanupInterval := flag.Duration("cache-cleanup-interval", 5*time.Minute, "full cache scan interval")
	cacheMaxBytes := flag.Int64("cache-max-bytes", 0, "optional cache size limit in bytes; zero disables the limit")
	s3MaxConns := flag.Int("s3-max-conns", 1000, "S3 HTTP max idle connections")
	flag.Parse()

	if err := applyEnvironment(
		cacheSizeMB,
		cacheDir,
		cacheTTL,
		cacheCleanupInterval,
		cacheMaxBytes,
		s3MaxConns,
	); err != nil {
		log.Fatalf("invalid image-parser configuration: %v", err)
	}

	upstream, err := client.NewUpstreamClient()
	if err != nil {
		log.Fatalf("failed to init upstream client: %v", err)
	}

	imageLoader, closeImageLoader, err := imageloader.Initialize(imageloader.Options{
		Upstream:             upstream,
		CacheSizeMB:          *cacheSizeMB,
		CacheDir:             *cacheDir,
		CacheTTL:             *cacheTTL,
		CacheCleanupInterval: *cacheCleanupInterval,
		CacheMaxBytes:        *cacheMaxBytes,
		S3MaxConns:           *s3MaxConns,
	})
	if err != nil {
		_ = upstream.Close()
		log.Fatalf("failed to init image loader: %v", err)
	}

	var httpHandler HTTPHandler = handler.NewSCRoutes(imageLoader)
	var grpcHandler imageparserv1.ImageParserServer = service.NewScImageService(imageLoader)

	grpcPort := os.Getenv("GRPC_PORT")
	if grpcPort == "" {
		grpcPort = "9092"
	}
	grpcLis, err := net.Listen("tcp", ":"+grpcPort)
	if err != nil {
		_ = upstream.Close()
		closeImageLoader()
		log.Fatalf("failed to listen gRPC: %v", err)
	}
	grpcServer := grpc.NewServer(
		grpc.UnaryInterceptor(metrics.GRPCUnaryInterceptor()),
		grpc.StreamInterceptor(metrics.GRPCStreamInterceptor()),
	)
	imageparserv1.RegisterImageParserServer(grpcServer, grpcHandler)
	go func() {
		log.Printf("gRPC server starting on :%s", grpcPort)
		if err := grpcServer.Serve(grpcLis); err != nil {
			log.Fatalf("gRPC server failed: %v", err)
		}
	}()

	r := gin.New()
	r.Use(handler.CORSMiddleware(), handler.StableRecovery(), metrics.GinTrafficMiddleware(), gin.Logger(), gin.Recovery())
	r.GET("/health", handler.Health)
	r.GET("/metrics", metrics.Handler)
	RegisterHandler(&r.RouterGroup, httpHandler)

	return &serverApp{
		router:        r,
		cacheSizeMB:   *cacheSizeMB,
		cacheDir:      *cacheDir,
		cacheTTL:      *cacheTTL,
		cacheMaxBytes: *cacheMaxBytes,
		s3MaxConns:    *s3MaxConns,
		close: func() {
			grpcServer.GracefulStop()
			_ = upstream.Close()
			closeImageLoader()
		},
	}
}

func applyEnvironment(
	cacheSizeMB *int,
	cacheDir *string,
	cacheTTL *time.Duration,
	cacheCleanupInterval *time.Duration,
	cacheMaxBytes *int64,
	s3MaxConns *int,
) error {
	if value := os.Getenv("CACHE_SIZE_MB"); value != "" {
		parsed, err := strconv.Atoi(value)
		if err != nil {
			return fmt.Errorf("CACHE_SIZE_MB must be an integer: %w", err)
		}
		*cacheSizeMB = parsed
	}
	if value := os.Getenv("CACHE_DIR"); value != "" {
		*cacheDir = value
	}
	if value := os.Getenv("CACHE_TTL"); value != "" {
		parsed, err := time.ParseDuration(value)
		if err != nil {
			return fmt.Errorf("CACHE_TTL must be a Go duration: %w", err)
		}
		*cacheTTL = parsed
	}
	if value := os.Getenv("CACHE_CLEANUP_INTERVAL"); value != "" {
		parsed, err := time.ParseDuration(value)
		if err != nil {
			return fmt.Errorf("CACHE_CLEANUP_INTERVAL must be a Go duration: %w", err)
		}
		*cacheCleanupInterval = parsed
	}
	if value := os.Getenv("CACHE_MAX_BYTES"); value != "" {
		parsed, err := strconv.ParseInt(value, 10, 64)
		if err != nil {
			return fmt.Errorf("CACHE_MAX_BYTES must be an integer byte count: %w", err)
		}
		*cacheMaxBytes = parsed
	}
	if value := os.Getenv("S3_MAX_CONNS"); value != "" {
		parsed, err := strconv.Atoi(value)
		if err != nil {
			return fmt.Errorf("S3_MAX_CONNS must be an integer: %w", err)
		}
		*s3MaxConns = parsed
	}
	return nil
}
