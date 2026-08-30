package artifactsource

import (
	"context"
	"errors"
	"fmt"
	"os"

	"image-parser/internal/artifactcache"
)

// CachedReader adapts a remote artifact source to the shared cache used by
// display image resolution.
type CachedReader struct {
	source  Source
	cache   artifactcache.Cache
	entryID string
}

type Revision struct {
	Identity string
	Revision string
	Size     int64
}

type Source interface {
	Describe(ctx context.Context, sourceRef string) (Revision, error)
	Download(ctx context.Context, sourceRef, destination string) error
}

func NewCachedReader(source Source, cache artifactcache.Cache, entryID string) (*CachedReader, error) {
	if source == nil || cache == nil || entryID == "" {
		return nil, fmt.Errorf("cached artifact reader requires source, cache, and entry ID")
	}
	return &CachedReader{source: source, cache: cache, entryID: entryID}, nil
}

func (r *CachedReader) Read(ctx context.Context, sourceRef string) (data []byte, resultErr error) {
	revision, err := r.source.Describe(ctx, sourceRef)
	if err != nil {
		return nil, err
	}
	lease, err := r.cache.Acquire(ctx, artifactcache.Ref{
		EntryID: r.entryID, SourceIdentity: revision.Identity,
		Revision: revision.Revision, Kind: artifactcache.KindFile,
	}, func(ctx context.Context, destination string) error {
		return r.source.Download(ctx, sourceRef, destination)
	})
	if err != nil {
		return nil, err
	}
	defer func() {
		resultErr = errors.Join(resultErr, lease.Release())
	}()
	data, err = os.ReadFile(lease.Path())
	if err != nil {
		return nil, fmt.Errorf("read cached artifact: %w", err)
	}
	return data, nil
}
