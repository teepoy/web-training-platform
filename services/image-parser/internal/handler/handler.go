package handler

import (
	"context"
	"fmt"

	imageloader "image-parser/internal/image_loader"
)

type scRoutes struct {
	images imageloader.ImageLoader
}

type SCImageRequest struct {
	Inspection    imageloader.InspectionKey
	DefectID      string
	ImageType     string
	ReviewImageID int
}

type SCSpriteRequest struct {
	Inspection imageloader.InspectionKey
	DefectID   string
	CellSize   int
	Images     []SCSpriteImage
}

type SCSpriteImage struct {
	Kind          imageloader.ImageKind
	ImageType     string
	ReviewImageID int
}

type SCWarmRequest struct {
	Inspection   imageloader.InspectionKey
	DefectIDs    []string
	RecordPrefix string
}

type ImageResponse struct {
	Data        []byte
	ContentType string
}

type WarmResponse struct {
	Zips int
}

func NewSCRoutes(images imageloader.ImageLoader) *scRoutes {
	return &scRoutes{images: images}
}

func (s *scRoutes) GetSCImage(ctx context.Context, req SCImageRequest) (ImageResponse, error) {
	imageType := normalizeImageType(req.ImageType)
	key := imageloader.ImageKey{
		Kind:          imageloader.ImageKindPatch,
		InspectionKey: req.Inspection,
		DefectID:      req.DefectID,
		ImageType:     imageType,
	}
	contentType := "image/png"
	if imageType == "review" {
		key.Kind = imageloader.ImageKindReview
		key.ReviewImageID = req.ReviewImageID
		contentType = "image/jpeg"
	}

	result := firstImageResult(s.images.GetImageBytes(ctx, []imageloader.ImageKey{key}))
	if result.Err != nil {
		return ImageResponse{}, result.Err
	}
	return ImageResponse{Data: result.Data, ContentType: contentType}, nil
}

func (s *scRoutes) GetSCSprite(ctx context.Context, req SCSpriteRequest) (ImageResponse, error) {
	pngs := make([][]byte, 0, len(req.Images))
	for _, image := range req.Images {
		switch image.Kind {
		case imageloader.ImageKindPatch:
			resized, err := patchSpriteCell(ctx, s.images, req.Inspection, req.DefectID, image.ImageType, req.CellSize)
			if err != nil {
				return ImageResponse{}, err
			}
			pngs = append(pngs, resized)
		case imageloader.ImageKindReview:
			resized, err := reviewSpriteCell(ctx, s.images, req.Inspection, req.DefectID, image.ReviewImageID, req.CellSize)
			if err != nil {
				return ImageResponse{}, err
			}
			pngs = append(pngs, resized)
		default:
			resized, err := blankSquarePNG(req.CellSize)
			if err != nil {
				return ImageResponse{}, err
			}
			pngs = append(pngs, resized)
		}
	}

	result, err := createSpriteFromResized(pngs, req.CellSize)
	if err != nil {
		return ImageResponse{}, err
	}
	return ImageResponse{Data: result, ContentType: "image/png"}, nil
}

func (s *scRoutes) WarmSC(ctx context.Context, req SCWarmRequest) (WarmResponse, error) {
	prefix := req.RecordPrefix
	if prefix == "" {
		prefix = "warm"
	}
	warmed, err := s.images.WarmInspection(ctx, req.Inspection, req.DefectIDs, prefix)
	if err != nil {
		return WarmResponse{}, err
	}
	return WarmResponse{Zips: warmed}, nil
}

func patchSpriteCell(ctx context.Context, images imageloader.ImageLoader, inspection imageloader.InspectionKey, defectID string, imageType string, cellSize int) ([]byte, error) {
	result := firstImageResult(images.GetImageBytes(ctx, []imageloader.ImageKey{{
		Kind:          imageloader.ImageKindPatch,
		InspectionKey: inspection,
		DefectID:      defectID,
		ImageType:     imageType,
	}}))
	if result.Err != nil {
		return blankSquarePNG(cellSize)
	}
	acquireBimg()
	resized, err := resizeSquarePNG(result.Data, cellSize)
	releaseBimg()
	if err != nil {
		return blankSquarePNG(cellSize)
	}
	return resized, nil
}

func reviewSpriteCell(ctx context.Context, images imageloader.ImageLoader, inspection imageloader.InspectionKey, defectID string, reviewImageID int, cellSize int) ([]byte, error) {
	result := firstImageResult(images.GetImageBytes(ctx, []imageloader.ImageKey{{
		Kind:          imageloader.ImageKindReview,
		InspectionKey: inspection,
		DefectID:      defectID,
		ReviewImageID: reviewImageID,
	}}))
	if result.Err != nil {
		return blankSquarePNG(cellSize)
	}
	acquireBimg()
	resized, err := resizeSquarePNG(result.Data, cellSize)
	releaseBimg()
	if err != nil {
		return blankSquarePNG(cellSize)
	}
	return resized, nil
}

func firstImageResult(results []imageloader.ImageBytes) imageloader.ImageBytes {
	if len(results) == 0 {
		return imageloader.ImageBytes{Err: fmt.Errorf("no image result")}
	}
	return results[0]
}
