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
	"image-parser/internal/artifactcache"
	"image-parser/internal/client"
	"image-parser/internal/display"
	"image-parser/internal/equipment"
	equipmentlegacy "image-parser/internal/equipment/legacyrangezip"
	"image-parser/internal/handler"
	"image-parser/internal/imagestream"
	"image-parser/internal/metrics"

	"github.com/gin-gonic/gin"
	"google.golang.org/grpc"

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

	patchArchives, err := newPatchArchiveSource()
	if err != nil {
		_ = upstream.Close()
		log.Fatalf("failed to init patch archive source: %v", err)
	}
	streamCaches := make(map[imagestream.UseCase]*artifactcache.Manager, 4)
	for _, useCase := range []imagestream.UseCase{imagestream.UseCaseDisplay, imagestream.UseCasePrediction, imagestream.UseCaseTraining, imagestream.UseCaseExport} {
		cacheOptions, err := artifactCacheOptions(useCase, artifactcache.Options{
			TTL: *cacheTTL, CleanupInterval: *cacheCleanupInterval, MaxBytes: *cacheMaxBytes,
		})
		if err != nil {
			log.Fatalf("invalid %s artifact cache configuration: %v", useCase, err)
		}
		manager, err := artifactcache.New(filepath.Join(*cacheDir, string(useCase)), cacheOptions)
		if err != nil {
			for _, opened := range streamCaches {
				opened.Close()
			}
			_ = upstream.Close()
			log.Fatalf("failed to init %s image artifact cache: %v", useCase, err)
		}
		streamCaches[useCase] = manager
		metrics.RegisterArtifactCache(string(useCase), manager)
	}
	legacyFactory, err := equipmentlegacy.NewFactory(upstream, patchArchives, 128)
	if err != nil {
		log.Fatalf("failed to init legacy range-ZIP image entry: %v", err)
	}
	registry, err := equipment.NewRegistry([]equipment.Registration{{
		EquipmentIDs: equipmentlegacy.DefaultEquipmentIDs,
		Factory:      legacyFactory,
	}})
	if err != nil {
		log.Fatalf("failed to init equipment image registry: %v", err)
	}
	caches := make(map[imagestream.UseCase]artifactcache.Cache, len(streamCaches))
	for useCase, manager := range streamCaches {
		caches[useCase] = manager
	}
	streamEngine, err := equipment.NewEngine(upstream, registry, caches, equipment.LimitsByUseCase{
		Display:    imagestream.Limits{MaxBatchItems: 512, MaxResponseBytes: 64 << 20, MaxActiveContexts: 32, MaxInFlightBatches: 1},
		Prediction: imagestream.Limits{MaxBatchItems: 512, MaxResponseBytes: 64 << 20, MaxActiveContexts: 32, MaxInFlightBatches: 2},
		Training:   imagestream.Limits{MaxBatchItems: 512, MaxResponseBytes: 64 << 20, MaxActiveContexts: 32, MaxInFlightBatches: 1},
		Export:     imagestream.Limits{MaxBatchItems: 512, MaxResponseBytes: 64 << 20, MaxActiveContexts: 32, MaxInFlightBatches: 1},
	})
	if err != nil {
		log.Fatalf("failed to init image stream engine: %v", err)
	}
	limiter, err := imagestream.NewFairLimiter(imagestream.GovernorConfig{
		GlobalConcurrency: 16,
		PerUseCase: map[imagestream.UseCase]int{
			imagestream.UseCaseDisplay: 8, imagestream.UseCasePrediction: 12,
			imagestream.UseCaseTraining: 2, imagestream.UseCaseExport: 4,
		},
		Weights: map[imagestream.UseCase]int{
			imagestream.UseCaseDisplay: 2, imagestream.UseCasePrediction: 6,
			imagestream.UseCaseTraining: 1, imagestream.UseCaseExport: 2,
		},
	})
	if err != nil {
		log.Fatalf("failed to init image stream fair limiter: %v", err)
	}
	governedEngine, err := imagestream.NewGovernedEngine(streamEngine, limiter)
	if err != nil {
		log.Fatalf("failed to init governed image stream engine: %v", err)
	}
	reviewImages, err := newReviewImageSource(streamCaches[imagestream.UseCaseDisplay])
	if err != nil {
		log.Fatalf("failed to init review image source: %v", err)
	}
	displayReader, err := display.New(upstream, reviewImages, governedEngine)
	if err != nil {
		_ = upstream.Close()
		for _, manager := range streamCaches {
			manager.Close()
		}
		log.Fatalf("failed to init display image reader: %v", err)
	}
	exportReviewImages, err := newReviewImageSource(streamCaches[imagestream.UseCaseExport])
	if err != nil {
		log.Fatalf("failed to init export review image source: %v", err)
	}
	exportReader, err := display.NewForUseCase(upstream, exportReviewImages, governedEngine, imagestream.UseCaseExport)
	if err != nil {
		log.Fatalf("failed to init export image reader: %v", err)
	}
	downloadRoot := filepath.Join(*cacheDir, "gallery-downloads")
	if err := os.MkdirAll(downloadRoot, 0o700); err != nil {
		log.Fatalf("failed to init gallery download root: %v", err)
	}
	downloadTempDir, err := os.MkdirTemp(downloadRoot, "instance-")
	if err != nil {
		log.Fatalf("failed to init gallery download temp directory: %v", err)
	}
	downloads, err := handler.NewGalleryDownloadService(exportReader, upstream, downloadTempDir)
	if err != nil {
		_ = os.RemoveAll(downloadTempDir)
		log.Fatalf("failed to init gallery downloads: %v", err)
	}

	var httpHandler HTTPHandler = handler.NewSCRoutesWithGalleryDownloadsAndProfiles(displayReader, downloads, streamEngine)
	var grpcHandler imageparserv1.ImageParserServer = service.NewScImageService(governedEngine)

	grpcLis, grpcAddress, removeSocket, err := listenGRPC()
	if err != nil {
		_ = upstream.Close()
		log.Fatalf("failed to listen gRPC: %v", err)
	}
	grpcServer := grpc.NewServer(
		grpc.MaxRecvMsgSize(72<<20),
		grpc.MaxSendMsgSize(72<<20),
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
	r.Use(handler.CORSMiddleware(), handler.StableRecovery(), metrics.GinTrafficMiddleware(), handler.SafeRequestLogger(), gin.Recovery())
	r.GET("/health", handler.Health)
	r.GET("/metrics", metrics.Handler)
	auth, err := handler.JWTAuthFromEnvironment()
	if err != nil {
		log.Fatalf("failed to configure image HTTP authentication: %v", err)
	}
	protected := r.Group("/")
	protected.Use(auth)
	RegisterHandler(protected, httpHandler)

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
			for _, manager := range streamCaches {
				manager.Close()
			}
			_ = os.RemoveAll(downloadTempDir)
		},
	}
}

func artifactCacheOptions(useCase imagestream.UseCase, base artifactcache.Options) (artifactcache.Options, error) {
	prefix := strings.ToUpper(string(useCase)) + "_CACHE_"
	if value := strings.TrimSpace(os.Getenv(prefix + "TTL")); value != "" {
		parsed, err := time.ParseDuration(value)
		if err != nil {
			return base, fmt.Errorf("%sTTL must be a Go duration: %w", prefix, err)
		}
		base.TTL = parsed
	}
	if value := strings.TrimSpace(os.Getenv(prefix + "CLEANUP_INTERVAL")); value != "" {
		parsed, err := time.ParseDuration(value)
		if err != nil {
			return base, fmt.Errorf("%sCLEANUP_INTERVAL must be a Go duration: %w", prefix, err)
		}
		base.CleanupInterval = parsed
	}
	if value := strings.TrimSpace(os.Getenv(prefix + "MAX_BYTES")); value != "" {
		parsed, err := strconv.ParseInt(value, 10, 64)
		if err != nil {
			return base, fmt.Errorf("%sMAX_BYTES must be an integer byte count: %w", prefix, err)
		}
		base.MaxBytes = parsed
	}
	return base, nil
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
