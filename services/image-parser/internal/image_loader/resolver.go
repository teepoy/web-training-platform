package image_loader

import (
	"context"
	"fmt"
	"path/filepath"
	"strconv"
	"strings"
	"sync"

	"image-parser/internal/image_loader/cache"
)

const defectsPerZip = 500
const patchZipWorkerLimit = 8

type Resolver struct {
	upstream UpstreamSource
	loader   objectLoader
	zipCache *cache.ZipCache
	warmer   *cache.Warmer
}

func newResolver(upstream UpstreamSource, loader objectLoader, zipCache *cache.ZipCache, warmer *cache.Warmer) *Resolver {
	return &Resolver{
		upstream: upstream,
		loader:   loader,
		zipCache: zipCache,
		warmer:   warmer,
	}
}

func (r *Resolver) GetImageBytes(ctx context.Context, keys []ImageKey) []ImageBytes {
	results := make([]ImageBytes, len(keys))
	patchLookupsByInspection := map[InspectionKey][]patchImageLookup{}

	for i, key := range keys {
		results[i] = ImageBytes{Key: key}
		switch key.Kind {
		case ImageKindPatch:
			patchLookupsByInspection[key.InspectionKey] = append(
				patchLookupsByInspection[key.InspectionKey],
				patchImageLookup{Index: i, DefectID: key.DefectID, ImageType: key.ImageType},
			)
		case ImageKindReview:
			data, err := r.getReviewImageBytes(ctx, key.InspectionTime, key.WaferKey, key.DefectID, key.ReviewImageID)
			results[i].Data = data
			results[i].ContentType = "image/jpeg"
			results[i].Err = err
		default:
			results[i].Err = fmt.Errorf("unsupported image kind %q", key.Kind)
		}
	}

	for inspection, lookups := range patchLookupsByInspection {
		resolved := r.loadPatchImages(ctx, inspection, lookups)
		for _, item := range resolved {
			results[item.Index].Data = item.Data
			results[item.Index].ContentType = "image/png"
			results[item.Index].Err = item.Err
		}
	}
	return results
}

func parseDefectID(defectID string) (int, error) {
	if n, err := strconv.Atoi(defectID); err == nil {
		return n, nil
	}
	i := strings.LastIndex(defectID, "-")
	if i >= 0 {
		return strconv.Atoi(defectID[i+1:])
	}
	return strconv.Atoi(defectID)
}

func (r *Resolver) resolveMetadataForWarm(ctx context.Context, inspectionTime string, waferKey int) (lotID, waferID, device, layerID string, err error) {
	resp, err := r.upstream.GetInspection(ctx, inspectionTime, int32(waferKey))
	if err != nil {
		return "", "", "", "", fmt.Errorf("get inspection: %w", err)
	}
	return resp.LotId, resp.WaferId, resp.Device, resp.LayerId, nil
}

func (r *Resolver) resolvePatchZipsForWarm(ctx context.Context, inspectionTime, lotID, waferID, device, layerID string) ([]cacheZipRef, error) {
	resp, err := r.upstream.GetInspectionPatchZips(ctx, inspectionTime, lotID, waferID, device, layerID)
	if err != nil {
		return nil, fmt.Errorf("get zips: %w", err)
	}
	var refs []cacheZipRef
	for _, z := range resp.Zips {
		refs = append(refs, cacheZipRef{Bucket: z.S3Bucket, Key: z.S3Key})
	}
	return refs, nil
}

type cacheZipRef struct {
	Bucket string
	Key    string
}

type patchImageLookup struct {
	Index     int
	DefectID  string
	ImageType string
}

type patchImageLookupResult struct {
	Index     int
	DefectID  string
	ImageType string
	Data      []byte
	Err       error
}

func locateZipForDefect(zips []cacheZipRef, defectID int) (*cacheZipRef, error) {
	zipIdx := zipIndexForDefect(defectID)
	if zipIdx >= len(zips) {
		return nil, fmt.Errorf("defect %d out of range (zip_idx=%d, total_zips=%d)", defectID, zipIdx, len(zips))
	}
	return &zips[zipIdx], nil
}

func patchImagePrefix(defectID int, imageType string) (string, bool) {
	switch normalizePatchImageType(imageType) {
	case "Reference":
		return fmt.Sprintf("%06d_PatchReference", defectID), true
	case "Defective":
		return fmt.Sprintf("%06d_PatchDefective", defectID), true
	case "Difference":
		return fmt.Sprintf("%06d_PatchDifference", defectID), true
	default:
		return "", false
	}
}

func normalizePatchImageType(imageType string) string {
	switch strings.ToLower(strings.TrimSpace(imageType)) {
	case "patch_template", "template", "reference", "patchtemplate", "patch_reference", "patchreference":
		return "Reference"
	case "patch_defective", "defective", "patchdefective":
		return "Defective"
	case "patch_difference", "difference", "patchdifference":
		return "Difference"
	default:
		return strings.TrimSpace(imageType)
	}
}

func (r *Resolver) getMetaAndZips(ctx context.Context, inspectionTime string, waferKey int) (lotID, waferID, device, layerID string, zips []cacheZipRef, err error) {
	meta, err := r.upstream.GetInspection(ctx, inspectionTime, int32(waferKey))
	if err != nil {
		return "", "", "", "", nil, fmt.Errorf("resolve metadata: %w", err)
	}
	m := meta
	zipsResp, err := r.upstream.GetInspectionPatchZips(ctx, inspectionTime, m.LotId, m.WaferId, m.Device, m.LayerId)
	if err != nil {
		return "", "", "", "", nil, fmt.Errorf("resolve zips: %w", err)
	}
	for _, z := range zipsResp.Zips {
		zips = append(zips, cacheZipRef{Bucket: z.S3Bucket, Key: z.S3Key})
	}
	return m.LotId, m.WaferId, m.Device, m.LayerId, zips, nil
}

func (r *Resolver) getPatchImageBytesBatchFromZips(ctx context.Context, zips []cacheZipRef, lookups []patchImageLookup) []patchImageLookupResult {
	results := make([]patchImageLookupResult, len(lookups))
	type zipLookup struct {
		resultIdx int
		prefix    string
		legacy    bool
	}
	grouped := map[string][]zipLookup{}
	refs := map[string]cacheZipRef{}

	for i, lookup := range lookups {
		results[i] = patchImageLookupResult{
			Index:     lookup.Index,
			DefectID:  lookup.DefectID,
			ImageType: lookup.ImageType,
		}
		if err := ctx.Err(); err != nil {
			results[i].Err = err
			continue
		}
		did, err := parseDefectID(lookup.DefectID)
		if err != nil {
			results[i].Err = fmt.Errorf("invalid defect_id: %w", err)
			continue
		}
		ref, err := locateZipForDefect(zips, did)
		if err != nil {
			results[i].Err = fmt.Errorf("locate zip: %w", err)
			continue
		}
		key := cache.CacheKey(ref.Bucket, ref.Key)
		refs[key] = *ref
		prefix, ok := patchImagePrefix(did, lookup.ImageType)
		legacy := false
		if !ok {
			prefix = fmt.Sprintf("%06d", did)
			legacy = true
		}
		grouped[key] = append(grouped[key], zipLookup{
			resultIdx: i,
			prefix:    prefix,
			legacy:    legacy,
		})
	}

	sem := make(chan struct{}, patchZipWorkerLimit)
	var wg sync.WaitGroup
	for key, items := range grouped {
		wg.Add(1)
		go func(key string, items []zipLookup) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			if err := ctx.Err(); err != nil {
				for _, item := range items {
					results[item.resultIdx].Err = err
				}
				return
			}

			ref := refs[key]
			zipData, err := r.zipCache.GetOrLoad(key, func() ([]byte, error) {
				return r.loader.LoadPatchZip(ctx, ref.Bucket, ref.Key)
			})
			if err != nil {
				for _, item := range items {
					results[item.resultIdx].Err = fmt.Errorf("download zip: %w", err)
				}
				return
			}
			prefixes := make([]string, 0, len(items))
			for _, item := range items {
				prefixes = append(prefixes, item.prefix)
			}
			matches := getImagesFromBytes(zipData, prefixes)
			for _, item := range items {
				match := matches[item.prefix]
				if match.Err != nil {
					results[item.resultIdx].Err = fmt.Errorf("image %s not found in zip: %w", item.prefix, match.Err)
					continue
				}
				if item.legacy && matchedImageType(match.Name) != "" {
					results[item.resultIdx].Err = fmt.Errorf("unknown image type %q for typed zip entry %s", results[item.resultIdx].ImageType, match.Name)
					continue
				}
				results[item.resultIdx].Data = match.Data
			}
		}(key, items)
	}
	wg.Wait()
	return results
}

func (r *Resolver) loadPatchImages(ctx context.Context, inspection InspectionKey, lookups []patchImageLookup) []patchImageLookupResult {
	_, _, _, _, zips, err := r.getMetaAndZips(ctx, inspection.InspectionTime, inspection.WaferKey)
	if err != nil {
		results := make([]patchImageLookupResult, len(lookups))
		for i, lookup := range lookups {
			results[i] = patchImageLookupResult{
				Index:     lookup.Index,
				DefectID:  lookup.DefectID,
				ImageType: lookup.ImageType,
				Err:       err,
			}
		}
		return results
	}
	return r.getPatchImageBytesBatchFromZips(ctx, zips, lookups)
}

func matchedImageType(name string) string {
	base := filepath.Base(name)
	parts := strings.SplitN(base, "_", 2)
	if len(parts) != 2 {
		return ""
	}
	stem := strings.TrimSuffix(parts[1], filepath.Ext(parts[1]))
	return normalizePatchImageType(stem)
}

func (r *Resolver) getReviewImageBytes(ctx context.Context, inspectionTime string, waferKey int, defectIDStr string, reviewImageID int) ([]byte, error) {
	did, err := parseDefectID(defectIDStr)
	if err != nil {
		return nil, fmt.Errorf("invalid defect_id: %w", err)
	}

	resp, err := r.upstream.GetReviewImageFileSpec(ctx, inspectionTime, int32(waferKey), int32(did), int32(reviewImageID))
	if err != nil {
		return nil, fmt.Errorf("query review image: %w", err)
	}

	bucket, key := parseS3Filespec(resp.ImageFilespec)
	if bucket == "" || key == "" {
		return nil, fmt.Errorf("invalid image_filespec: %s", resp.ImageFilespec)
	}

	return r.getReviewObjectBytes(ctx, bucket, key)
}

func parseS3Filespec(filespec string) (bucket, key string) {
	s := filespec
	if after, ok := strings.CutPrefix(s, "s3://"); ok {
		s = after
	}
	idx := strings.Index(s, "/")
	if idx < 0 {
		return s, ""
	}
	return s[:idx], s[idx+1:]
}

func (r *Resolver) getReviewObjectBytes(ctx context.Context, bucket, key string) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return r.loader.LoadReviewObject(ctx, bucket, key)
}

func (r *Resolver) warmAsync(record, bucket string, keys []string) {
	if r.warmer != nil {
		r.warmer.WarmAsync(record, bucket, keys)
	}
}

func (r *Resolver) WarmInspection(ctx context.Context, inspection InspectionKey, defectIDs []string, recordPrefix string) (int, error) {
	lotID, waferID, device, layerID, err := r.resolveMetadataForWarm(ctx, inspection.InspectionTime, inspection.WaferKey)
	if err != nil {
		return 0, fmt.Errorf("resolve metadata for warm: %w", err)
	}
	allZips, err := r.resolvePatchZipsForWarm(ctx, inspection.InspectionTime, lotID, waferID, device, layerID)
	if err != nil {
		return 0, fmt.Errorf("resolve patch zips for warm: %w", err)
	}

	zipsToWarm := allZips
	if len(defectIDs) > 0 {
		numericIDs := make([]int, 0, len(defectIDs))
		for _, defectID := range defectIDs {
			n, err := parseDefectID(defectID)
			if err != nil {
				continue
			}
			numericIDs = append(numericIDs, n)
		}
		zipsToWarm = filterZipsByDefectIDs(allZips, numericIDs)
	}

	keysByBucket := map[string][]string{}
	for _, ref := range zipsToWarm {
		keysByBucket[ref.Bucket] = append(keysByBucket[ref.Bucket], ref.Key)
	}
	for bucket, keys := range keysByBucket {
		r.warmAsync(
			fmt.Sprintf("%s:%s:%d:%s", recordPrefix, inspection.InspectionTime, inspection.WaferKey, bucket),
			bucket,
			keys,
		)
	}
	return len(zipsToWarm), nil
}

func filterZipsByDefectIDs(zips []cacheZipRef, defectIDs []int) []cacheZipRef {
	seen := make(map[int]bool)
	var result []cacheZipRef
	for _, did := range defectIDs {
		zipIdx := zipIndexForDefect(did)
		if zipIdx < len(zips) && !seen[zipIdx] {
			seen[zipIdx] = true
			result = append(result, zips[zipIdx])
		}
	}
	return result
}

func zipIndexForDefect(defectID int) int {
	if defectID <= 0 {
		return 0
	}
	return (defectID - 1) / defectsPerZip
}
