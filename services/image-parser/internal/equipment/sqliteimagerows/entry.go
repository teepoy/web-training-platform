// Package sqliteimagerows implements a fixed SQLite image-row equipment entry.
// The caller selects it only indirectly through the inspection equipment ID.
package sqliteimagerows

import (
	"context"
	"database/sql"
	"fmt"
	"net/url"
	"strings"

	"image-parser/internal/artifactcache"
	"image-parser/internal/equipment"
	"image-parser/internal/imagestream"

	_ "modernc.org/sqlite"
)

const (
	EntryID             = "sc.sqlite-image-rows.v1"
	maxQuerySampleIDs   = 400
	validationStatement = "SELECT sample_id, role, image_bytes, content_type FROM images LIMIT 0"
)

// Artifact is the immutable SQLite source selected for one inspection.
type Artifact struct {
	SourceIdentity string
	Revision       string
}

// Source owns inspection-to-artifact discovery and artifact download. The
// service-owned Artifact Cache Manager supplies the staging destination.
type Source interface {
	Describe(ctx context.Context, inspection equipment.Inspection) (Artifact, error)
	Download(ctx context.Context, artifact Artifact, destination string) error
}

type Factory struct {
	source Source
}

func NewFactory(source Source) *Factory {
	return &Factory{source: source}
}

func (f *Factory) Open(
	ctx context.Context,
	params equipment.OpenParams,
) (imagestream.Context, error) {
	if f == nil || f.source == nil {
		return nil, &imagestream.ContextError{
			Code: "entry_unavailable", Message: "SQLite image-row source is required",
		}
	}
	if params.Cache == nil {
		return nil, &imagestream.ContextError{
			Code: "cache_unavailable", Message: "SQLite image-row artifact cache is required",
		}
	}
	roles, err := normalizeRoles(params.Roles)
	if err != nil {
		return nil, &imagestream.ContextError{Code: "unsupported_roles", Message: err.Error()}
	}
	artifact, err := f.source.Describe(ctx, params.Inspection)
	if err != nil {
		return nil, &imagestream.ContextError{
			Code: "source_unavailable", Message: fmt.Sprintf("describe SQLite image artifact: %v", err),
		}
	}
	artifact.SourceIdentity = strings.TrimSpace(artifact.SourceIdentity)
	artifact.Revision = strings.TrimSpace(artifact.Revision)
	if artifact.SourceIdentity == "" || artifact.Revision == "" {
		return nil, &imagestream.ContextError{
			Code: "source_unavailable", Message: "SQLite image artifact requires source identity and revision",
		}
	}
	path, err := params.Cache.GetOrDownload(
		ctx,
		artifactcache.Ref{
			EntryID:        EntryID,
			SourceIdentity: artifact.SourceIdentity,
			Revision:       artifact.Revision,
			Kind:           artifactcache.KindFile,
		},
		func(ctx context.Context, destination string) error {
			return f.source.Download(ctx, artifact, destination)
		},
	)
	if err != nil {
		return nil, &imagestream.ContextError{
			Code: "source_unavailable", Message: fmt.Sprintf("cache SQLite image artifact: %v", err),
		}
	}
	database, err := openReadOnly(path)
	if err != nil {
		return nil, &imagestream.ContextError{
			Code: "parser_unavailable", Message: fmt.Sprintf("open SQLite image artifact: %v", err),
		}
	}
	return &entryContext{
		equipmentID: params.Inspection.EquipmentID,
		roles:       roles,
		database:    database,
	}, nil
}

type entryContext struct {
	equipmentID string
	roles       []string
	database    *sql.DB
}

func (c *entryContext) EquipmentID() string { return c.equipmentID }

func (c *entryContext) Resolve(
	ctx context.Context,
	requests []imagestream.SampleRequest,
) ([]imagestream.SampleResult, error) {
	results := make([]imagestream.SampleResult, len(requests))
	sampleIDs := make([]string, 0, len(requests))
	seenSampleIDs := make(map[string]struct{}, len(requests))
	for index, request := range requests {
		results[index] = imagestream.SampleResult{
			Sequence: request.Sequence,
			SampleID: request.SampleID,
			DefectID: request.DefectID,
			Images:   make([]imagestream.RoleResult, len(c.roles)),
		}
		for roleIndex, role := range c.roles {
			results[index].Images[roleIndex].Role = role
		}
		sampleID := strings.TrimSpace(request.SampleID)
		if sampleID == "" {
			for roleIndex := range results[index].Images {
				results[index].Images[roleIndex].Err = fmt.Errorf("sample_id is required")
			}
			continue
		}
		if _, exists := seenSampleIDs[sampleID]; !exists {
			seenSampleIDs[sampleID] = struct{}{}
			sampleIDs = append(sampleIDs, sampleID)
		}
	}

	resolved := make(map[imageKey]storedImage, len(sampleIDs)*len(c.roles))
	for start := 0; start < len(sampleIDs); start += maxQuerySampleIDs {
		end := min(start+maxQuerySampleIDs, len(sampleIDs))
		if err := c.readBatch(ctx, sampleIDs[start:end], resolved); err != nil {
			return nil, &imagestream.ContextError{
				Code: "parser_unavailable", Message: fmt.Sprintf("query SQLite image artifact: %v", err),
			}
		}
	}
	for resultIndex := range results {
		sampleID := strings.TrimSpace(results[resultIndex].SampleID)
		if sampleID == "" {
			continue
		}
		for roleIndex, role := range c.roles {
			image, exists := resolved[imageKey{sampleID: sampleID, role: role}]
			if !exists {
				results[resultIndex].Images[roleIndex].Err = fmt.Errorf(
					"image row not found for sample %q role %q", sampleID, role,
				)
				continue
			}
			results[resultIndex].Images[roleIndex].Data = image.data
			results[resultIndex].Images[roleIndex].ContentType = image.contentType
		}
	}
	return results, nil
}

func (c *entryContext) readBatch(
	ctx context.Context,
	sampleIDs []string,
	destination map[imageKey]storedImage,
) error {
	if len(sampleIDs) == 0 {
		return nil
	}
	arguments := make([]any, 0, len(sampleIDs)+len(c.roles))
	for _, sampleID := range sampleIDs {
		arguments = append(arguments, sampleID)
	}
	for _, role := range c.roles {
		arguments = append(arguments, role)
	}
	query := "SELECT sample_id, role, image_bytes, content_type FROM images WHERE sample_id IN (" +
		placeholders(len(sampleIDs)) + ") AND role IN (" + placeholders(len(c.roles)) + ")"
	rows, err := c.database.QueryContext(ctx, query, arguments...)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		var sampleID string
		var role string
		var data []byte
		var contentType string
		if err := rows.Scan(&sampleID, &role, &data, &contentType); err != nil {
			return err
		}
		key := imageKey{sampleID: sampleID, role: role}
		if _, exists := destination[key]; exists {
			return fmt.Errorf("duplicate image row for sample %q role %q", sampleID, role)
		}
		if strings.TrimSpace(contentType) == "" {
			return fmt.Errorf("empty content_type for sample %q role %q", sampleID, role)
		}
		destination[key] = storedImage{data: data, contentType: contentType}
	}
	return rows.Err()
}

func (c *entryContext) Close() error {
	if c == nil || c.database == nil {
		return nil
	}
	return c.database.Close()
}

type imageKey struct {
	sampleID string
	role     string
}

type storedImage struct {
	data        []byte
	contentType string
}

func openReadOnly(path string) (*sql.DB, error) {
	location := &url.URL{Scheme: "file", Path: path}
	query := location.Query()
	query.Set("mode", "ro")
	query.Set("immutable", "1")
	location.RawQuery = query.Encode()
	database, err := sql.Open("sqlite", location.String())
	if err != nil {
		return nil, err
	}
	database.SetMaxOpenConns(1)
	database.SetMaxIdleConns(1)
	if err := database.Ping(); err != nil {
		_ = database.Close()
		return nil, err
	}
	if _, err := database.Exec(validationStatement); err != nil {
		_ = database.Close()
		return nil, fmt.Errorf("validate images table: %w", err)
	}
	return database, nil
}

func normalizeRoles(rawRoles []string) ([]string, error) {
	roles := make([]string, len(rawRoles))
	seen := make(map[string]struct{}, len(rawRoles))
	for index, raw := range rawRoles {
		var role string
		switch strings.ToLower(strings.TrimSpace(raw)) {
		case "patch_template", "template", "reference":
			role = "patch_template"
		case "patch_defective", "defective":
			role = "patch_defective"
		case "patch_difference", "difference":
			role = "patch_difference"
		default:
			return nil, fmt.Errorf("unsupported SQLite image role %q", raw)
		}
		if _, exists := seen[role]; exists {
			return nil, fmt.Errorf("duplicate SQLite image role %q", role)
		}
		seen[role] = struct{}{}
		roles[index] = role
	}
	return roles, nil
}

func placeholders(count int) string {
	if count <= 0 {
		return "NULL"
	}
	return strings.TrimSuffix(strings.Repeat("?,", count), ",")
}

var _ equipment.Factory = (*Factory)(nil)
