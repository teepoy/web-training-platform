package main

import (
	"context"
	"fmt"
	"os"

	"image-parser/internal/frameprotocol"
)

func main() {
	images, closeImages, err := initializeImageLoader()
	if err != nil {
		_, _ = fmt.Fprintf(os.Stderr, "initialize local image resolver: %v\n", err)
		os.Exit(1)
	}
	defer closeImages()
	if err := frameprotocol.Run(context.Background(), os.Stdin, os.Stdout, images); err != nil {
		_, _ = fmt.Fprintf(os.Stderr, "local image resolver failed: %v\n", err)
		os.Exit(1)
	}
}
