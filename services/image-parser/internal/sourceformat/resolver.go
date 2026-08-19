// Package sourceformat defines the shared contract between a filesystem source
// and a format-specific asset resolver. It deliberately knows nothing about
// ZIP files, defect indexes, remote object stores, or cache policy.
package sourceformat

import (
	"context"
	"fmt"
	"strings"

	"image-parser/internal/filesource"
)

type Request struct {
	RequestID string
	SampleID  string
	Roles     []string
	Fields    map[string]string
	RolePaths map[string]string
}

type Result struct {
	RequestID   string
	SampleID    string
	Role        string
	Data        []byte
	ContentType string
	Err         error
}

type Driver interface {
	Format() string
	Resolve(ctx context.Context, source *filesource.Source, requests []Request) []Result
}

// Stager is optional. If installed by an entrypoint it must make the requested
// source objects visible below source.Path before Driver.Resolve runs.
type Stager interface {
	Stage(ctx context.Context, source *filesource.Source, requests []Request) error
}

type Resolver struct {
	source *filesource.Source
	driver Driver
	stager Stager
}

func NewResolver(source *filesource.Source, driver Driver, stager Stager) (*Resolver, error) {
	if source == nil {
		return nil, fmt.Errorf("filesystem source is required")
	}
	if driver == nil {
		return nil, fmt.Errorf("source format driver is required")
	}
	if strings.TrimSpace(driver.Format()) == "" {
		return nil, fmt.Errorf("source format driver ID is required")
	}
	return &Resolver{source: source, driver: driver, stager: stager}, nil
}

func (r *Resolver) Format() string { return r.driver.Format() }

func (r *Resolver) Resolve(ctx context.Context, format string, requests []Request) ([]Result, error) {
	if strings.TrimSpace(format) != r.driver.Format() {
		return nil, fmt.Errorf("source format %q is not available; configured format is %q", format, r.driver.Format())
	}
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if r.stager != nil {
		if err := r.stager.Stage(ctx, r.source, requests); err != nil {
			return nil, fmt.Errorf("stage source: %w", err)
		}
	}
	return r.driver.Resolve(ctx, r.source, requests), nil
}
