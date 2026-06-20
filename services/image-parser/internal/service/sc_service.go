package service

import (
	"context"
	"fmt"
	"sort"

	imageparserv1 "image-parser/gen/go/imageparser/v1"
	"image-parser/internal/resolve"
)

const streamLookupBatchSize = 2048

type ScImageService struct {
	imageparserv1.UnimplementedImageParserServer
	images resolve.ImageBytesSource
}

func NewScImageService(images resolve.ImageBytesSource) *ScImageService {
	return &ScImageService{images: images}
}

func (s *ScImageService) GetScImage(ctx context.Context, req *imageparserv1.GetScImageRequest) (*imageparserv1.GetScImageResponse, error) {
	imageType := normalizeImageType(req.ImageType)
	contentType := "image/png"

	if imageType == "review" {
		reviewImageID := int(req.ReviewImageId)
		if reviewImageID <= 0 {
			return nil, errMissingParam("review_image_id")
		}
		data, err := s.images.GetReviewImageBytes(ctx, req.InspectionTime, int(req.WaferKey), req.DefectId, reviewImageID)
		if err != nil {
			return nil, err
		}
		contentType = "image/jpeg"
		return &imageparserv1.GetScImageResponse{ImageData: data, ContentType: contentType}, nil
	}

	data, err := s.images.GetPatchImageBytes(ctx, req.InspectionTime, int(req.WaferKey), req.DefectId, imageType)
	if err != nil {
		return nil, err
	}
	return &imageparserv1.GetScImageResponse{ImageData: data, ContentType: contentType}, nil
}

func (s *ScImageService) BatchGetScImage(ctx context.Context, req *imageparserv1.BatchGetScImageRequest) (*imageparserv1.BatchGetScImageResponse, error) {
	results := make([]*imageparserv1.ScImageResult, len(req.Images))
	patchLookups := make([]resolve.PatchImageLookup, 0, len(req.Images))
	requestedImageTypes := make(map[int]string, len(req.Images))

	for i, img := range req.Images {
		imageType := normalizeImageType(img.ImageType)
		if imageType != "review" {
			requestedImageTypes[i] = img.ImageType
			patchLookups = append(patchLookups, resolve.PatchImageLookup{
				Index:     i,
				DefectID:  img.DefectId,
				ImageType: imageType,
			})
			continue
		}

		reviewImageID := int(img.ReviewImageId)
		if reviewImageID <= 0 {
			results[i] = &imageparserv1.ScImageResult{
				DefectId: img.DefectId, ImageType: img.ImageType,
				Error: "missing review_image_id",
			}
			continue
		}
		data, err := s.images.GetReviewImageBytes(ctx, req.InspectionTime, int(req.WaferKey), img.DefectId, reviewImageID)
		if err != nil {
			results[i] = &imageparserv1.ScImageResult{
				DefectId: img.DefectId, ImageType: img.ImageType,
				Error: err.Error(),
			}
			continue
		}
		results[i] = &imageparserv1.ScImageResult{
			DefectId: img.DefectId, ImageType: img.ImageType,
			ImageData: data, ContentType: "image/jpeg",
		}
	}

	if len(patchLookups) > 0 {
		_, _, _, _, patchZips, err := s.images.GetMetaAndZips(ctx, req.InspectionTime, int(req.WaferKey))
		if err != nil {
			for _, lookup := range patchLookups {
				results[lookup.Index] = &imageparserv1.ScImageResult{
					DefectId: lookup.DefectID, ImageType: requestedImageTypes[lookup.Index],
					Error: err.Error(),
				}
			}
		} else {
			resolved := s.images.GetPatchImageBytesBatchFromZips(ctx, patchZips, patchLookups)
			for _, item := range resolved {
				result := &imageparserv1.ScImageResult{
					DefectId:    item.DefectID,
					ImageType:   requestedImageTypes[item.Index],
					ContentType: "image/png",
				}
				if item.Err != nil {
					result.Error = item.Err.Error()
				} else {
					result.ImageData = item.Data
				}
				results[item.Index] = result
			}
		}
	}

	return &imageparserv1.BatchGetScImageResponse{Results: results}, nil
}

func (s *ScImageService) StreamScInspectionImages(req *imageparserv1.StreamScInspectionImagesRequest, stream imageparserv1.ImageParser_StreamScInspectionImagesServer) error {
	defectIDs := append([]int32(nil), req.DefectIds...)
	sort.Slice(defectIDs, func(i, j int) bool { return defectIDs[i] < defectIDs[j] })

	imageTypes := append([]string(nil), req.ImageTypes...)
	if len(imageTypes) == 0 {
		imageTypes = []string{"patch_template", "patch_defective", "patch_difference"}
	}

	_, _, _, _, zips, err := s.images.GetMetaAndZips(stream.Context(), req.InspectionTime, int(req.WaferKey))
	if err != nil {
		return fmt.Errorf("resolve inspection zips: %w", err)
	}

	warmPatchZips(s.images, req.InspectionTime, int(req.WaferKey), zips, defectIDs)

	lookups := make([]resolve.PatchImageLookup, 0, len(defectIDs)*len(imageTypes))
	requestedTypeByIndex := make(map[int]string, len(defectIDs)*len(imageTypes))
	idx := 0
	for _, defectID := range defectIDs {
		defectIDStr := fmt.Sprintf("%d", defectID)
		for _, requestedType := range imageTypes {
			requestedTypeByIndex[idx] = requestedType
			lookups = append(lookups, resolve.PatchImageLookup{
				Index:     idx,
				DefectID:  defectIDStr,
				ImageType: normalizeImageType(requestedType),
			})
			idx++
		}
	}

	for start := 0; start < len(lookups); start += streamLookupBatchSize {
		end := start + streamLookupBatchSize
		if end > len(lookups) {
			end = len(lookups)
		}
		results := s.images.GetPatchImageBytesBatchFromZips(stream.Context(), zips, lookups[start:end])
		sort.Slice(results, func(i, j int) bool { return results[i].Index < results[j].Index })
		for _, resolved := range results {
			result := &imageparserv1.ScImageResult{
				DefectId:    resolved.DefectID,
				ImageType:   requestedTypeByIndex[resolved.Index],
				ContentType: "image/png",
			}
			if resolved.Err != nil {
				result.Error = resolved.Err.Error()
			} else {
				result.ImageData = resolved.Data
			}
			if err := stream.Context().Err(); err != nil {
				return err
			}
			if err := stream.Send(result); err != nil {
				return err
			}
		}
	}
	return nil
}

func warmPatchZips(images resolve.ImageBytesSource, inspectionTime string, waferKey int, zips []resolve.CacheZipRef, defectIDs []int32) {
	if len(defectIDs) == 0 {
		return
	}
	numericIDs := make([]int, 0, len(defectIDs))
	for _, defectID := range defectIDs {
		numericIDs = append(numericIDs, int(defectID))
	}
	zipsToWarm := resolve.FilterZipsByDefectIDs(zips, numericIDs)
	keysByBucket := map[string][]string{}
	for _, ref := range zipsToWarm {
		keysByBucket[ref.Bucket] = append(keysByBucket[ref.Bucket], ref.Key)
	}
	for bucket, keys := range keysByBucket {
		images.WarmAsync(
			fmt.Sprintf("stream:%s:%d:%s", inspectionTime, waferKey, bucket),
			bucket,
			keys,
		)
	}
}

func (s *ScImageService) WarmScCache(ctx context.Context, req *imageparserv1.WarmScCacheRequest) (*imageparserv1.WarmScCacheResponse, error) {
	lotID, waferID, device, layerID, err := s.images.ResolveMetadataForWarm(ctx, req.InspectionTime, int(req.WaferKey))
	if err != nil {
		return nil, fmt.Errorf("resolve metadata for warm: %w", err)
	}
	allZips, err := s.images.ResolvePatchZipsForWarm(ctx, req.InspectionTime, lotID, waferID, device, layerID)
	if err != nil {
		return nil, fmt.Errorf("resolve patch zips for warm: %w", err)
	}

	var zipsToWarm []resolve.CacheZipRef
	if len(req.DefectIds) > 0 {
		numericIDs := make([]int, len(req.DefectIds))
		for i, d := range req.DefectIds {
			num, err := resolve.ParseDefectID(fmt.Sprintf("%d", d))
			if err != nil {
				numericIDs[i] = 0
			} else {
				numericIDs[i] = num
			}
		}
		zipsToWarm = resolve.FilterZipsByDefectIDs(allZips, numericIDs)
	} else {
		zipsToWarm = allZips
	}

	keys := make([]string, len(zipsToWarm))
	for i, ref := range zipsToWarm {
		keys[i] = ref.Key
	}

	if len(zipsToWarm) > 0 {
		s.images.WarmAsync(
			fmt.Sprintf("warm:%s:%d", req.InspectionTime, req.WaferKey),
			zipsToWarm[0].Bucket,
			keys,
		)
	}

	return &imageparserv1.WarmScCacheResponse{
		Status:     "warming",
		ZipsWarmed: int32(len(keys)),
	}, nil
}

func normalizeImageType(imageType string) string {
	switch imageType {
	case "PATCH_TEMPLATE", "patch_template":
		return "template"
	case "PATCH_DEFECTIVE", "patch_defective":
		return "defective"
	case "PATCH_DIFFERENCE", "patch_difference", "difference":
		return "difference"
	case "REVIEW_HIGH_MAG", "review_high_mag":
		return "review"
	default:
		return imageType
	}
}

func errMissingParam(name string) error {
	return fmt.Errorf("required parameter %s is missing or invalid", name)
}

func (s *ScImageService) Health(ctx context.Context, req *imageparserv1.HealthRequest) (*imageparserv1.HealthResponse, error) {
	return &imageparserv1.HealthResponse{Status: "ok"}, nil
}

func (s *ScImageService) GetImage(ctx context.Context, req *imageparserv1.GetImageRequest) (*imageparserv1.GetImageResponse, error) {
	return nil, nil
}

func (s *ScImageService) Sprite(ctx context.Context, req *imageparserv1.SpriteRequest) (*imageparserv1.SpriteResponse, error) {
	return nil, nil
}

func (s *ScImageService) V2Sprite(ctx context.Context, req *imageparserv1.V2SpriteRequest) (*imageparserv1.V2SpriteResponse, error) {
	return nil, nil
}
