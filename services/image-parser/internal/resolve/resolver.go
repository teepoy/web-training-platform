package resolve

import (
	"context"
	"fmt"
	"strconv"
	"strings"

	"image-parser/internal/client"
	"image-parser/internal/cache"
	"image-parser/internal/s3client"
	"image-parser/internal/zipreader"
)

const defectsPerZip = 500

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

	prefix := fmt.Sprintf("%06d", did)

	ck := cache.CacheKey(ref.Bucket, ref.Key)
	zipData, err := r.ZipCache.GetOrLoad(ck, func() ([]byte, error) {
		return zipreader.DownloadFullZip(s3client.Get(), ref.Bucket, ref.Key)
	})
	if err != nil {
		return nil, fmt.Errorf("download zip: %w", err)
	}

	imgData, _, err := zipreader.GetImageFromBytes(zipData, prefix)
	if err != nil {
		newPrefix := fmt.Sprintf("Defect%06d_%s", did, imageType)
		imgData, _, err = zipreader.GetImageFromBytes(zipData, newPrefix)
		if err != nil {
			return nil, fmt.Errorf("image %s not found in zip", prefix)
		}
	}

	return imgData, nil
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
	cli := s3client.Get()
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
