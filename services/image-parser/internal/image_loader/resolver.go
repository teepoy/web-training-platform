package image_loader

import (
	"context"
	"fmt"
	"strconv"
	"strings"

	"image-parser/internal/sourceformat"
	"image-parser/internal/sourceformat/legacyrangezip"
)

type Resolver struct {
	upstream UpstreamSource
	loader   objectLoader
	patches  *sourceformat.Resolver
}

func newResolver(upstream UpstreamSource, loader objectLoader, patches *sourceformat.Resolver) *Resolver {
	return &Resolver{upstream: upstream, loader: loader, patches: patches}
}

func (r *Resolver) GetImageBytes(ctx context.Context, keys []ImageKey) []ImageBytes {
	results := make([]ImageBytes, len(keys))
	patchesByFormat := map[string][]int{}
	for index, key := range keys {
		results[index] = ImageBytes{Key: key}
		switch key.Kind {
		case ImageKindPatch:
			format := strings.TrimSpace(key.SourceFormat)
			if format == "" {
				format = r.patches.Format()
			}
			patchesByFormat[format] = append(patchesByFormat[format], index)
		case ImageKindReview:
			data, err := r.getReviewImageBytes(
				ctx,
				key.InspectionTime,
				key.WaferKey,
				key.DefectID,
				key.ReviewImageID,
			)
			results[index].Data = data
			results[index].ContentType = "image/jpeg"
			results[index].Err = err
		default:
			results[index].Err = fmt.Errorf("unsupported image kind %q", key.Kind)
		}
	}
	for format, indexes := range patchesByFormat {
		batch := make([]ImageKey, len(indexes))
		for batchIndex, resultIndex := range indexes {
			batch[batchIndex] = keys[resultIndex]
		}
		resolved, err := r.ResolvePatchImageBytes(ctx, format, batch)
		if err != nil {
			for _, resultIndex := range indexes {
				results[resultIndex].Err = err
			}
			continue
		}
		for batchIndex, resultIndex := range indexes {
			results[resultIndex] = resolved[batchIndex]
		}
	}
	return results
}

func (r *Resolver) ResolvePatchImageBytes(ctx context.Context, format string, keys []ImageKey) ([]ImageBytes, error) {
	requests := make([]sourceformat.Request, len(keys))
	for index, key := range keys {
		if key.Kind != ImageKindPatch {
			return nil, fmt.Errorf("ResolvePatchImageBytes only accepts patch image keys")
		}
		requests[index] = sourceformat.Request{
			RequestID: strconv.Itoa(index),
			SampleID:  key.DefectID,
			Roles:     []string{key.ImageType},
			Fields: map[string]string{
				legacyrangezip.FieldInspectionTime: key.InspectionTime,
				legacyrangezip.FieldWaferKey:       strconv.Itoa(key.WaferKey),
				legacyrangezip.FieldDefectID:       key.DefectID,
			},
			RolePaths: key.RolePaths,
		}
	}
	resolved, err := r.patches.Resolve(ctx, format, requests)
	if err != nil {
		return nil, err
	}
	if len(resolved) != len(keys) {
		return nil, fmt.Errorf("source format driver returned %d results for %d keys", len(resolved), len(keys))
	}
	results := make([]ImageBytes, len(keys))
	for index, item := range resolved {
		results[index] = ImageBytes{
			Key:         keys[index],
			Data:        item.Data,
			ContentType: item.ContentType,
			Err:         item.Err,
		}
	}
	return results, nil
}

func parseDefectID(defectID string) (int, error) {
	if number, err := strconv.Atoi(defectID); err == nil {
		return number, nil
	}
	if index := strings.LastIndex(defectID, "-"); index >= 0 {
		return strconv.Atoi(defectID[index+1:])
	}
	return strconv.Atoi(defectID)
}

func (r *Resolver) getReviewImageBytes(ctx context.Context, inspectionTime string, waferKey int, defectID string, reviewImageID int) ([]byte, error) {
	if r.upstream == nil {
		return nil, fmt.Errorf("review image source is not configured for this entrypoint")
	}
	numericDefectID, err := parseDefectID(defectID)
	if err != nil {
		return nil, fmt.Errorf("invalid defect_id: %w", err)
	}
	response, err := r.upstream.GetReviewImageFileSpec(
		ctx,
		inspectionTime,
		int32(waferKey),
		int32(numericDefectID),
		int32(reviewImageID),
	)
	if err != nil {
		return nil, fmt.Errorf("query review image: %w", err)
	}
	bucket, key := parseS3Filespec(response.ImageFilespec)
	if bucket == "" || key == "" {
		return nil, fmt.Errorf("invalid image_filespec: %s", response.ImageFilespec)
	}
	return r.loader.LoadReviewObject(ctx, bucket, key)
}

func parseS3Filespec(filespec string) (bucket, key string) {
	value := filespec
	if withoutScheme, ok := strings.CutPrefix(value, "s3://"); ok {
		value = withoutScheme
	}
	index := strings.Index(value, "/")
	if index < 0 {
		return value, ""
	}
	return value[:index], value[index+1:]
}

func (r *Resolver) WarmInspection(ctx context.Context, inspection InspectionKey, defectIDs []string, _ string) (int, error) {
	if len(defectIDs) == 0 {
		return 0, fmt.Errorf("defect_ids is required for format-aware source warming")
	}
	requests := make([]sourceformat.Request, len(defectIDs))
	for index, defectID := range defectIDs {
		requests[index] = sourceformat.Request{
			RequestID: strconv.Itoa(index),
			Fields: map[string]string{
				legacyrangezip.FieldInspectionTime: inspection.InspectionTime,
				legacyrangezip.FieldWaferKey:       strconv.Itoa(inspection.WaferKey),
				legacyrangezip.FieldDefectID:       defectID,
			},
		}
	}
	if _, err := r.patches.Resolve(ctx, r.patches.Format(), requests); err != nil {
		return 0, err
	}
	return len(defectIDs), nil
}
