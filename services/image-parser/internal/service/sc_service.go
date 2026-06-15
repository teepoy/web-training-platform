package service

import (
	"context"
	"fmt"
	"sort"
	"sync"

	imageparserv1 "image-parser/gen/go/imageparser/v1"
	"image-parser/internal/resolve"
)

const streamLookupBatchSize = 2048

type ScImageService struct {
	imageparserv1.UnimplementedImageParserServer
	resolver *resolve.Resolver
}

func NewScImageService(resolver *resolve.Resolver) *ScImageService {
	return &ScImageService{resolver: resolver}
}

func (s *ScImageService) GetScImage(ctx context.Context, req *imageparserv1.GetScImageRequest) (*imageparserv1.GetScImageResponse, error) {
	imageType := normalizeImageType(req.ImageType)
	contentType := "image/png"

	if imageType == "review" {
		reviewImageID := int(req.ReviewImageId)
		if reviewImageID <= 0 {
			return nil, errMissingParam("review_image_id")
		}
		data, err := s.resolver.GetReviewImage(req.InspectionTime, int(req.WaferKey), req.DefectId, reviewImageID)
		if err != nil {
			return nil, err
		}
		contentType = "image/jpeg"
		return &imageparserv1.GetScImageResponse{ImageData: data, ContentType: contentType}, nil
	}

	data, err := s.resolver.GetPatchImage(req.InspectionTime, int(req.WaferKey), req.DefectId, imageType)
	if err != nil {
		return nil, err
	}
	return &imageparserv1.GetScImageResponse{ImageData: data, ContentType: contentType}, nil
}

func (s *ScImageService) BatchGetScImage(ctx context.Context, req *imageparserv1.BatchGetScImageRequest) (*imageparserv1.BatchGetScImageResponse, error) {
	results := make([]*imageparserv1.ScImageResult, len(req.Images))
	var patchZips []resolve.CacheZipRef
	var patchZipsErr error
	var patchZipsOnce sync.Once
	var wg sync.WaitGroup
	wg.Add(len(req.Images))

	getPatchZips := func() ([]resolve.CacheZipRef, error) {
		patchZipsOnce.Do(func() {
			_, _, _, _, patchZips, patchZipsErr = s.resolver.GetMetaAndZips(req.InspectionTime, int(req.WaferKey))
		})
		return patchZips, patchZipsErr
	}

	for i, img := range req.Images {
		go func(idx int, ref *imageparserv1.ScImageRef) {
			defer wg.Done()
			imageType := normalizeImageType(ref.ImageType)
			contentType := "image/png"
			var data []byte
			var err error

			if imageType == "review" {
				reviewImageID := int(ref.ReviewImageId)
				if reviewImageID <= 0 {
					results[idx] = &imageparserv1.ScImageResult{
						DefectId: ref.DefectId, ImageType: ref.ImageType,
						Error: "missing review_image_id",
					}
					return
				}
				contentType = "image/jpeg"
				data, err = s.resolver.GetReviewImage(req.InspectionTime, int(req.WaferKey), ref.DefectId, reviewImageID)
			} else {
				zips, zipsErr := getPatchZips()
				if zipsErr != nil {
					err = zipsErr
				} else {
					data, err = s.resolver.GetPatchImageFromZips(zips, ref.DefectId, imageType)
				}
			}

			if err != nil {
				results[idx] = &imageparserv1.ScImageResult{
					DefectId: ref.DefectId, ImageType: ref.ImageType,
					Error: err.Error(),
				}
				return
			}
			results[idx] = &imageparserv1.ScImageResult{
				DefectId: ref.DefectId, ImageType: ref.ImageType,
				ImageData: data, ContentType: contentType,
			}
		}(i, img)
	}

	wg.Wait()
	return &imageparserv1.BatchGetScImageResponse{Results: results}, nil
}

func (s *ScImageService) StreamScInspectionImages(req *imageparserv1.StreamScInspectionImagesRequest, stream imageparserv1.ImageParser_StreamScInspectionImagesServer) error {
	defectIDs := append([]int32(nil), req.DefectIds...)
	sort.Slice(defectIDs, func(i, j int) bool { return defectIDs[i] < defectIDs[j] })

	imageTypes := append([]string(nil), req.ImageTypes...)
	if len(imageTypes) == 0 {
		imageTypes = []string{"patch_template", "patch_defective", "patch_difference"}
	}

	_, _, _, _, zips, err := s.resolver.GetMetaAndZips(req.InspectionTime, int(req.WaferKey))
	if err != nil {
		return fmt.Errorf("resolve inspection zips: %w", err)
	}

	warmPatchZips(s.resolver, req.InspectionTime, int(req.WaferKey), zips, defectIDs)

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
		results := s.resolver.GetPatchImagesFromZips(zips, lookups[start:end])
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

func warmPatchZips(resolver *resolve.Resolver, inspectionTime string, waferKey int, zips []resolve.CacheZipRef, defectIDs []int32) {
	if resolver.Warmer == nil || len(defectIDs) == 0 {
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
		resolver.Warmer.WarmAsync(
			fmt.Sprintf("stream:%s:%d:%s", inspectionTime, waferKey, bucket),
			bucket,
			keys,
		)
	}
}

func (s *ScImageService) WarmScCache(ctx context.Context, req *imageparserv1.WarmScCacheRequest) (*imageparserv1.WarmScCacheResponse, error) {
	lotID, waferID, device, layerID, err := s.resolver.ResolveMetadataForWarm(req.InspectionTime, int(req.WaferKey))
	if err != nil {
		return nil, fmt.Errorf("resolve metadata for warm: %w", err)
	}
	allZips, err := s.resolver.ResolvePatchZipsForWarm(req.InspectionTime, lotID, waferID, device, layerID)
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

	if len(zipsToWarm) > 0 && s.resolver.Warmer != nil {
		s.resolver.Warmer.WarmAsync(
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
