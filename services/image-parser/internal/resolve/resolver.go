package resolve

import (
	"context"
	"fmt"
	"path/filepath"
	"strconv"
	"strings"
	"sync"

	"image-parser/internal/cache"
	"image-parser/internal/client"
	"image-parser/internal/s3client"
	"image-parser/internal/zipreader"
)

const defectsPerZip = 500
const patchZipWorkerLimit = 8

type Resolver struct {
	upstream *client.UpstreamClient
	ZipCache *cache.ZipCache
	Warmer   *cache.Warmer
}

func New(upstream *client.UpstreamClient, zipCache *cache.ZipCache, warmer *cache.Warmer) *Resolver {
	return &Resolver{
		upstream: upstream,
		ZipCache: zipCache,
		Warmer:   warmer,
	}
}

func ParseDefectID(defectID string) (int, error) {
	if n, err := strconv.Atoi(defectID); err == nil {
		return n, nil
	}
	i := strings.LastIndex(defectID, "-")
	if i >= 0 {
		return strconv.Atoi(defectID[i+1:])
	}
	return strconv.Atoi(defectID)
}

func (r *Resolver) ResolveMetadataForWarm(inspectionTime string, waferKey int) (lotID, waferID, device, layerID string, err error) {
	resp, err := r.upstream.GetInspection(context.Background(), inspectionTime, int32(waferKey))
	if err != nil {
		return "", "", "", "", fmt.Errorf("get inspection: %w", err)
	}
	return resp.LotId, resp.WaferId, resp.Device, resp.LayerId, nil
}

func (r *Resolver) ResolvePatchZipsForWarm(inspectionTime, lotID, waferID, device, layerID string) ([]CacheZipRef, error) {
	resp, err := r.upstream.GetInspectionPatchZips(context.Background(), inspectionTime, lotID, waferID, device, layerID)
	if err != nil {
		return nil, fmt.Errorf("get zips: %w", err)
	}
	var refs []CacheZipRef
	for _, z := range resp.Zips {
		refs = append(refs, CacheZipRef{Bucket: z.S3Bucket, Key: z.S3Key})
	}
	return refs, nil
}

type CacheZipRef struct {
	Bucket string
	Key    string
}

type PatchImageLookup struct {
	Index     int
	DefectID  string
	ImageType string
}

type PatchImageLookupResult struct {
	Index     int
	DefectID  string
	ImageType string
	Data      []byte
	Err       error
}

func locateZipForDefect(zips []CacheZipRef, defectID int) (*CacheZipRef, error) {
	zipIdx := defectID / defectsPerZip
	if zipIdx >= len(zips) {
		return nil, fmt.Errorf("defect %d out of range (zip_idx=%d, total_zips=%d)", defectID, zipIdx, len(zips))
	}
	return &zips[zipIdx], nil
}

func (r *Resolver) GetPatchImage(inspectionTime string, waferKey int, defectIDStr string, imageType string) ([]byte, error) {
	did, err := ParseDefectID(defectIDStr)
	if err != nil {
		return nil, fmt.Errorf("invalid defect_id: %w", err)
	}

	meta, err := r.upstream.GetInspection(context.Background(), inspectionTime, int32(waferKey))
	if err != nil {
		return nil, fmt.Errorf("resolve metadata: %w", err)
	}

	zipsResp, err := r.upstream.GetInspectionPatchZips(context.Background(), inspectionTime, meta.LotId, meta.WaferId, meta.Device, meta.LayerId)
	if err != nil {
		return nil, fmt.Errorf("resolve zips: %w", err)
	}

	var zips []CacheZipRef
	for _, z := range zipsResp.Zips {
		zips = append(zips, CacheZipRef{Bucket: z.S3Bucket, Key: z.S3Key})
	}

	ref, err := locateZipForDefect(zips, did)
	if err != nil {
		return nil, fmt.Errorf("locate zip: %w", err)
	}

	ck := cache.CacheKey(ref.Bucket, ref.Key)
	zipData, err := r.ZipCache.GetOrLoad(ck, func() ([]byte, error) {
		return zipreader.DownloadFullZip(s3client.GetZips(), ref.Bucket, ref.Key)
	})
	if err != nil {
		return nil, fmt.Errorf("download zip: %w", err)
	}

	prefix, ok := PatchImagePrefix(did, imageType)
	if ok {
		imgData, _, err := zipreader.GetImageFromBytes(zipData, prefix)
		if err == nil {
			return imgData, nil
		}
		return nil, fmt.Errorf("image %s not found in zip: %w", prefix, err)
	}
	legacyPrefix := fmt.Sprintf("%06d", did)
	imgData, matchedName, err := zipreader.GetImageFromBytes(zipData, legacyPrefix)
	if err != nil {
		return nil, fmt.Errorf("image %s not found in zip", legacyPrefix)
	}
	if matchedImageType(matchedName) != "" {
		return nil, fmt.Errorf("unknown image type %q for typed zip entry %s", imageType, matchedName)
	}
	return imgData, nil
}

func PatchImagePrefix(defectID int, imageType string) (string, bool) {
	switch normalizePatchImageType(imageType) {
	case "template":
		return fmt.Sprintf("%06d_PatchTemplate", defectID), true
	case "defective":
		return fmt.Sprintf("%06d_PatchDefective", defectID), true
	case "difference":
		return fmt.Sprintf("%06d_PatchDifference", defectID), true
	default:
		return "", false
	}
}

func normalizePatchImageType(imageType string) string {
	switch strings.ToLower(strings.TrimSpace(imageType)) {
	case "patch_template", "template", "patchtemplate":
		return "template"
	case "patch_defective", "defective", "patchdefective":
		return "defective"
	case "patch_difference", "difference", "patchdifference":
		return "difference"
	default:
		return strings.ToLower(strings.TrimSpace(imageType))
	}
}

func (r *Resolver) GetMetaAndZips(inspectionTime string, waferKey int) (lotID, waferID, device, layerID string, zips []CacheZipRef, err error) {
	meta, err := r.upstream.GetInspection(context.Background(), inspectionTime, int32(waferKey))
	if err != nil {
		return "", "", "", "", nil, fmt.Errorf("resolve metadata: %w", err)
	}
	m := meta
	zipsResp, err := r.upstream.GetInspectionPatchZips(context.Background(), inspectionTime, m.LotId, m.WaferId, m.Device, m.LayerId)
	if err != nil {
		return "", "", "", "", nil, fmt.Errorf("resolve zips: %w", err)
	}
	for _, z := range zipsResp.Zips {
		zips = append(zips, CacheZipRef{Bucket: z.S3Bucket, Key: z.S3Key})
	}
	return m.LotId, m.WaferId, m.Device, m.LayerId, zips, nil
}

func (r *Resolver) GetPatchImageFromZips(zips []CacheZipRef, defectIDStr string, imageType string) ([]byte, error) {
	did, err := ParseDefectID(defectIDStr)
	if err != nil {
		return nil, fmt.Errorf("invalid defect_id: %w", err)
	}
	ref, err := locateZipForDefect(zips, did)
	if err != nil {
		return nil, fmt.Errorf("locate zip: %w", err)
	}
	ck := cache.CacheKey(ref.Bucket, ref.Key)
	zipData, err := r.ZipCache.GetOrLoad(ck, func() ([]byte, error) {
		return zipreader.DownloadFullZip(s3client.GetZips(), ref.Bucket, ref.Key)
	})
	if err != nil {
		return nil, fmt.Errorf("download zip: %w", err)
	}
	prefix, ok := PatchImagePrefix(did, imageType)
	if ok {
		imgData, _, err := zipreader.GetImageFromBytes(zipData, prefix)
		if err == nil {
			return imgData, nil
		}
		return nil, fmt.Errorf("image %s not found in zip: %w", prefix, err)
	}
	legacyPrefix := fmt.Sprintf("%06d", did)
	imgData, matchedName, err := zipreader.GetImageFromBytes(zipData, legacyPrefix)
	if err != nil {
		return nil, fmt.Errorf("image %s not found in zip", legacyPrefix)
	}
	if matchedImageType(matchedName) != "" {
		return nil, fmt.Errorf("unknown image type %q for typed zip entry %s", imageType, matchedName)
	}
	return imgData, nil
}

func (r *Resolver) GetPatchImagesFromZips(zips []CacheZipRef, lookups []PatchImageLookup) []PatchImageLookupResult {
	results := make([]PatchImageLookupResult, len(lookups))
	type zipLookup struct {
		resultIdx int
		prefix    string
		legacy    bool
	}
	grouped := map[string][]zipLookup{}
	refs := map[string]CacheZipRef{}

	for i, lookup := range lookups {
		results[i] = PatchImageLookupResult{
			Index:     lookup.Index,
			DefectID:  lookup.DefectID,
			ImageType: lookup.ImageType,
		}
		did, err := ParseDefectID(lookup.DefectID)
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
		prefix, ok := PatchImagePrefix(did, lookup.ImageType)
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

			ref := refs[key]
			zipData, err := r.ZipCache.GetOrLoad(key, func() ([]byte, error) {
				return zipreader.DownloadFullZip(s3client.GetZips(), ref.Bucket, ref.Key)
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
			matches := zipreader.GetImagesFromBytes(zipData, prefixes)
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

func matchedImageType(name string) string {
	base := filepath.Base(name)
	parts := strings.SplitN(base, "_", 2)
	if len(parts) != 2 {
		return ""
	}
	stem := strings.TrimSuffix(parts[1], filepath.Ext(parts[1]))
	return normalizePatchImageType(stem)
}

func (r *Resolver) GetReviewImage(inspectionTime string, waferKey int, defectIDStr string, reviewImageID int) ([]byte, error) {
	did, err := ParseDefectID(defectIDStr)
	if err != nil {
		return nil, fmt.Errorf("invalid defect_id: %w", err)
	}

	resp, err := r.upstream.GetReviewImageFileSpec(context.Background(), inspectionTime, int32(waferKey), int32(did), int32(reviewImageID))
	if err != nil {
		return nil, fmt.Errorf("query review image: %w", err)
	}

	bucket, key := parseS3Filespec(resp.ImageFilespec)
	if bucket == "" || key == "" {
		return nil, fmt.Errorf("invalid image_filespec: %s", resp.ImageFilespec)
	}

	return GetRawS3Object(bucket, key)
}

func (r *Resolver) GetReviewImages(inspectionTime string, waferKey int, defectIDStr string) ([]string, error) {
	did, err := ParseDefectID(defectIDStr)
	if err != nil {
		return nil, fmt.Errorf("invalid defect_id: %w", err)
	}

	resp, err := r.upstream.ListReviewImages(context.Background(), inspectionTime, int32(waferKey), int32(did))
	if err != nil {
		return nil, fmt.Errorf("list review images: %w", err)
	}

	var specs []string
	for _, img := range resp.Images {
		specs = append(specs, img.ImageFilespec)
	}
	return specs, nil
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

func GetRawS3Object(bucket, key string) ([]byte, error) {
	cli := s3client.GetReview()
	return zipreader.DownloadFullZip(cli, bucket, key)
}

func (r *Resolver) GetPatchZipKeys(inspectionTime string, waferKey int) ([]CacheZipRef, error) {
	meta, err := r.upstream.GetInspection(context.Background(), inspectionTime, int32(waferKey))
	if err != nil {
		return nil, err
	}

	resp, err := r.upstream.GetInspectionPatchZips(context.Background(), inspectionTime, meta.LotId, meta.WaferId, meta.Device, meta.LayerId)
	if err != nil {
		return nil, err
	}

	var refs []CacheZipRef
	for _, z := range resp.Zips {
		refs = append(refs, CacheZipRef{Bucket: z.S3Bucket, Key: z.S3Key})
	}
	return refs, nil
}

func FilterZipsByDefectIDs(zips []CacheZipRef, defectIDs []int) []CacheZipRef {
	seen := make(map[int]bool)
	var result []CacheZipRef
	for _, did := range defectIDs {
		zipIdx := did / defectsPerZip
		if zipIdx < len(zips) && !seen[zipIdx] {
			seen[zipIdx] = true
			result = append(result, zips[zipIdx])
		}
	}
	return result
}
