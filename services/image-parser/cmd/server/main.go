package main

import (
	"log"
	"os"

	"image-parser/internal/handler"
)

func main() {
	app := wire()
	defer app.close()

	protected := app.router.Group("/")
	protected.Use(handler.JWTAuth())
	protected.GET("/admin/health", handler.Health)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	log.Printf("HTTP server starting on :%s (cache=%dMB, s3-conns=%d)", port, app.cacheSizeMB, app.s3MaxConns)
	if err := app.router.Run(":" + port); err != nil {
		log.Fatalf("HTTP server failed: %v", err)
	}
}
