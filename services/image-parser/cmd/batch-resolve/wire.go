package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"image-parser/internal/client"
	"image-parser/internal/filesource"
	imageloader "image-parser/internal/image_loader"
	"image-parser/internal/sourceformat/legacyrangezip"
)

const (
	defaultBatchCacheRoot = "/tmp/sc-job-image-resolver"
)

func initializeImageLoader() (imageloader.ImageLoader, func(), error) {
	upstream, err := client.NewUpstreamClient()
	if err != nil {
		return nil, nil, err
	}
	closeUpstream := func() { _ = upstream.Close() }

	cacheRoot := strings.TrimSpace(os.Getenv("SC_JOB_IMAGE_RESOLVER_CACHE_ROOT"))
	if cacheRoot == "" {
		cacheRoot = defaultBatchCacheRoot
	}
	if !filepath.IsAbs(cacheRoot) {
		closeUpstream()
		return nil, nil, fmt.Errorf("SC_JOB_IMAGE_RESOLVER_CACHE_ROOT must be absolute")
	}
	if err := os.MkdirAll(cacheRoot, 0o750); err != nil {
		closeUpstream()
		return nil, nil, fmt.Errorf("create job image resolver root: %w", err)
	}
	cacheDir, err := os.MkdirTemp(cacheRoot, "job-")
	if err != nil {
		closeUpstream()
		return nil, nil, fmt.Errorf("create job image resolver source: %w", err)
	}

	images, closeImages, err := imageloader.Initialize(imageloader.Options{
		Upstream: upstream,
		PatchSource: imageloader.PatchSourceConfig{
			Format:    legacyrangezip.FormatID,
			Root:      cacheDir,
			Kind:      filesource.KindDirectory,
			Ownership: filesource.OwnershipJobOwned,
			Stager:    imageloader.PatchSourceStagerScUpstream,
		},
	})
	if err != nil {
		_ = os.RemoveAll(cacheDir)
		closeUpstream()
		return nil, nil, err
	}
	return images, func() {
		closeImages()
		closeUpstream()
	}, nil
}
