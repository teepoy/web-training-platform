package service

import (
	"context"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	imageparserv1 "image-parser/gen/go/imageparser/v1"
	imageloader "image-parser/internal/image_loader"
)

const streamLookupBatchSize = 2048

type ScImageService struct {
	imageparserv1.UnimplementedImageParserServer
	images imageloader.ImageLoader
}

type patchImageBatchResolver interface {
	ResolvePatchImageBytes(ctx context.Context, profile string, keys []imageloader.ImageKey) ([]imageloader.ImageBytes, error)
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

func (s *ScImageService) ResolvePatchImages(req *imageparserv1.ResolvePatchImagesRequest, stream imageparserv1.ImageParser_ResolvePatchImagesServer) error {
	response, err := ResolvePatchImagesBatch(stream.Context(), s.images, req)
	if err != nil {
		return err
	}
	for _, result := range response.Results {
		if err := stream.Send(result); err != nil {
			return err
		}
	}
	return nil
}

// ResolvePatchImagesBatch resolves one bounded request while preserving the
// request-item then role order. The gRPC stream and the offline batch process
// deliberately share this implementation so training and prediction cannot
// drift in image-role or correlation semantics.
func ResolvePatchImagesBatch(ctx context.Context, images imageloader.ImageLoader, req *imageparserv1.ResolvePatchImagesRequest) (*imageparserv1.ResolvePatchImagesBatchResponse, error) {
	resolver, ok := images.(patchImageBatchResolver)
	if !ok {
		return nil, status.Error(codes.Internal, "configured image loader does not support source profiles")
	}
	if req == nil {
		return nil, status.Error(codes.InvalidArgument, "request is required")
	}
	profile := strings.TrimSpace(req.SourceProfile)
	if profile == "" {
		return nil, status.Error(codes.InvalidArgument, "source_profile is required")
	}
	if _, err := resolver.ResolvePatchImageBytes(ctx, profile, nil); err != nil {
		return nil, status.Error(codes.InvalidArgument, err.Error())
	}
	roles, err := validatePatchRoles(req.Roles)
	if err != nil {
		return nil, status.Error(codes.InvalidArgument, err.Error())
	}
	if len(req.Items) == 0 {
		return nil, status.Error(codes.InvalidArgument, "items is required")
	}

	type correlation struct {
		item *imageparserv1.ResolvePatchImageItem
		role string
	}
	keys := make([]imageloader.ImageKey, 0, len(req.Items)*len(roles))
	correlations := make([]correlation, 0, len(req.Items)*len(roles))
	requestIDs := make(map[string]struct{}, len(req.Items))
	for _, item := range req.Items {
		if err := validatePatchItem(item); err != nil {
			return nil, status.Error(codes.InvalidArgument, err.Error())
		}
		if _, exists := requestIDs[item.RequestId]; exists {
			return nil, status.Errorf(codes.InvalidArgument, "duplicate request_id %q", item.RequestId)
		}
		requestIDs[item.RequestId] = struct{}{}
		for _, role := range roles {
			keys = append(keys, imageloader.ImageKey{
				Kind:          imageloader.ImageKindPatch,
				SourceProfile: profile,
				InspectionKey: imageloader.InspectionKey{InspectionTime: item.InspectionTime, WaferKey: int(item.WaferKey)},
				DefectID:      item.DefectId,
				ImageType:     role,
			})
			correlations = append(correlations, correlation{item: item, role: role})
		}
	}

	response := &imageparserv1.ResolvePatchImagesBatchResponse{
		Results: make([]*imageparserv1.ResolvePatchImageResult, 0, len(keys)),
	}
	for start := 0; start < len(keys); start += streamLookupBatchSize {
		end := start + streamLookupBatchSize
		if end > len(keys) {
			end = len(keys)
		}
		resolved, err := resolver.ResolvePatchImageBytes(ctx, profile, keys[start:end])
		if err != nil {
			if ctx.Err() != nil {
				return nil, ctx.Err()
			}
			return nil, status.Errorf(codes.Unavailable, "image source profile %q unavailable: %v", profile, err)
		}
		if len(resolved) != end-start {
			return nil, status.Error(codes.Internal, "image resolver returned an unexpected result count")
		}
		for index, image := range resolved {
			correlation := correlations[start+index]
			result := &imageparserv1.ResolvePatchImageResult{
				RequestId:      correlation.item.RequestId,
				SampleId:       correlation.item.SampleId,
				InspectionTime: correlation.item.InspectionTime,
				WaferKey:       correlation.item.WaferKey,
				DefectId:       correlation.item.DefectId,
				Role:           correlation.role,
				ContentType:    image.ContentType,
			}
			if image.Err != nil {
				result.Error = image.Err.Error()
			} else {
				result.ImageData = image.Data
			}
			response.Results = append(response.Results, result)
		}
	}
	return response, nil
}

func validatePatchRoles(rawRoles []string) ([]string, error) {
	if len(rawRoles) == 0 {
		return nil, fmt.Errorf("roles is required")
	}
	roles := make([]string, 0, len(rawRoles))
	seen := make(map[string]struct{}, len(rawRoles))
	for _, rawRole := range rawRoles {
		normalized := imageloader.NormalizeImageType(rawRole)
		var role string
		switch normalized {
		case "Reference":
			role = "patch_template"
		case "Defective":
			role = "patch_defective"
		case "Difference":
			role = "patch_difference"
		default:
			return nil, fmt.Errorf("unsupported patch image role %q", rawRole)
		}
		if _, exists := seen[role]; exists {
			return nil, fmt.Errorf("duplicate patch image role %q", role)
		}
		seen[role] = struct{}{}
		roles = append(roles, role)
	}
	return roles, nil
}

func validatePatchItem(item *imageparserv1.ResolvePatchImageItem) error {
	if item == nil {
		return fmt.Errorf("items cannot contain null entries")
	}
	if strings.TrimSpace(item.RequestId) == "" {
		return fmt.Errorf("item request_id is required")
	}
	if strings.TrimSpace(item.SampleId) == "" {
		return fmt.Errorf("item %q sample_id is required", item.RequestId)
	}
	if item.WaferKey <= 0 {
		return fmt.Errorf("item %q wafer_key must be greater than zero", item.RequestId)
	}
	defectID, err := strconv.Atoi(item.DefectId)
	if err != nil || defectID <= 0 {
		return fmt.Errorf("item %q defect_id must be a positive integer", item.RequestId)
	}
	if !validInspectionTime(item.InspectionTime) {
		return fmt.Errorf("item %q inspection_time must be RFC3339 or YYYYMMDD_HHMMSS", item.RequestId)
	}
	return nil
}

func validInspectionTime(raw string) bool {
	if _, err := time.Parse(time.RFC3339Nano, raw); err == nil {
		return true
	}
	if _, err := time.Parse("2006-01-02T15:04:05", raw); err == nil {
		return true
	}
	_, err := time.Parse("20060102_150405", raw)
	return err == nil
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
