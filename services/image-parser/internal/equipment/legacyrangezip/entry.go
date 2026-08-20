// Package legacyrangezip implements the fixed SC range-ZIP image entry used by
// explicitly registered equipment IDs.
package legacyrangezip

import (
	"archive/zip"
	"context"
	"fmt"
	"io"
	"mime"
	"path/filepath"
	"strconv"
	"strings"

	scv1 "image-parser/gen/go/sc/v1"
	"image-parser/internal/artifactcache"
	"image-parser/internal/equipment"
	"image-parser/internal/imagestream"
)

const (
	EntryID            = "sc.legacy-range-zip.v1"
	defectsPerArchive  = 500
	maxArchiveParallel = 8
)

var DefaultEquipmentIDs = []string{"EQ-TOOL-A1", "EQP01"}

type Catalog interface {
	GetInspectionPatchZips(ctx context.Context, inspectionTime, lotID, waferID, device, layerID string) (*scv1.GetInspectionPatchZipsResponse, error)
}

type ObjectRevision struct {
	Revision string
	Size     int64
}

type ObjectStore interface {
	DescribePatchObject(ctx context.Context, bucket, key string) (ObjectRevision, error)
	DownloadPatchObject(ctx context.Context, bucket, key, destination string) error
}

type Factory struct {
	catalog Catalog
	objects ObjectStore
}

func NewFactory(catalog Catalog, objects ObjectStore) *Factory {
	return &Factory{catalog: catalog, objects: objects}
}

func (f *Factory) Open(ctx context.Context, params equipment.OpenParams) (imagestream.Context, error) {
	if f.catalog == nil || f.objects == nil {
		return nil, &imagestream.ContextError{Code: "entry_unavailable", Message: "legacy range-ZIP entry dependencies are required"}
	}
	roles, err := normalizeRoles(params.Roles)
	if err != nil {
		return nil, &imagestream.ContextError{Code: "unsupported_roles", Message: err.Error()}
	}
	refs, err := f.catalog.GetInspectionPatchZips(
		ctx,
		params.Inspection.InspectionTime,
		params.Inspection.LotID,
		params.Inspection.WaferID,
		params.Inspection.Device,
		params.Inspection.LayerID,
	)
	if err != nil {
		return nil, &imagestream.ContextError{Code: "source_unavailable", Message: fmt.Sprintf("resolve inspection patch archives: %v", err)}
	}
	if refs == nil || len(refs.Zips) == 0 {
		return nil, &imagestream.ContextError{Code: "source_unavailable", Message: "inspection has no patch archives"}
	}
	return &entryContext{
		equipmentID: params.Inspection.EquipmentID,
		roles:       roles,
		refs:        append([]*scv1.ZipRef(nil), refs.Zips...),
		cache:       params.Cache,
		objects:     f.objects,
	}, nil
}

type entryContext struct {
	equipmentID string
	roles       []roleSpec
	refs        []*scv1.ZipRef
	cache       artifactcache.Cache
	objects     ObjectStore
}

func (c *entryContext) EquipmentID() string { return c.equipmentID }

type plannedSample struct {
	request      imagestream.SampleRequest
	defectID     int
	archiveIndex int
}

type plannedRole struct {
	sampleIndex int
	roleIndex   int
	prefix      string
}

func (c *entryContext) Resolve(ctx context.Context, requests []imagestream.SampleRequest) ([]imagestream.SampleResult, error) {
	results := make([]imagestream.SampleResult, len(requests))
	groups := make(map[int][]plannedRole)
	for sampleIndex, request := range requests {
		results[sampleIndex] = imagestream.SampleResult{
			Sequence: request.Sequence,
			SampleID: request.SampleID,
			DefectID: request.DefectID,
			Images:   make([]imagestream.RoleResult, len(c.roles)),
		}
		defectID, err := parseDefectID(request.DefectID)
		if err != nil || defectID <= 0 {
			results[sampleIndex].Err = fmt.Errorf("defect_id must end in a positive integer")
			continue
		}
		archiveIndex := (defectID - 1) / defectsPerArchive
		if archiveIndex < 0 || archiveIndex >= len(c.refs) || c.refs[archiveIndex] == nil {
			return nil, &imagestream.ContextError{Code: "source_unavailable", Message: fmt.Sprintf("inspection has no patch archive at index %d", archiveIndex)}
		}
		for roleIndex, role := range c.roles {
			results[sampleIndex].Images[roleIndex].Role = role.canonical
			groups[archiveIndex] = append(groups[archiveIndex], plannedRole{
				sampleIndex: sampleIndex,
				roleIndex:   roleIndex,
				prefix:      fmt.Sprintf("%06d_%s", defectID, role.member),
			})
		}
	}

	type archiveResult struct {
		index  int
		path   string
		assets []plannedRole
		err    error
	}
	resolvedArchives := make(chan archiveResult, len(groups))
	semaphore := make(chan struct{}, maxArchiveParallel)
	for archiveIndex, assets := range groups {
		go func(index int, assets []plannedRole) {
			semaphore <- struct{}{}
			defer func() { <-semaphore }()
			path, err := c.resolveArchive(ctx, c.refs[index])
			resolvedArchives <- archiveResult{index: index, path: path, assets: assets, err: err}
		}(archiveIndex, assets)
	}
	for range groups {
		archive := <-resolvedArchives
		if archive.err != nil {
			return nil, archive.err
		}
		if err := parseArchive(archive.path, archive.assets, results); err != nil {
			return nil, &imagestream.ContextError{Code: "parser_unavailable", Message: fmt.Sprintf("parse patch archive %d: %v", archive.index, err)}
		}
	}
	return results, nil
}

func (c *entryContext) resolveArchive(ctx context.Context, ref *scv1.ZipRef) (string, error) {
	if strings.TrimSpace(ref.S3Bucket) == "" || strings.TrimSpace(ref.S3Key) == "" {
		return "", &imagestream.ContextError{Code: "source_unavailable", Message: "patch archive has an invalid object reference"}
	}
	revision, err := c.objects.DescribePatchObject(ctx, ref.S3Bucket, ref.S3Key)
	if err != nil {
		return "", &imagestream.ContextError{Code: "source_unavailable", Message: fmt.Sprintf("describe patch archive: %v", err)}
	}
	path, err := c.cache.GetOrDownload(ctx, artifactcache.Ref{
		EntryID: EntryID, SourceIdentity: ref.S3Bucket + "/" + ref.S3Key, Revision: revision.Revision, Kind: artifactcache.KindFile,
	}, func(ctx context.Context, destination string) error {
		return c.objects.DownloadPatchObject(ctx, ref.S3Bucket, ref.S3Key, destination)
	})
	if err != nil {
		return "", &imagestream.ContextError{Code: "source_unavailable", Message: fmt.Sprintf("cache patch archive: %v", err)}
	}
	return path, nil
}

func (*entryContext) Close() error { return nil }

type roleSpec struct {
	canonical string
	member    string
}

func normalizeRoles(rawRoles []string) ([]roleSpec, error) {
	roles := make([]roleSpec, len(rawRoles))
	seen := make(map[string]struct{}, len(rawRoles))
	for index, raw := range rawRoles {
		var role roleSpec
		switch strings.ToLower(strings.TrimSpace(raw)) {
		case "patch_template", "template", "reference":
			role = roleSpec{canonical: "patch_template", member: "PatchReference"}
		case "patch_defective", "defective":
			role = roleSpec{canonical: "patch_defective", member: "PatchDefective"}
		case "patch_difference", "difference":
			role = roleSpec{canonical: "patch_difference", member: "PatchDifference"}
		default:
			return nil, fmt.Errorf("unsupported patch image role %q", raw)
		}
		if _, exists := seen[role.canonical]; exists {
			return nil, fmt.Errorf("duplicate patch image role %q", role.canonical)
		}
		seen[role.canonical] = struct{}{}
		roles[index] = role
	}
	return roles, nil
}

func parseArchive(path string, assets []plannedRole, results []imagestream.SampleResult) error {
	archive, err := zip.OpenReader(path)
	if err != nil {
		return err
	}
	defer archive.Close()
	wanted := make(map[string][]plannedRole, len(assets))
	for _, asset := range assets {
		wanted[asset.prefix] = append(wanted[asset.prefix], asset)
	}
	found := make(map[string]bool, len(wanted))
	for _, file := range archive.File {
		stem := strings.TrimSuffix(filepath.Base(file.Name), filepath.Ext(file.Name))
		planned := wanted[stem]
		if len(planned) == 0 || found[stem] {
			continue
		}
		found[stem] = true
		data, readErr := readZipMember(file)
		contentType := mime.TypeByExtension(filepath.Ext(file.Name))
		if contentType == "" {
			contentType = "application/octet-stream"
		}
		for _, asset := range planned {
			result := &results[asset.sampleIndex].Images[asset.roleIndex]
			result.ContentType = contentType
			if readErr != nil {
				result.Err = readErr
			} else {
				result.Data = data
			}
		}
	}
	for prefix, planned := range wanted {
		if found[prefix] {
			continue
		}
		for _, asset := range planned {
			results[asset.sampleIndex].Images[asset.roleIndex].Err = fmt.Errorf("image member %q not found in patch archive", prefix)
		}
	}
	return nil
}

func readZipMember(file *zip.File) ([]byte, error) {
	handle, err := file.Open()
	if err != nil {
		return nil, fmt.Errorf("open ZIP member: %w", err)
	}
	data, readErr := io.ReadAll(handle)
	closeErr := handle.Close()
	if readErr != nil {
		return nil, fmt.Errorf("read ZIP member: %w", readErr)
	}
	if closeErr != nil {
		return nil, fmt.Errorf("close ZIP member: %w", closeErr)
	}
	return data, nil
}

func parseDefectID(raw string) (int, error) {
	trimmed := strings.TrimSpace(raw)
	if value, err := strconv.Atoi(trimmed); err == nil {
		return value, nil
	}
	if index := strings.LastIndex(trimmed, "-"); index >= 0 {
		return strconv.Atoi(trimmed[index+1:])
	}
	return 0, fmt.Errorf("invalid defect_id %q", raw)
}

var _ equipment.Factory = (*Factory)(nil)
