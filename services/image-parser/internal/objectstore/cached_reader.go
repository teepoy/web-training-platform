package objectstore

import (
	"context"
	"fmt"
	"os"

	"image-parser/internal/artifactcache"
)

// CachedReader adapts a source object store to the shared artifact cache used
// by display image resolution.
type CachedReader struct {
	store   *PatchStore
	cache   artifactcache.Cache
	entryID string
}

func NewCachedReader(store *PatchStore, cache artifactcache.Cache, entryID string) (*CachedReader, error) {
	if store == nil || cache == nil || entryID == "" {
		return nil, fmt.Errorf("cached object reader requires store, cache, and entry ID")
	}
	return &CachedReader{store: store, cache: cache, entryID: entryID}, nil
}

func (r *CachedReader) ReadObject(ctx context.Context, bucket, key string) ([]byte, error) {
	revision, err := r.store.DescribePatchObject(ctx, bucket, key)
	if err != nil {
		return nil, err
	}
	path, err := r.cache.GetOrDownload(ctx, artifactcache.Ref{
		EntryID: r.entryID, SourceIdentity: bucket + "/" + key,
		Revision: revision.Revision, Kind: artifactcache.KindFile,
	}, func(ctx context.Context, destination string) error {
		return r.store.DownloadPatchObject(ctx, bucket, key, destination)
	})
	if err != nil {
		return nil, err
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read cached object: %w", err)
	}
	return data, nil
}
