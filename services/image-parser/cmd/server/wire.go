package main

import (
	"flag"
	"log"
	"net"
	"os"
	"strconv"
	"time"

	imageparserv1 "image-parser/gen/go/imageparser/v1"
	"image-parser/internal/client"
	"image-parser/internal/handler"

	"github.com/gin-gonic/gin"
	"google.golang.org/grpc"

	imageloader "image-parser/internal/image_loader"
	"image-parser/internal/service"
)

type serverApp struct {
	router      *gin.Engine
	cacheSizeMB int
	s3MaxConns  int
	close       func()
}

func wire() *serverApp {
	cacheSizeMB := flag.Int("cache-size-mb", 1024, "LRU cache size in MB")
	s3MaxConns := flag.Int("s3-max-conns", 1000, "S3 HTTP max idle connections")
	flag.Parse()

	if v := os.Getenv("CACHE_SIZE_MB"); v != "" {
		*cacheSizeMB, _ = strconv.Atoi(v)
	}
	if v := os.Getenv("S3_MAX_CONNS"); v != "" {
		*s3MaxConns, _ = strconv.Atoi(v)
	}

	upstream, err := client.NewUpstreamClient()
	if err != nil {
		log.Fatalf("failed to init upstream client: %v", err)
	}

	imageLoader, closeImageLoader, err := imageloader.Initialize(imageloader.Options{
		Upstream:    upstream,
		CacheSizeMB: *cacheSizeMB,
		CacheTTL:    10 * time.Minute,
		S3MaxConns:  *s3MaxConns,
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
	grpcServer := grpc.NewServer()
	imageparserv1.RegisterImageParserServer(grpcServer, grpcHandler)
	go func() {
		log.Printf("gRPC server starting on :%s", grpcPort)
		if err := grpcServer.Serve(grpcLis); err != nil {
			log.Fatalf("gRPC server failed: %v", err)
		}
	}()

	r := gin.New()
	r.Use(handler.CORSMiddleware(), handler.StableRecovery(), gin.Logger(), gin.Recovery())
	r.GET("/health", handler.Health)
	RegisterHandler(&r.RouterGroup, httpHandler)

	return &serverApp{
		router:      r,
		cacheSizeMB: *cacheSizeMB,
		s3MaxConns:  *s3MaxConns,
		close: func() {
			grpcServer.GracefulStop()
			_ = upstream.Close()
			closeImageLoader()
		},
	}
}
