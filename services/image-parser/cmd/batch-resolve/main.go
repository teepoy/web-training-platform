package main

import (
	"context"
	"fmt"
	"io"
	"os"

	"image-parser/internal/frameprotocol"
	imageloader "image-parser/internal/image_loader"
)

func run(ctx context.Context, input io.Reader, output io.Writer, images imageloader.ImageLoader) error {
	return frameprotocol.Run(ctx, input, output, images)
}

func main() {
	images, closeImages, err := initializeImageLoader()
	if err != nil {
		_, _ = fmt.Fprintf(os.Stderr, "initialize job image resolver: %v\n", err)
		os.Exit(1)
	}
	defer closeImages()
	if err := run(context.Background(), os.Stdin, os.Stdout, images); err != nil {
		_, _ = fmt.Fprintf(os.Stderr, "job image resolver failed: %v\n", err)
		os.Exit(1)
	}
}
