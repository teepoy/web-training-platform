package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"image-parser/internal/filesource"
	imageloader "image-parser/internal/image_loader"
)

func initializeImageLoader() (imageloader.ImageLoader, func(), error) {
	root := strings.TrimSpace(os.Getenv("IMAGE_SOURCE_ROOT"))
	if root == "" {
		return nil, nil, fmt.Errorf("IMAGE_SOURCE_ROOT is required")
	}
	if !filepath.IsAbs(root) {
		return nil, nil, fmt.Errorf("IMAGE_SOURCE_ROOT must be absolute")
	}
	format := strings.TrimSpace(os.Getenv("IMAGE_SOURCE_FORMAT"))
	if format == "" {
		return nil, nil, fmt.Errorf("IMAGE_SOURCE_FORMAT is required")
	}
	kind := filesource.Kind(strings.TrimSpace(os.Getenv("IMAGE_SOURCE_KIND")))
	if kind == "" {
		kind = filesource.KindDirectory
	}
	return imageloader.Initialize(imageloader.Options{
		PatchSource: imageloader.PatchSourceConfig{
			Format:    format,
			Root:      root,
			Kind:      kind,
			Ownership: filesource.OwnershipBorrowed,
			Stager:    imageloader.PatchSourceStagerNone,
		},
	})
}
