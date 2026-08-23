// Package sqliteinspectionimages implements the inspection_images SQLite
// artifact contract used by equipment-specific image entries.
package sqliteinspectionimages

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/binary"
	"errors"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"net/url"
	"sort"
	"strconv"
	"strings"

	"github.com/golang/snappy"
	"golang.org/x/sync/singleflight"
	"image-parser/internal/artifactcache"
	"image-parser/internal/equipment"
	"image-parser/internal/imagestream"
	"image-parser/internal/memorylru"

	_ "modernc.org/sqlite"
)

const (
	EntryID             = "sc.sqlite-inspection-images.v1"
	maxQueryDefectIDs   = 400
	imageWidth          = 32
	imageHeight         = 32
	validationStatement = "SELECT id, defect_id, image_type, image_id, image_value FROM inspection_images LIMIT 0"
)

var snappyPrefix = []byte{0x2e, 0x9c}

type Artifact struct {
	SourceIdentity string
	Revision       string
}

type Source interface {
	Describe(ctx context.Context, inspection equipment.Inspection) (Artifact, error)
	Download(ctx context.Context, artifact Artifact, destination string) error
}

type Factory struct {
	source   Source
	profiles *memorylru.Cache[string, equipment.InspectionImageProfile]
	loads    singleflight.Group
}

func NewFactory(source Source, profileCacheEntries int) (*Factory, error) {
	if source == nil {
		return nil, fmt.Errorf("SQLite inspection image source is required")
	}
	profiles, err := memorylru.New[string, equipment.InspectionImageProfile](profileCacheEntries)
	if err != nil {
		return nil, fmt.Errorf("create SQLite image profile cache: %w", err)
	}
	return &Factory{source: source, profiles: profiles}, nil
}

func (f *Factory) Open(ctx context.Context, params equipment.OpenParams) (imagestream.Context, error) {
	roles, err := normalizeRoles(params.Roles)
	if err != nil {
		return nil, &imagestream.ContextError{Code: "unsupported_roles", Message: err.Error()}
	}
	lease, database, _, err := f.openArtifact(ctx, params.Inspection, params.Cache)
	if err != nil {
		return nil, err
	}
	return &entryContext{
		equipmentID: params.Inspection.EquipmentID,
		roles:       roles,
		database:    database,
		lease:       lease,
	}, nil
}

func (f *Factory) Profile(ctx context.Context, params equipment.ProfileParams) (equipment.InspectionImageProfile, error) {
	if params.Cache == nil {
		return equipment.InspectionImageProfile{}, &imagestream.ContextError{Code: "cache_unavailable", Message: "SQLite inspection image artifact cache is required"}
	}
	artifact, err := f.describe(ctx, params.Inspection)
	if err != nil {
		return equipment.InspectionImageProfile{}, err
	}
	cacheKey := artifact.SourceIdentity + "\x00" + artifact.Revision
	if cached, ok := f.profiles.Get(cacheKey); ok {
		return cloneProfile(cached), nil
	}
	loaded, err, _ := f.loads.Do(cacheKey, func() (any, error) {
		if cached, ok := f.profiles.Get(cacheKey); ok {
			return cached, nil
		}
		lease, database, err := f.openDescribedArtifact(ctx, artifact, params.Cache)
		if err != nil {
			return equipment.InspectionImageProfile{}, err
		}
		defer lease.Release()
		defer database.Close()
		profile, err := scanProfile(ctx, database)
		if err != nil {
			return equipment.InspectionImageProfile{}, &imagestream.ContextError{Code: "parser_unavailable", Message: fmt.Sprintf("profile SQLite inspection images: %v", err)}
		}
		f.profiles.Add(cacheKey, cloneProfile(profile))
		return profile, nil
	})
	if err != nil {
		return equipment.InspectionImageProfile{}, err
	}
	return cloneProfile(loaded.(equipment.InspectionImageProfile)), nil
}

func (f *Factory) openArtifact(
	ctx context.Context,
	inspection equipment.Inspection,
	cache artifactcache.Cache,
) (artifactcache.Lease, *sql.DB, Artifact, error) {
	artifact, err := f.describe(ctx, inspection)
	if err != nil {
		return nil, nil, Artifact{}, err
	}
	lease, database, err := f.openDescribedArtifact(ctx, artifact, cache)
	return lease, database, artifact, err
}

func (f *Factory) describe(ctx context.Context, inspection equipment.Inspection) (Artifact, error) {
	artifact, err := f.source.Describe(ctx, inspection)
	if err != nil {
		return Artifact{}, &imagestream.ContextError{Code: "source_unavailable", Message: fmt.Sprintf("describe SQLite inspection image artifact: %v", err)}
	}
	artifact.SourceIdentity = strings.TrimSpace(artifact.SourceIdentity)
	artifact.Revision = strings.TrimSpace(artifact.Revision)
	if artifact.SourceIdentity == "" || artifact.Revision == "" {
		return Artifact{}, &imagestream.ContextError{Code: "source_unavailable", Message: "SQLite inspection image artifact requires source identity and revision"}
	}
	return artifact, nil
}

func (f *Factory) openDescribedArtifact(
	ctx context.Context,
	artifact Artifact,
	cache artifactcache.Cache,
) (artifactcache.Lease, *sql.DB, error) {
	if cache == nil {
		return nil, nil, &imagestream.ContextError{Code: "cache_unavailable", Message: "SQLite inspection image artifact cache is required"}
	}
	lease, err := cache.Acquire(ctx, artifactcache.Ref{
		EntryID: EntryID, SourceIdentity: artifact.SourceIdentity, Revision: artifact.Revision, Kind: artifactcache.KindFile,
	}, func(ctx context.Context, destination string) error {
		return f.source.Download(ctx, artifact, destination)
	})
	if err != nil {
		return nil, nil, &imagestream.ContextError{Code: "source_unavailable", Message: fmt.Sprintf("cache SQLite inspection image artifact: %v", err)}
	}
	database, err := openReadOnly(lease.Path())
	if err != nil {
		_ = lease.Release()
		return nil, nil, &imagestream.ContextError{Code: "parser_unavailable", Message: fmt.Sprintf("open SQLite inspection image artifact: %v", err)}
	}
	return lease, database, nil
}

type entryContext struct {
	equipmentID string
	roles       []roleSpec
	database    *sql.DB
	lease       artifactcache.Lease
}

func (c *entryContext) EquipmentID() string { return c.equipmentID }

func (c *entryContext) Resolve(ctx context.Context, requests []imagestream.SampleRequest) ([]imagestream.SampleResult, error) {
	results := make([]imagestream.SampleResult, len(requests))
	defectIDs := make([]int, 0, len(requests))
	seen := make(map[int]struct{}, len(requests))
	requestDefectIDs := make([]int, len(requests))
	for index, request := range requests {
		results[index] = imagestream.SampleResult{
			Sequence: request.Sequence, SampleID: request.SampleID, DefectID: request.DefectID,
			Images: make([]imagestream.RoleResult, len(c.roles)),
		}
		for roleIndex, role := range c.roles {
			results[index].Images[roleIndex].Role = role.canonical
		}
		defectID, err := parseDefectID(request.DefectID)
		if err != nil || defectID <= 0 {
			results[index].Err = fmt.Errorf("defect_id must end in a positive integer")
			continue
		}
		requestDefectIDs[index] = defectID
		if _, ok := seen[defectID]; !ok {
			seen[defectID] = struct{}{}
			defectIDs = append(defectIDs, defectID)
		}
	}
	resolved := make(map[imageKey]storedImage, len(defectIDs)*len(c.roles))
	for start := 0; start < len(defectIDs); start += maxQueryDefectIDs {
		end := min(start+maxQueryDefectIDs, len(defectIDs))
		if err := c.readBatch(ctx, defectIDs[start:end], resolved); err != nil {
			return nil, &imagestream.ContextError{Code: "parser_unavailable", Message: fmt.Sprintf("query SQLite inspection images: %v", err)}
		}
	}
	for resultIndex := range results {
		defectID := requestDefectIDs[resultIndex]
		if defectID == 0 {
			continue
		}
		for roleIndex, role := range c.roles {
			stored, ok := resolved[imageKey{defectID: defectID, roleKey: roleKey{imageType: role.databaseType, imageID: role.imageID}}]
			if !ok {
				results[resultIndex].Images[roleIndex].Err = fmt.Errorf("image row not found for defect %d role %q", defectID, role.canonical)
				continue
			}
			if stored.err != nil {
				results[resultIndex].Images[roleIndex].Err = stored.err
				continue
			}
			results[resultIndex].Images[roleIndex].Data = stored.png
			results[resultIndex].Images[roleIndex].ContentType = "image/png"
		}
	}
	return results, nil
}

func (c *entryContext) readBatch(ctx context.Context, defectIDs []int, destination map[imageKey]storedImage) error {
	if len(defectIDs) == 0 {
		return nil
	}
	arguments := make([]any, len(defectIDs))
	for index, defectID := range defectIDs {
		arguments[index] = defectID
	}
	rows, err := c.database.QueryContext(ctx,
		"SELECT defect_id, image_type, image_id, image_value FROM inspection_images WHERE defect_id IN ("+placeholders(len(defectIDs))+")",
		arguments...,
	)
	if err != nil {
		return err
	}
	defer rows.Close()
	wanted := make(map[roleKey]struct{}, len(c.roles))
	for _, role := range c.roles {
		wanted[roleKey{imageType: role.databaseType, imageID: role.imageID}] = struct{}{}
	}
	for rows.Next() {
		var defectID int
		var imageType string
		var imageID sql.NullInt64
		var value []byte
		if err := rows.Scan(&defectID, &imageType, &imageID, &value); err != nil {
			return err
		}
		key := imageKey{defectID: defectID, roleKey: roleKey{
			imageType: strings.ToUpper(strings.TrimSpace(imageType)), imageID: nullableImageID(imageID),
		}}
		if _, ok := wanted[roleKey{imageType: key.imageType, imageID: key.imageID}]; !ok {
			continue
		}
		if _, exists := destination[key]; exists {
			return fmt.Errorf("duplicate image row for defect %d type %q image_id %d", defectID, imageType, key.imageID)
		}
		decoded, err := decodeSnappyImage(value)
		if err != nil {
			destination[key] = storedImage{err: fmt.Errorf("decode defect %d role %q: %w", defectID, imageType, err)}
			continue
		}
		destination[key] = storedImage{png: decoded.png}
	}
	return rows.Err()
}

func (c *entryContext) Close() error {
	if c == nil {
		return nil
	}
	var databaseErr error
	if c.database != nil {
		databaseErr = c.database.Close()
	}
	var leaseErr error
	if c.lease != nil {
		leaseErr = c.lease.Release()
	}
	return errors.Join(databaseErr, leaseErr)
}

type roleSpec struct {
	canonical    string
	databaseType string
	imageID      int
}

type roleKey struct {
	imageType string
	imageID   int
}

type imageKey struct {
	defectID int
	roleKey
}

type storedImage struct {
	png []byte
	err error
}

func normalizeRoles(rawRoles []string) ([]roleSpec, error) {
	roles := make([]roleSpec, len(rawRoles))
	seen := make(map[roleKey]struct{}, len(rawRoles))
	for index, raw := range rawRoles {
		role, err := parseRole(raw)
		if err != nil {
			return nil, err
		}
		key := roleKey{imageType: role.databaseType, imageID: role.imageID}
		if _, exists := seen[key]; exists {
			return nil, fmt.Errorf("duplicate SQLite inspection image role %q", role.canonical)
		}
		seen[key] = struct{}{}
		roles[index] = role
	}
	return roles, nil
}

func parseRole(raw string) (roleSpec, error) {
	base, imageIDRaw, hasImageID := strings.Cut(strings.ToLower(strings.TrimSpace(raw)), ":")
	imageID := 0
	if hasImageID {
		parsed, err := strconv.Atoi(strings.TrimSpace(imageIDRaw))
		if err != nil || parsed < 0 {
			return roleSpec{}, fmt.Errorf("invalid SQLite inspection image role %q", raw)
		}
		imageID = parsed
	}
	var role roleSpec
	switch base {
	case "patch_defective", "patchdefective", "defective", "target":
		if hasImageID {
			return roleSpec{}, fmt.Errorf("Defective image role does not accept image_id")
		}
		role = roleSpec{canonical: "patch_defective", databaseType: "T", imageID: -1}
	case "patch_template", "patch_reference", "patchreference", "template", "reference":
		role = roleSpec{canonical: fmt.Sprintf("patch_reference:%d", imageID), databaseType: "R", imageID: imageID}
	case "patch_difference", "patchdifference", "difference":
		role = roleSpec{canonical: fmt.Sprintf("patch_difference:%d", imageID), databaseType: "D", imageID: imageID}
	case "patch_mask", "patchmask", "mask":
		role = roleSpec{canonical: fmt.Sprintf("patch_mask:%d", imageID), databaseType: "M", imageID: imageID}
	default:
		return roleSpec{}, fmt.Errorf("unsupported SQLite inspection image role %q", raw)
	}
	return role, nil
}

func scanProfile(ctx context.Context, database *sql.DB) (equipment.InspectionImageProfile, error) {
	rows, err := database.QueryContext(ctx, "SELECT image_type, image_id, image_value FROM inspection_images ORDER BY id")
	if err != nil {
		return equipment.InspectionImageProfile{}, err
	}
	defer rows.Close()
	type aggregate struct {
		imageType string
		imageID   int
		bitDepth  int
		zMin      uint16
		zMax      uint16
	}
	profiles := make(map[roleKey]aggregate)
	for rows.Next() {
		var databaseType string
		var imageID sql.NullInt64
		var value []byte
		if err := rows.Scan(&databaseType, &imageID, &value); err != nil {
			return equipment.InspectionImageProfile{}, err
		}
		databaseType = strings.ToUpper(strings.TrimSpace(databaseType))
		imageType, ok := publicImageType(databaseType)
		if !ok {
			return equipment.InspectionImageProfile{}, fmt.Errorf("unsupported image_type %q", databaseType)
		}
		id := nullableImageID(imageID)
		decoded, err := decodeSnappyImage(value)
		if err != nil {
			return equipment.InspectionImageProfile{}, fmt.Errorf("decode %s image_id %d: %w", databaseType, id, err)
		}
		key := roleKey{imageType: databaseType, imageID: id}
		current, exists := profiles[key]
		if !exists {
			profiles[key] = aggregate{imageType: imageType, imageID: id, bitDepth: decoded.bitDepth, zMin: decoded.zMin, zMax: decoded.zMax}
			continue
		}
		current.bitDepth = max(current.bitDepth, decoded.bitDepth)
		current.zMin = min(current.zMin, decoded.zMin)
		current.zMax = max(current.zMax, decoded.zMax)
		profiles[key] = current
	}
	if err := rows.Err(); err != nil {
		return equipment.InspectionImageProfile{}, err
	}
	items := make([]aggregate, 0, len(profiles))
	for _, item := range profiles {
		items = append(items, item)
	}
	sort.Slice(items, func(left, right int) bool {
		leftRank := imageTypeRank(items[left].imageType)
		rightRank := imageTypeRank(items[right].imageType)
		if leftRank != rightRank {
			return leftRank < rightRank
		}
		return items[left].imageID < items[right].imageID
	})
	result := equipment.InspectionImageProfile{Patches: make([]equipment.PatchImageProfile, len(items))}
	for index, item := range items {
		var imageID *int
		if item.imageID >= 0 {
			value := item.imageID
			imageID = &value
		}
		result.Patches[index] = equipment.PatchImageProfile{
			ImageType: item.imageType, ImageID: imageID, BitDepth: item.bitDepth, ZMin: item.zMin, ZMax: item.zMax,
		}
	}
	return result, nil
}

type decodedImage struct {
	png      []byte
	bitDepth int
	zMin     uint16
	zMax     uint16
}

func decodeSnappyImage(value []byte) (decodedImage, error) {
	if len(value) < len(snappyPrefix) || !bytes.Equal(value[:len(snappyPrefix)], snappyPrefix) {
		return decodedImage{}, fmt.Errorf("missing 2E9C Snappy prefix")
	}
	raw, err := snappy.Decode(nil, value[len(snappyPrefix):])
	if err != nil {
		return decodedImage{}, fmt.Errorf("decode Snappy block: %w", err)
	}
	var source image.Image
	var bitDepth int
	zMin := uint16(65535)
	var zMax uint16
	switch len(raw) {
	case imageWidth * imageHeight:
		gray := image.NewGray(image.Rect(0, 0, imageWidth, imageHeight))
		copy(gray.Pix, raw)
		for _, value := range raw {
			zMin = min(zMin, uint16(value))
			zMax = max(zMax, uint16(value))
		}
		bitDepth = 8
		source = gray
	case imageWidth * imageHeight * 2:
		gray := image.NewGray16(image.Rect(0, 0, imageWidth, imageHeight))
		for index := 0; index < imageWidth*imageHeight; index++ {
			value := binary.BigEndian.Uint16(raw[index*2 : index*2+2])
			if value > 4095 {
				return decodedImage{}, fmt.Errorf("12-bit pixel %d exceeds 4095", value)
			}
			gray.SetGray16(index%imageWidth, index/imageWidth, color.Gray16{Y: value})
			zMin = min(zMin, value)
			zMax = max(zMax, value)
		}
		bitDepth = 12
		source = gray
	default:
		return decodedImage{}, fmt.Errorf("decoded %d bytes, want 1024 or 2048", len(raw))
	}
	var encoded bytes.Buffer
	if err := png.Encode(&encoded, source); err != nil {
		return decodedImage{}, fmt.Errorf("encode PNG: %w", err)
	}
	return decodedImage{png: encoded.Bytes(), bitDepth: bitDepth, zMin: zMin, zMax: zMax}, nil
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
	// Each immutable artifact gets one connection. Bounded concurrency belongs
	// to imagestream's governor; SQLite must not create an unbounded pool.
	database.SetMaxOpenConns(1)
	database.SetMaxIdleConns(1)
	if err := database.Ping(); err != nil {
		_ = database.Close()
		return nil, err
	}
	if _, err := database.Exec(validationStatement); err != nil {
		_ = database.Close()
		return nil, fmt.Errorf("validate inspection_images table: %w", err)
	}
	return database, nil
}

func publicImageType(databaseType string) (string, bool) {
	switch databaseType {
	case "T":
		return "Defective", true
	case "R":
		return "Reference", true
	case "D":
		return "Difference", true
	case "M":
		return "Mask", true
	default:
		return "", false
	}
}

func imageTypeRank(imageType string) int {
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

func nullableImageID(value sql.NullInt64) int {
	if !value.Valid {
		return -1
	}
	return int(value.Int64)
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

func placeholders(count int) string {
	if count <= 0 {
		return "NULL"
	}
	return strings.TrimSuffix(strings.Repeat("?,", count), ",")
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

var _ equipment.Factory = (*Factory)(nil)
var _ equipment.ProfileFactory = (*Factory)(nil)
