package main

import (
	"log"
	"os"
)

func main() {
	app := wire()
	defer app.close()

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	log.Printf(
		"HTTP server starting on :%s (local-cache-dir=%s, local-cache-ttl=%s, local-cache-max-bytes=%d)",
		port,
		app.cacheDir,
		app.cacheTTL,
		app.cacheMaxBytes,
	)
	if err := app.router.Run(":" + port); err != nil {
		log.Fatalf("HTTP server failed: %v", err)
	}
}
