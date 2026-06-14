package service

import (
	"context"
	"strconv"

	imageparserv1 "ft-platform/protos/gen/go/imageparser/v1"
	"image-parser/internal/resolve"
)

type ScImageService struct {
	imageparserv1.UnimplementedImageParserServer
	resolver *resolve.Resolver
}

func NewScImageService(resolver *resolve.Resolver) *ScImageService {
	return &ScImageService{resolver: resolver}
}

func (s *ScImageService) GetScImage(ctx context.Context, req *imageparserv1.GetScImageRequest) (*imageparserv1.GetScImageResponse, error) {
	imageType := req.ImageType
	contentType := "image/png"

	if imageType == "review" || imageType == "REVIEW_HIGH_MAG" {
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

func errMissingParam(name string) error {
	return strconv.ErrSyntax
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
