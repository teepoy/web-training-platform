// Package legacyrangezip implements the fixed SC range-ZIP image entry used by
// explicitly registered equipment IDs.
package legacyrangezip

import (
	"archive/zip"
	"bytes"
	"context"
	"crypto/sha256"
	"fmt"
	"image"
	_ "image/jpeg"
	_ "image/png"
	"io"
	"mime"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

	scv1 "image-parser/gen/go/sc/v1"
	"image-parser/internal/artifactcache"
	"image-parser/internal/equipment"
	"image-parser/internal/imagestream"
	"image-parser/internal/memorylru"

	"golang.org/x/sync/singleflight"
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

type ArchiveDescriptor struct {
	Identity string
	Revision string
	Size     int64
}

type ArchiveSource interface {
	DescribeArchive(ctx context.Context, ref *scv1.ZipRef) (ArchiveDescriptor, error)
	DownloadArchive(ctx context.Context, ref *scv1.ZipRef, destination string) error
}

type Factory struct {
	catalog  Catalog
	archives ArchiveSource
	profiles *memorylru.Cache[string, equipment.InspectionImageProfile]
	loads    singleflight.Group
}

func NewFactory(catalog Catalog, archives ArchiveSource, profileCacheEntries int) (*Factory, error) {
	if catalog == nil || archives == nil {
		return nil, fmt.Errorf("legacy range-ZIP entry dependencies are required")
	}
	profiles, err := memorylru.New[string, equipment.InspectionImageProfile](profileCacheEntries)
	if err != nil {
		return nil, fmt.Errorf("create legacy range-ZIP image profile cache: %w", err)
	}
	return &Factory{catalog: catalog, archives: archives, profiles: profiles}, nil
}

func (f *Factory) Open(ctx context.Context, params equipment.OpenParams) (imagestream.Context, error) {
	if f.catalog == nil || f.archives == nil {
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
		archives:    f.archives,
	}, nil
}

func (f *Factory) Profile(ctx context.Context, params equipment.ProfileParams) (equipment.InspectionImageProfile, error) {
	if params.Cache == nil {
		return equipment.InspectionImageProfile{}, &imagestream.ContextError{Code: "cache_unavailable", Message: "legacy range-ZIP artifact cache is required"}
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
		return equipment.InspectionImageProfile{}, &imagestream.ContextError{Code: "source_unavailable", Message: fmt.Sprintf("resolve inspection patch archives: %v", err)}
	}
	if refs == nil || len(refs.Zips) == 0 {
		return equipment.InspectionImageProfile{}, &imagestream.ContextError{Code: "source_unavailable", Message: "inspection has no patch archives"}
	}
	described := make([]describedArchive, len(refs.Zips))
	hash := sha256.New()
	for index, ref := range refs.Zips {
		if ref == nil {
			return equipment.InspectionImageProfile{}, &imagestream.ContextError{Code: "source_unavailable", Message: fmt.Sprintf("patch archive %d has no source reference", index)}
		}
		descriptor, err := f.archives.DescribeArchive(ctx, ref)
		if err != nil {
			return equipment.InspectionImageProfile{}, &imagestream.ContextError{Code: "source_unavailable", Message: fmt.Sprintf("describe patch archive %d: %v", index, err)}
		}
		described[index] = describedArchive{ref: ref, descriptor: descriptor}
		_, _ = fmt.Fprintf(hash, "%s\x00%s\x00", descriptor.Identity, descriptor.Revision)
	}
	cacheKey := fmt.Sprintf("%x", hash.Sum(nil))
	if cached, ok := f.profiles.Get(cacheKey); ok {
		return cloneProfile(cached), nil
	}
	loaded, err, _ := f.loads.Do(cacheKey, func() (any, error) {
		if cached, ok := f.profiles.Get(cacheKey); ok {
			return cached, nil
		}
		profile, err := f.scanProfile(ctx, params.Cache, described)
		if err != nil {
			return equipment.InspectionImageProfile{}, err
		}
		f.profiles.Add(cacheKey, cloneProfile(profile))
		return profile, nil
	})
	if err != nil {
		return equipment.InspectionImageProfile{}, err
	}
	return cloneProfile(loaded.(equipment.InspectionImageProfile)), nil
}

type describedArchive struct {
	ref        *scv1.ZipRef
	descriptor ArchiveDescriptor
}

func (f *Factory) scanProfile(ctx context.Context, cache artifactcache.Cache, archives []describedArchive) (equipment.InspectionImageProfile, error) {
	aggregates := make(map[profileKey]profileAggregate)
	for index, archive := range archives {
		lease, err := cache.Acquire(ctx, artifactcache.Ref{
			EntryID: EntryID, SourceIdentity: archive.descriptor.Identity,
			Revision: archive.descriptor.Revision, Kind: artifactcache.KindFile,
		}, func(ctx context.Context, destination string) error {
			return f.archives.DownloadArchive(ctx, archive.ref, destination)
		})
		if err != nil {
			return equipment.InspectionImageProfile{}, &imagestream.ContextError{Code: "source_unavailable", Message: fmt.Sprintf("cache patch archive %d: %v", index, err)}
		}
		scanErr := scanArchiveProfile(lease.Path(), aggregates)
		releaseErr := lease.Release()
		if scanErr != nil {
			return equipment.InspectionImageProfile{}, &imagestream.ContextError{Code: "parser_unavailable", Message: fmt.Sprintf("profile patch archive %d: %v", index, scanErr)}
		}
		if releaseErr != nil {
			return equipment.InspectionImageProfile{}, &imagestream.ContextError{Code: "entry_unavailable", Message: fmt.Sprintf("release patch archive %d: %v", index, releaseErr)}
		}
	}
	items := make([]profileAggregate, 0, len(aggregates))
	for _, item := range aggregates {
		items = append(items, item)
	}
	sort.Slice(items, func(left, right int) bool {
		leftRank := profileImageTypeRank(items[left].imageType)
		rightRank := profileImageTypeRank(items[right].imageType)
		if leftRank != rightRank {
			return leftRank < rightRank
		}
		return items[left].imageID < items[right].imageID
	})
	profile := equipment.InspectionImageProfile{Patches: make([]equipment.PatchImageProfile, len(items))}
	for index, item := range items {
		var imageID *int
		if item.imageID >= 0 {
			value := item.imageID
			imageID = &value
		}
		profile.Patches[index] = equipment.PatchImageProfile{
			ImageType: item.imageType, ImageID: imageID, BitDepth: item.bitDepth, ZMin: item.zMin, ZMax: item.zMax,
		}
	}
	return profile, nil
}

type entryContext struct {
	equipmentID string
	roles       []roleSpec
	refs        []*scv1.ZipRef
	cache       artifactcache.Cache
	archives    ArchiveSource
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
		lease  artifactcache.Lease
		assets []plannedRole
		err    error
	}
	resolvedArchives := make(chan archiveResult, len(groups))
	semaphore := make(chan struct{}, maxArchiveParallel)
	for archiveIndex, assets := range groups {
		go func(index int, assets []plannedRole) {
			semaphore <- struct{}{}
			defer func() { <-semaphore }()
			lease, err := c.resolveArchive(ctx, c.refs[index])
			resolvedArchives <- archiveResult{index: index, lease: lease, assets: assets, err: err}
		}(archiveIndex, assets)
	}
	var firstErr error
	for range groups {
		archive := <-resolvedArchives
		if archive.err != nil {
			if firstErr == nil {
				firstErr = archive.err
			}
			continue
		}
		if firstErr == nil {
			if err := parseArchive(archive.lease.Path(), archive.assets, results); err != nil {
				firstErr = &imagestream.ContextError{Code: "parser_unavailable", Message: fmt.Sprintf("parse patch archive %d: %v", archive.index, err)}
			}
		}
		if err := archive.lease.Release(); err != nil && firstErr == nil {
			firstErr = &imagestream.ContextError{Code: "entry_unavailable", Message: fmt.Sprintf("release patch archive %d: %v", archive.index, err)}
		}
	}
	if firstErr != nil {
		return nil, firstErr
	}
	return results, nil
}

func (c *entryContext) resolveArchive(ctx context.Context, ref *scv1.ZipRef) (artifactcache.Lease, error) {
	if ref == nil {
		return nil, &imagestream.ContextError{Code: "source_unavailable", Message: "patch archive has no source reference"}
	}
	descriptor, err := c.archives.DescribeArchive(ctx, ref)
	if err != nil {
		return nil, &imagestream.ContextError{Code: "source_unavailable", Message: fmt.Sprintf("describe patch archive: %v", err)}
	}
	lease, err := c.cache.Acquire(ctx, artifactcache.Ref{
		EntryID: EntryID, SourceIdentity: descriptor.Identity, Revision: descriptor.Revision, Kind: artifactcache.KindFile,
	}, func(ctx context.Context, destination string) error {
		return c.archives.DownloadArchive(ctx, ref, destination)
	})
	if err != nil {
		return nil, &imagestream.ContextError{Code: "source_unavailable", Message: fmt.Sprintf("cache patch archive: %v", err)}
	}
	return lease, nil
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
		base, imageIDRaw, hasImageID := strings.Cut(strings.ToLower(strings.TrimSpace(raw)), ":")
		imageID := 0
		if hasImageID {
			parsed, err := strconv.Atoi(strings.TrimSpace(imageIDRaw))
			if err != nil || parsed < 0 {
				return nil, fmt.Errorf("invalid patch image role %q", raw)
			}
			imageID = parsed
		}
		var role roleSpec
		switch base {
		case "patch_template", "patchtemplate", "patch_reference", "patchreference", "template", "reference":
			role = roleSpec{canonical: "patch_template", member: "PatchReference"}
			if hasImageID {
				role = roleSpec{canonical: fmt.Sprintf("patch_reference:%d", imageID), member: fmt.Sprintf("PatchReference%d", imageID)}
			}
		case "patch_defective", "patchdefective", "defective":
			if hasImageID {
				return nil, fmt.Errorf("Defective patch image role does not accept image_id")
			}
			role = roleSpec{canonical: "patch_defective", member: "PatchDefective"}
		case "patch_difference", "patchdifference", "difference":
			role = roleSpec{canonical: "patch_difference", member: "PatchDifference"}
			if hasImageID {
				role = roleSpec{canonical: fmt.Sprintf("patch_difference:%d", imageID), member: fmt.Sprintf("PatchDifference%d", imageID)}
			}
		case "patch_mask", "patchmask", "mask":
			role = roleSpec{canonical: "patch_mask", member: "PatchMask"}
			if hasImageID {
				role = roleSpec{canonical: fmt.Sprintf("patch_mask:%d", imageID), member: fmt.Sprintf("PatchMask%d", imageID)}
			}
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

type profileKey struct {
	imageType string
	imageID   int
}

type profileAggregate struct {
	imageType string
	imageID   int
	bitDepth  int
	zMin      uint16
	zMax      uint16
}

func scanArchiveProfile(path string, aggregates map[profileKey]profileAggregate) error {
	archive, err := zip.OpenReader(path)
	if err != nil {
		return err
	}
	defer archive.Close()
	for _, file := range archive.File {
		imageType, imageID, ok, err := parsePatchProfileMember(filepath.Base(file.Name))
		if err != nil {
			return err
		}
		if !ok {
			continue
		}
		data, err := readZipMember(file)
		if err != nil {
			return err
		}
		bitDepth, zMin, zMax, err := grayProfile(data)
		if err != nil {
			return fmt.Errorf("%s: %w", file.Name, err)
		}
		key := profileKey{imageType: imageType, imageID: imageID}
		current, exists := aggregates[key]
		if !exists {
			aggregates[key] = profileAggregate{imageType: imageType, imageID: imageID, bitDepth: bitDepth, zMin: zMin, zMax: zMax}
			continue
		}
		current.bitDepth = max(current.bitDepth, bitDepth)
		current.zMin = min(current.zMin, zMin)
		current.zMax = max(current.zMax, zMax)
		aggregates[key] = current
	}
	return nil
}

func parsePatchProfileMember(name string) (string, int, bool, error) {
	stem := strings.TrimSuffix(name, filepath.Ext(name))
	separator := strings.IndexByte(stem, '_')
	if separator < 0 || separator == len(stem)-1 {
		return "", 0, false, nil
	}
	suffix := stem[separator+1:]
	for _, candidate := range []struct {
		prefix    string
		imageType string
	}{
		{prefix: "PatchDefective", imageType: "Defective"},
		{prefix: "PatchReference", imageType: "Reference"},
		{prefix: "PatchDifference", imageType: "Difference"},
		{prefix: "PatchMask", imageType: "Mask"},
	} {
		if !strings.HasPrefix(suffix, candidate.prefix) {
			continue
		}
		remainder := strings.TrimPrefix(suffix, candidate.prefix)
		if remainder == "" {
			return candidate.imageType, -1, true, nil
		}
		imageID, err := strconv.Atoi(remainder)
		if err != nil || imageID < 0 {
			return "", 0, false, fmt.Errorf("invalid image instance in ZIP member %q", name)
		}
		if candidate.imageType == "Defective" {
			return "", 0, false, fmt.Errorf("Defective ZIP member %q must not have image_id", name)
		}
		return candidate.imageType, imageID, true, nil
	}
	return "", 0, false, nil
}

func grayProfile(data []byte) (int, uint16, uint16, error) {
	decoded, _, err := image.Decode(bytes.NewReader(data))
	if err != nil {
		return 0, 0, 0, fmt.Errorf("decode grayscale image: %w", err)
	}
	zMin := uint16(65535)
	var zMax uint16
	bitDepth := 0
	switch typed := decoded.(type) {
	case *image.Gray:
		bitDepth = 8
		for _, value := range typed.Pix {
			zMin = min(zMin, uint16(value))
			zMax = max(zMax, uint16(value))
		}
	case *image.Gray16:
		for y := typed.Bounds().Min.Y; y < typed.Bounds().Max.Y; y++ {
			for x := typed.Bounds().Min.X; x < typed.Bounds().Max.X; x++ {
				value := typed.Gray16At(x, y).Y
				zMin = min(zMin, value)
				zMax = max(zMax, value)
			}
		}
		bitDepth = 16
		if zMax <= 4095 {
			bitDepth = 12
		}
	default:
		bounds := decoded.Bounds()
		for y := bounds.Min.Y; y < bounds.Max.Y; y++ {
			for x := bounds.Min.X; x < bounds.Max.X; x++ {
				red, green, blue, alpha := decoded.At(x, y).RGBA()
				if red != green || green != blue || alpha != 65535 {
					return 0, 0, 0, fmt.Errorf("only grayscale patch images can be profiled")
				}
				zMin = min(zMin, uint16(red))
				zMax = max(zMax, uint16(red))
			}
		}
		bitDepth = 16
	}
	return bitDepth, zMin, zMax, nil
}

func profileImageTypeRank(imageType string) int {
	switch imageType {
	case "Defective":
		return 0
	case "Reference":
		return 1
	case "Difference":
		return 2
	case "Mask":
		return 3
	default:
		return 4
	}
}

func cloneProfile(profile equipment.InspectionImageProfile) equipment.InspectionImageProfile {
	cloned := profile
	cloned.Patches = make([]equipment.PatchImageProfile, len(profile.Patches))
	for index, patch := range profile.Patches {
		cloned.Patches[index] = patch
		if patch.ImageID != nil {
			value := *patch.ImageID
			cloned.Patches[index].ImageID = &value
		}
	}
	return cloned
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
var _ equipment.ProfileFactory = (*Factory)(nil)
