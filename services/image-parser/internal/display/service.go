package display

import (
	"context"
	"fmt"
	"strconv"
	"strings"
	"sync/atomic"

	"image-parser/internal/imagestream"
)

type Service struct {
	upstream      UpstreamSource
	reviewObjects ReviewObjectStore
	streams       imagestream.Engine
	nextID        atomic.Uint64
}

func (r *Service) GetImageBytes(ctx context.Context, keys []ImageKey) []ImageBytes {
	results := make([]ImageBytes, len(keys))
	patchIndexes := make([]int, 0, len(keys))
	for index, key := range keys {
		results[index] = ImageBytes{Key: key}
		switch key.Kind {
		case ImageKindPatch:
			patchIndexes = append(patchIndexes, index)
		case ImageKindReview:
			data, err := r.getReviewImageBytes(ctx, key.InspectionTime, key.WaferKey, key.DefectID, key.ReviewImageID)
			results[index].Data = data
			results[index].ContentType = "image/jpeg"
			results[index].Err = err
		default:
			results[index].Err = fmt.Errorf("unsupported image kind %q", key.Kind)
		}
	}
	if len(patchIndexes) == 0 {
		return results
	}
	patchKeys := make([]ImageKey, len(patchIndexes))
	for index, resultIndex := range patchIndexes {
		patchKeys[index] = keys[resultIndex]
	}
	resolved := r.resolvePatchImageBytes(ctx, patchKeys)
	for index, resultIndex := range patchIndexes {
		results[resultIndex] = resolved[index]
	}
	return results
}

type patchGroupKey struct {
	inspectionTime string
	waferKey       int
	role           string
}

func (r *Service) resolvePatchImageBytes(ctx context.Context, keys []ImageKey) []ImageBytes {
	results := make([]ImageBytes, len(keys))
	groups := make(map[patchGroupKey][]int)
	for index, key := range keys {
		results[index] = ImageBytes{Key: key}
		if key.Kind != ImageKindPatch {
			results[index].Err = fmt.Errorf("patch resolver only accepts patch image keys")
			continue
		}
		role := NormalizeImageType(key.ImageType)
		if strings.TrimSpace(role) == "" {
			results[index].Err = fmt.Errorf("patch image role is required")
			continue
		}
		group := patchGroupKey{key.InspectionTime, key.WaferKey, role}
		groups[group] = append(groups[group], index)
	}
	for group, indexes := range groups {
		contextID := fmt.Sprintf("display-%d", r.nextID.Add(1))
		opened, err := r.streams.Open(ctx, imagestream.UseCaseDisplay, imagestream.OpenRequest{
			ContextID: contextID, InspectionTime: group.inspectionTime, WaferKey: int32(group.waferKey), Roles: []string{group.role},
		})
		if err != nil {
			for _, index := range indexes {
				results[index].Err = err
			}
			continue
		}
		requests := make([]imagestream.SampleRequest, len(indexes))
		for requestIndex, index := range indexes {
			requests[requestIndex] = imagestream.SampleRequest{Sequence: uint64(requestIndex + 1), SampleID: keys[index].DefectID, DefectID: keys[index].DefectID}
		}
		resolved, resolveErr := opened.Resolve(ctx, requests)
		closeErr := opened.Close()
		if resolveErr != nil || closeErr != nil {
			if resolveErr == nil {
				resolveErr = closeErr
			}
			for _, index := range indexes {
				results[index].Err = resolveErr
			}
			continue
		}
		if len(resolved) != len(requests) {
			for _, index := range indexes {
				results[index].Err = fmt.Errorf("equipment entry returned %d samples for %d requests", len(resolved), len(requests))
			}
			continue
		}
		bySequence := make(map[uint64]imagestream.SampleResult, len(resolved))
		for _, item := range resolved {
			bySequence[item.Sequence] = item
		}
		for requestIndex, index := range indexes {
			item, ok := bySequence[uint64(requestIndex+1)]
			if !ok || len(item.Images) != 1 {
				results[index].Err = fmt.Errorf("equipment entry returned an incomplete image result")
				continue
			}
			results[index].Data = item.Images[0].Data
			results[index].ContentType = item.Images[0].ContentType
			results[index].Err = item.Err
			if results[index].Err == nil {
				results[index].Err = item.Images[0].Err
			}
		}
	}
	return results
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

func (r *Service) getReviewImageBytes(ctx context.Context, inspectionTime string, waferKey int, defectID string, reviewImageID int) ([]byte, error) {
	numericDefectID, err := parseDefectID(defectID)
	if err != nil {
		return nil, fmt.Errorf("invalid defect_id: %w", err)
	}
	response, err := r.upstream.GetReviewImageFileSpec(ctx, inspectionTime, int32(waferKey), int32(numericDefectID), int32(reviewImageID))
	if err != nil {
		return nil, fmt.Errorf("query review image: %w", err)
	}
	bucket, key := parseS3Filespec(response.ImageFilespec)
	if bucket == "" || key == "" {
		return nil, fmt.Errorf("invalid image_filespec: %s", response.ImageFilespec)
	}
	return r.reviewObjects.ReadObject(ctx, bucket, key)
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
