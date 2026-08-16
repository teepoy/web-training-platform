package image_loader

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	PatchProviderScUpstream     = "sc_upstream"
	PatchProviderScZipFolder    = "sc_patch_zip_folder"
	patchInspectionFolderLayout = "20060102_150405"
)

type PatchArchive struct {
	CacheKey string
	Bucket   string
	Key      string
	Path     string
}

type PatchArchiveProvider interface {
	ResolveArchives(ctx context.Context, inspection InspectionKey, zipIndexes []int) (map[int]PatchArchive, error)
	LoadArchive(ctx context.Context, archive PatchArchive) ([]byte, error)
}

type PatchArchiveProviderRegistry struct {
	profiles map[string]PatchArchiveProvider
}

func NewPatchArchiveProviderRegistry(profiles map[string]PatchArchiveProvider) (*PatchArchiveProviderRegistry, error) {
	if len(profiles) == 0 {
		return nil, fmt.Errorf("at least one image source profile is required")
	}
	copyProfiles := make(map[string]PatchArchiveProvider, len(profiles))
	for rawName, provider := range profiles {
		name := strings.TrimSpace(rawName)
		if name == "" {
			return nil, fmt.Errorf("image source profile name cannot be empty")
		}
		if provider == nil {
			return nil, fmt.Errorf("image source profile %q has no provider", name)
		}
		if _, exists := copyProfiles[name]; exists {
			return nil, fmt.Errorf("duplicate image source profile %q", name)
		}
		copyProfiles[name] = provider
	}
	return &PatchArchiveProviderRegistry{profiles: copyProfiles}, nil
}

func (r *PatchArchiveProviderRegistry) Get(profile string) (PatchArchiveProvider, error) {
	provider, ok := r.profiles[strings.TrimSpace(profile)]
	if !ok {
		return nil, fmt.Errorf("unknown image source profile %q", profile)
	}
	return provider, nil
}

type upstreamPatchArchiveProvider struct {
	upstream UpstreamSource
	loader   objectLoader
}

func newUpstreamPatchArchiveProvider(upstream UpstreamSource, loader objectLoader) PatchArchiveProvider {
	return &upstreamPatchArchiveProvider{upstream: upstream, loader: loader}
}

func (p *upstreamPatchArchiveProvider) ResolveArchives(ctx context.Context, inspection InspectionKey, zipIndexes []int) (map[int]PatchArchive, error) {
	meta, err := p.upstream.GetInspection(ctx, inspection.InspectionTime, int32(inspection.WaferKey))
	if err != nil {
		return nil, fmt.Errorf("resolve inspection metadata: %w", err)
	}
	zips, err := p.upstream.GetInspectionPatchZips(ctx, inspection.InspectionTime, meta.LotId, meta.WaferId, meta.Device, meta.LayerId)
	if err != nil {
		return nil, fmt.Errorf("resolve patch archives: %w", err)
	}
	resolved := make(map[int]PatchArchive, len(zipIndexes))
	for _, zipIndex := range uniqueSortedIndexes(zipIndexes) {
		if zipIndex < 0 || zipIndex >= len(zips.Zips) {
			continue
		}
		ref := zips.Zips[zipIndex]
		resolved[zipIndex] = PatchArchive{
			CacheKey: ref.S3Bucket + "\x00" + ref.S3Key,
			Bucket:   ref.S3Bucket,
			Key:      ref.S3Key,
		}
	}
	return resolved, nil
}

func (p *upstreamPatchArchiveProvider) LoadArchive(ctx context.Context, archive PatchArchive) ([]byte, error) {
	return p.loader.LoadPatchZip(ctx, archive.Bucket, archive.Key)
}

type folderPatchArchiveProvider struct {
	root string
}

func NewFolderPatchArchiveProvider(root string) (PatchArchiveProvider, error) {
	if !filepath.IsAbs(root) {
		return nil, fmt.Errorf("folder provider root must be absolute")
	}
	resolvedRoot, err := filepath.EvalSymlinks(filepath.Clean(root))
	if err != nil {
		return nil, fmt.Errorf("resolve folder provider root: %w", err)
	}
	info, err := os.Stat(resolvedRoot)
	if err != nil {
		return nil, fmt.Errorf("stat folder provider root: %w", err)
	}
	if !info.IsDir() {
		return nil, fmt.Errorf("folder provider root is not a directory")
	}
	return &folderPatchArchiveProvider{root: resolvedRoot}, nil
}

func (p *folderPatchArchiveProvider) ResolveArchives(_ context.Context, inspection InspectionKey, zipIndexes []int) (map[int]PatchArchive, error) {
	folder, err := inspectionFolder(inspection.InspectionTime)
	if err != nil {
		return nil, err
	}
	if inspection.WaferKey <= 0 {
		return nil, fmt.Errorf("wafer_key must be greater than zero")
	}
	waferFolder := strconv.Itoa(inspection.WaferKey)
	resolved := make(map[int]PatchArchive, len(zipIndexes))
	for _, zipIndex := range uniqueSortedIndexes(zipIndexes) {
		if zipIndex < 0 {
			return nil, fmt.Errorf("patch archive index cannot be negative")
		}
		start := zipIndex*defectsPerZip + 1
		end := start + defectsPerZip - 1
		relative := filepath.Join(folder, waferFolder, fmt.Sprintf("%06d-%06d.zip", start, end))
		path, err := secureJoinedPath(p.root, relative)
		if err != nil {
			return nil, err
		}
		resolved[zipIndex] = PatchArchive{
			CacheKey: "folder\x00" + path,
			Path:     path,
		}
	}
	return resolved, nil
}

func (p *folderPatchArchiveProvider) LoadArchive(ctx context.Context, archive PatchArchive) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	path, err := secureExistingPath(p.root, archive.Path)
	if err != nil {
		return nil, err
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	return data, nil
}

func inspectionFolder(raw string) (string, error) {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return "", fmt.Errorf("inspection_time is required")
	}
	if parsed, err := time.Parse(patchInspectionFolderLayout, trimmed); err == nil {
		return parsed.Format(patchInspectionFolderLayout), nil
	}
	parsed, err := time.Parse(time.RFC3339Nano, trimmed)
	if err != nil {
		return "", fmt.Errorf("inspection_time must be RFC3339 or YYYYMMDD_HHMMSS: %w", err)
	}
	return parsed.Format(patchInspectionFolderLayout), nil
}

func secureJoinedPath(root, relative string) (string, error) {
	if filepath.IsAbs(relative) {
		return "", fmt.Errorf("archive path must be relative")
	}
	joined := filepath.Clean(filepath.Join(root, relative))
	inside, err := pathWithinRoot(root, joined)
	if err != nil {
		return "", err
	}
	if !inside {
		return "", fmt.Errorf("archive path escapes configured root")
	}
	return joined, nil
}

func secureExistingPath(root, candidate string) (string, error) {
	inside, err := pathWithinRoot(root, candidate)
	if err != nil {
		return "", err
	}
	if !inside {
		return "", fmt.Errorf("archive path escapes configured root")
	}
	resolved, err := filepath.EvalSymlinks(candidate)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return "", fmt.Errorf("patch archive not found: %w", err)
		}
		return "", fmt.Errorf("resolve patch archive: %w", err)
	}
	inside, err = pathWithinRoot(root, resolved)
	if err != nil {
		return "", err
	}
	if !inside {
		return "", fmt.Errorf("patch archive symlink escapes configured root")
	}
	return resolved, nil
}

func pathWithinRoot(root, candidate string) (bool, error) {
	relative, err := filepath.Rel(root, candidate)
	if err != nil {
		return false, fmt.Errorf("compare archive path with configured root: %w", err)
	}
	return relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator)), nil
}

func uniqueSortedIndexes(values []int) []int {
	seen := make(map[int]struct{}, len(values))
	for _, value := range values {
		seen[value] = struct{}{}
	}
	result := make([]int, 0, len(seen))
	for value := range seen {
		result = append(result, value)
	}
	sort.Ints(result)
	return result
}
