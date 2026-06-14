package main

import (
	"flag"
	"log"
	"net"
	"os"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"google.golang.org/grpc"
	imageparserv1 "image-parser/gen/go/imageparser/v1"
	"image-parser/internal/auth"
	"image-parser/internal/cache"
	"image-parser/internal/client"
	"image-parser/internal/handler"
	"image-parser/internal/resolve"
	"image-parser/internal/s3client"
	"image-parser/internal/service"
)

func main() {
	cacheSizeMB := flag.Int("cache-size-mb", 1024, "LRU cache size in MB")
	s3MaxConns := flag.Int("s3-max-conns", 1000, "S3 HTTP max idle connections")
	flag.Parse()

	if v := os.Getenv("CACHE_SIZE_MB"); v != "" {
		*cacheSizeMB, _ = strconv.Atoi(v)
	}
	if v := os.Getenv("S3_MAX_CONNS"); v != "" {
		*s3MaxConns, _ = strconv.Atoi(v)
	}

	s3client.MaxConns = int32(*s3MaxConns)
	_ = s3client.GetZips()
	_ = s3client.GetReview()

	zipCache, err := cache.New(*cacheSizeMB, 10*time.Minute)
	if err != nil {
		log.Fatalf("failed to init zip cache: %v", err)
	}
	defer zipCache.Close()

	upstream, err := client.NewUpstreamClient()
	if err != nil {
		log.Fatalf("failed to init upstream client: %v", err)
	}
	defer upstream.Close()

	recordCache := cache.NewRecordCache()
	warmer := cache.NewWarmer(zipCache)

	svc := service.New(zipCache, recordCache, warmer, "")
	h := handler.New(svc)

	resolver := resolve.New(upstream, zipCache, warmer)
	scRoutes := handler.NewSCRoutes(resolver)

	scSvc := service.NewScImageService(resolver)

	grpcPort := os.Getenv("GRPC_PORT")
	if grpcPort == "" {
		grpcPort = "9092"
	}
	grpcLis, err := net.Listen("tcp", ":"+grpcPort)
	if err != nil {
		log.Fatalf("failed to listen gRPC: %v", err)
	}
	grpcServer := grpc.NewServer()
	imageparserv1.RegisterImageParserServer(grpcServer, scSvc)
	go func() {
		log.Printf("gRPC server starting on :%s", grpcPort)
		if err := grpcServer.Serve(grpcLis); err != nil {
			log.Fatalf("gRPC server failed: %v", err)
		}
	}()

	r := gin.New()
	r.Use(handler.CORSMiddleware(), handler.StableRecovery(), gin.Logger(), gin.Recovery())

	r.GET("/health", h.Health)

	scRoutes.Register(&r.RouterGroup)

	r.GET("/image", h.GetImage)
	r.GET("/sprite", h.Sprite)
	r.GET("/v2/sprite", h.HandleV2Sprite)

	protected := r.Group("/")
	protected.Use(auth.JWTAuth())
	protected.GET("/admin/health", h.Health)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	log.Printf("HTTP server starting on :%s (cache=%dMB, s3-conns=%d)", port, *cacheSizeMB, *s3MaxConns)
	if err := r.Run(":" + port); err != nil {
		log.Fatalf("HTTP server failed: %v", err)
	}
}
