// Package directfiles resolves role-to-path mappings without assuming a
// directory layout or container format.
package directfiles

import (
	"context"
	"fmt"
	"mime"
	"path/filepath"

	"image-parser/internal/filesource"
	"image-parser/internal/sourceformat"
)

const FormatID = "filesystem.role-paths.v1"

type Driver struct{}

func (Driver) Format() string { return FormatID }

func (Driver) Resolve(ctx context.Context, source *filesource.Source, requests []sourceformat.Request) []sourceformat.Result {
	results := make([]sourceformat.Result, 0)
	for _, request := range requests {
		for _, role := range request.Roles {
			result := sourceformat.Result{
				RequestID: request.RequestID,
				SampleID:  request.SampleID,
				Role:      role,
			}
			if err := ctx.Err(); err != nil {
				result.Err = err
				results = append(results, result)
				continue
			}
			path, ok := request.RolePaths[role]
			if !ok {
				result.Err = fmt.Errorf("role %q has no explicit source path", role)
				results = append(results, result)
				continue
			}
			data, err := source.ReadFile(path)
			if err != nil {
				result.Err = fmt.Errorf("read role %q: %w", role, err)
				results = append(results, result)
				continue
			}
			result.Data = data
			result.ContentType = mime.TypeByExtension(filepath.Ext(path))
			if result.ContentType == "" {
				result.ContentType = "application/octet-stream"
			}
			results = append(results, result)
		}
	}
	return results
}
