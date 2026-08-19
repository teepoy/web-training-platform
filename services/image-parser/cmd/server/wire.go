package main

import (
	"flag"
	"fmt"
	"log"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	imageparserv1 "image-parser/gen/go/imageparser/v1"
	"image-parser/internal/client"
	"image-parser/internal/filesource"
	"image-parser/internal/handler"
	"image-parser/internal/metrics"
	"image-parser/internal/sourceformat/legacyrangezip"

	"github.com/gin-gonic/gin"
	"google.golang.org/grpc"

	imageloader "image-parser/internal/image_loader"
	"image-parser/internal/service"
)

type serverApp struct {
	router        *gin.Engine
	cacheDir      string
	cacheTTL      time.Duration
	cacheMaxBytes int64
	close         func()
}

func wire() *serverApp {
	cacheDir := flag.String("cache-dir", "/tmp/image-parser-cache", "local file cache directory")
	cacheTTL := flag.Duration("cache-ttl", 10*time.Minute, "cache entry TTL since its last successful read")
	cacheCleanupInterval := flag.Duration("cache-cleanup-interval", 5*time.Minute, "full cache scan interval")
	cacheMaxBytes := flag.Int64("cache-max-bytes", 0, "optional cache size limit in bytes; zero disables the limit")
	flag.Parse()

	if err := applyEnvironment(
		cacheDir,
		cacheTTL,
		cacheCleanupInterval,
		cacheMaxBytes,
	); err != nil {
		log.Fatalf("invalid image-parser configuration: %v", err)
	}

	upstream, err := client.NewUpstreamClient()
	if err != nil {
		log.Fatalf("failed to init upstream client: %v", err)
	}

	imageLoader, closeImageLoader, err := imageloader.Initialize(imageloader.Options{
		Upstream:             upstream,
		CacheTTL:             *cacheTTL,
		CacheCleanupInterval: *cacheCleanupInterval,
		CacheMaxBytes:        *cacheMaxBytes,
		PatchSource: imageloader.PatchSourceConfig{
			Format:    legacyrangezip.FormatID,
			Root:      filepath.Join(*cacheDir, "patch-source"),
			Kind:      filesource.KindDirectory,
			Ownership: filesource.OwnershipSharedCache,
			Stager:    imageloader.PatchSourceStagerScUpstream,
		},
	})
	if err != nil {
		_ = upstream.Close()
		log.Fatalf("failed to init image loader: %v", err)
	}

	var httpHandler HTTPHandler = handler.NewSCRoutes(imageLoader)
	var grpcHandler imageparserv1.ImageParserServer = service.NewScImageService(imageLoader)

	grpcLis, grpcAddress, removeSocket, err := listenGRPC()
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
		log.Printf("gRPC server starting on %s", grpcAddress)
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
		cacheDir:      *cacheDir,
		cacheTTL:      *cacheTTL,
		cacheMaxBytes: *cacheMaxBytes,
		close: func() {
			grpcServer.GracefulStop()
			_ = grpcLis.Close()
			removeSocket()
			_ = upstream.Close()
			closeImageLoader()
		},
	}
}

func listenGRPC() (net.Listener, string, func(), error) {
	raw := strings.TrimSpace(os.Getenv("GRPC_LISTEN"))
	if raw == "" {
		port := os.Getenv("GRPC_PORT")
		if port == "" {
			port = "9092"
		}
		raw = "tcp://:" + port
	}
	if address, ok := strings.CutPrefix(raw, "tcp://"); ok {
		listener, err := net.Listen("tcp", address)
		return listener, raw, func() {}, err
	}
	if address, ok := strings.CutPrefix(raw, "unix://"); ok {
		if !filepath.IsAbs(address) {
			return nil, raw, func() {}, fmt.Errorf("unix socket path must be absolute")
		}
		if info, err := os.Lstat(address); err == nil {
			if info.Mode()&os.ModeSocket == 0 {
				return nil, raw, func() {}, fmt.Errorf("refusing to replace non-socket path %s", address)
			}
			if err := os.Remove(address); err != nil {
				return nil, raw, func() {}, fmt.Errorf("remove stale unix socket: %w", err)
			}
		} else if !os.IsNotExist(err) {
			return nil, raw, func() {}, fmt.Errorf("inspect unix socket: %w", err)
		}
		listener, err := net.Listen("unix", address)
		return listener, raw, func() { _ = os.Remove(address) }, err
	}
	return nil, raw, func() {}, fmt.Errorf("GRPC_LISTEN must use tcp:// or unix://")
}

func applyEnvironment(
	cacheDir *string,
	cacheTTL *time.Duration,
	cacheCleanupInterval *time.Duration,
	cacheMaxBytes *int64,
) error {
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
	return nil
}
