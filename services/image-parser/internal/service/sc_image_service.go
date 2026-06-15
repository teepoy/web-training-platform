package service

import (
	"context"
	"fmt"
	"sort"

	imageparserv1 "image-parser/gen/go/imageparser/v1"
	imageloader "image-parser/internal/image_loader"
)

const streamLookupBatchSize = 2048

type ScImageService struct {
	imageparserv1.UnimplementedImageParserServer
	images imageloader.ImageLoader
}

func NewScImageService(images imageloader.ImageLoader) *ScImageService {
	return &ScImageService{images: images}
}

func (s *ScImageService) GetScImage(ctx context.Context, req *imageparserv1.GetScImageRequest) (*imageparserv1.GetScImageResponse, error) {
	imageType := imageloader.NormalizeImageType(req.ImageType)
	contentType := "image/png"

	if imageType == "review" {
		reviewImageID := int(req.ReviewImageId)
		if reviewImageID <= 0 {
			return nil, errMissingParam("review_image_id")
		}
		result := firstImageResult(s.images.GetImageBytes(ctx, []imageloader.ImageKey{{
			Kind:          imageloader.ImageKindReview,
			InspectionKey: imageloader.InspectionKey{InspectionTime: req.InspectionTime, WaferKey: int(req.WaferKey)},
			DefectID:      req.DefectId,
			ReviewImageID: reviewImageID,
		}}))
		if result.Err != nil {
			return nil, result.Err
		}
		contentType = "image/jpeg"
		return &imageparserv1.GetScImageResponse{ImageData: result.Data, ContentType: contentType}, nil
	}

	result := firstImageResult(s.images.GetImageBytes(ctx, []imageloader.ImageKey{{
		Kind:          imageloader.ImageKindPatch,
		InspectionKey: imageloader.InspectionKey{InspectionTime: req.InspectionTime, WaferKey: int(req.WaferKey)},
		DefectID:      req.DefectId,
		ImageType:     imageType,
	}}))
	if result.Err != nil {
		return nil, result.Err
	}
	return &imageparserv1.GetScImageResponse{ImageData: result.Data, ContentType: contentType}, nil
}

func (s *ScImageService) BatchGetScImage(ctx context.Context, req *imageparserv1.BatchGetScImageRequest) (*imageparserv1.BatchGetScImageResponse, error) {
	keys := make([]imageloader.ImageKey, 0, len(req.Images))

	for _, img := range req.Images {
		imageType := imageloader.NormalizeImageType(img.ImageType)
		if imageType == "review" {
			keys = append(keys, imageloader.ImageKey{
				Kind:          imageloader.ImageKindReview,
				InspectionKey: imageloader.InspectionKey{InspectionTime: req.InspectionTime, WaferKey: int(req.WaferKey)},
				DefectID:      img.DefectId,
				ImageType:     img.ImageType,
				ReviewImageID: int(img.ReviewImageId),
			})
			continue
		}
		keys = append(keys, imageloader.ImageKey{
			Kind:          imageloader.ImageKindPatch,
			InspectionKey: imageloader.InspectionKey{InspectionTime: req.InspectionTime, WaferKey: int(req.WaferKey)},
			DefectID:      img.DefectId,
			ImageType:     imageType,
		})
	}

	loaded := s.images.GetImageBytes(ctx, keys)
	results := make([]*imageparserv1.ScImageResult, len(loaded))
	for i, item := range loaded {
		result := &imageparserv1.ScImageResult{
			DefectId:    item.Key.DefectID,
			ImageType:   item.Key.ImageType,
			ContentType: item.ContentType,
		}
		if item.Err != nil {
			result.Error = item.Err.Error()
		} else {
			result.ImageData = item.Data
		}
		results[i] = result
	}

	return &imageparserv1.BatchGetScImageResponse{Results: results}, nil
}

func (s *ScImageService) StreamScInspectionImages(req *imageparserv1.StreamScInspectionImagesRequest, stream imageparserv1.ImageParser_StreamScInspectionImagesServer) error {
	defectIDs := append([]int32(nil), req.DefectIds...)
	sort.Slice(defectIDs, func(i, j int) bool { return defectIDs[i] < defectIDs[j] })

	imageTypes := append([]string(nil), req.ImageTypes...)
	if len(imageTypes) == 0 {
		imageTypes = []string{"Reference", "Defective", "Difference"}
	}

	warmPatchZips(s.images, req.InspectionTime, int(req.WaferKey), defectIDs)

	keys := make([]imageloader.ImageKey, 0, len(defectIDs)*len(imageTypes))
	for _, defectID := range defectIDs {
		defectIDStr := fmt.Sprintf("%d", defectID)
		for _, requestedType := range imageTypes {
			imageType := imageloader.NormalizeImageType(requestedType)
			keys = append(keys, imageloader.ImageKey{
				Kind:          imageloader.ImageKindPatch,
				InspectionKey: imageloader.InspectionKey{InspectionTime: req.InspectionTime, WaferKey: int(req.WaferKey)},
				DefectID:      defectIDStr,
				ImageType:     imageType,
			})
		}
	}

	for start := 0; start < len(keys); start += streamLookupBatchSize {
		end := start + streamLookupBatchSize
		if end > len(keys) {
			end = len(keys)
		}
		results := s.images.GetImageBytes(stream.Context(), keys[start:end])
		for _, resolved := range results {
			result := &imageparserv1.ScImageResult{
				DefectId:    resolved.Key.DefectID,
				ImageType:   resolved.Key.ImageType,
				ContentType: resolved.ContentType,
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

func warmPatchZips(images imageloader.ImageLoader, inspectionTime string, waferKey int, defectIDs []int32) {
	if len(defectIDs) == 0 {
		return
	}
	defectIDStrings := make([]string, 0, len(defectIDs))
	for _, defectID := range defectIDs {
		defectIDStrings = append(defectIDStrings, fmt.Sprintf("%d", defectID))
	}
	_, _ = images.WarmInspection(context.Background(), imageloader.InspectionKey{InspectionTime: inspectionTime, WaferKey: waferKey}, defectIDStrings, "stream")
}

func (s *ScImageService) WarmScCache(ctx context.Context, req *imageparserv1.WarmScCacheRequest) (*imageparserv1.WarmScCacheResponse, error) {
	defectIDs := make([]string, 0, len(req.DefectIds))
	for _, defectID := range req.DefectIds {
		defectIDs = append(defectIDs, fmt.Sprintf("%d", defectID))
	}
	warmed, err := s.images.WarmInspection(ctx, imageloader.InspectionKey{InspectionTime: req.InspectionTime, WaferKey: int(req.WaferKey)}, defectIDs, "warm")
	if err != nil {
		return nil, err
	}

	return &imageparserv1.WarmScCacheResponse{
		Status:     "warming",
		ZipsWarmed: int32(warmed),
	}, nil
}

func firstImageResult(results []imageloader.ImageBytes) imageloader.ImageBytes {
	if len(results) == 0 {
		return imageloader.ImageBytes{Err: fmt.Errorf("no image result")}
	}
	return results[0]
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
