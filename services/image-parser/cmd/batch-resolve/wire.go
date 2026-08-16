package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"image-parser/internal/client"
	imageloader "image-parser/internal/image_loader"
)

const (
	defaultBatchCacheSizeMB = 256
	defaultBatchCacheRoot   = "/tmp/sc-training-image-parser"
)

func initializeImageLoader() (imageloader.ImageLoader, func(), error) {
	profiles, defaultProfile, err := batchPatchSourceProfiles()
	if err != nil {
		return nil, nil, err
	}

	var upstream imageloader.UpstreamSource
	closeUpstream := func() {}
	if profilesNeedUpstream(profiles) {
		upstreamClient, err := client.NewUpstreamClient()
		if err != nil {
			return nil, nil, err
		}
		upstream = upstreamClient
		closeUpstream = func() { _ = upstreamClient.Close() }
	}

	cacheSizeMB, err := positiveIntEnvironment("SC_TRAINING_IMAGE_PARSER_CACHE_SIZE_MB", defaultBatchCacheSizeMB)
	if err != nil {
		closeUpstream()
		return nil, nil, err
	}
	cacheRoot := strings.TrimSpace(os.Getenv("SC_TRAINING_IMAGE_PARSER_CACHE_ROOT"))
	if cacheRoot == "" {
		cacheRoot = defaultBatchCacheRoot
	}
	if !filepath.IsAbs(cacheRoot) {
		closeUpstream()
		return nil, nil, fmt.Errorf("SC_TRAINING_IMAGE_PARSER_CACHE_ROOT must be absolute")
	}
	if err := os.MkdirAll(cacheRoot, 0o750); err != nil {
		closeUpstream()
		return nil, nil, fmt.Errorf("create training image parser cache root: %w", err)
	}
	cacheDir, err := os.MkdirTemp(cacheRoot, "job-")
	if err != nil {
		closeUpstream()
		return nil, nil, fmt.Errorf("create training image parser cache: %w", err)
	}

	images, closeImages, err := imageloader.Initialize(imageloader.Options{
		Upstream:             upstream,
		CacheSizeMB:          cacheSizeMB,
		CacheDir:             cacheDir,
		CacheTTL:             30 * time.Minute,
		CacheCleanupInterval: 5 * time.Minute,
		PatchSourceProfiles:  profiles,
		DefaultPatchProfile:  defaultProfile,
	})
	if err != nil {
		_ = os.RemoveAll(cacheDir)
		closeUpstream()
		return nil, nil, err
	}
	return images, func() {
		closeImages()
		closeUpstream()
		_ = os.RemoveAll(cacheDir)
	}, nil
}

func batchPatchSourceProfiles() (map[string]imageloader.PatchSourceProfileConfig, string, error) {
	raw := strings.TrimSpace(os.Getenv("IMAGE_SOURCE_PROFILES_JSON"))
	if raw == "" {
		return nil, "", fmt.Errorf("IMAGE_SOURCE_PROFILES_JSON is required")
	}
	profiles := make(map[string]imageloader.PatchSourceProfileConfig)
	if err := json.Unmarshal([]byte(raw), &profiles); err != nil {
		return nil, "", fmt.Errorf("parse IMAGE_SOURCE_PROFILES_JSON: %w", err)
	}
	defaultProfile := strings.TrimSpace(os.Getenv("SC_COMPAT_IMAGE_SOURCE_PROFILE"))
	if defaultProfile == "" {
		return nil, "", fmt.Errorf("SC_COMPAT_IMAGE_SOURCE_PROFILE is required")
	}
	if _, ok := profiles[defaultProfile]; !ok {
		return nil, "", fmt.Errorf("SC_COMPAT_IMAGE_SOURCE_PROFILE %q is not configured", defaultProfile)
	}
	return profiles, defaultProfile, nil
}

func profilesNeedUpstream(profiles map[string]imageloader.PatchSourceProfileConfig) bool {
	for _, profile := range profiles {
		if profile.Provider == imageloader.PatchProviderScUpstream {
			return true
		}
	}
	return false
}

func positiveIntEnvironment(name string, fallback int) (int, error) {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback, nil
	}
	value, err := strconv.Atoi(raw)
	if err != nil || value <= 0 {
		return 0, fmt.Errorf("%s must be a positive integer", name)
	}
	return value, nil
}
