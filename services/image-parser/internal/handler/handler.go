package handler

import (
	"context"
	"fmt"

	"image-parser/internal/display"
	"image-parser/internal/equipment"
)

type scRoutes struct {
	images    display.Reader
	downloads *GalleryDownloadService
	profiles  equipment.ImageProfiler
}

type SCImageRequest struct {
	Inspection    display.InspectionKey
	DefectID      string
	ImageType     string
	ReviewImageID int
}

type SCSpriteRequest struct {
	Inspection   display.InspectionKey
	DefectID     string
	CellSize     int
	Images       []SCSpriteImage
	GrayMappings PatchGrayMappings
}

type SCSpriteImage struct {
	Kind          display.ImageKind
	ImageType     string
	ReviewImageID int
}

type ImageResponse struct {
	Data        []byte
	ContentType string
}

func NewSCRoutes(images display.Reader) *scRoutes {
	return &scRoutes{images: images}
}

func NewSCRoutesWithGalleryDownloads(images display.Reader, downloads *GalleryDownloadService) *scRoutes {
	return &scRoutes{images: images, downloads: downloads}
}

func NewSCRoutesWithGalleryDownloadsAndProfiles(
	images display.Reader,
	downloads *GalleryDownloadService,
	profiles equipment.ImageProfiler,
) *scRoutes {
	return &scRoutes{images: images, downloads: downloads, profiles: profiles}
}

func (s *scRoutes) GetSCInspectionImageProfile(
	ctx context.Context,
	inspectionTime string,
	waferKey int32,
) (equipment.InspectionImageProfile, error) {
	if s.profiles == nil {
		return equipment.InspectionImageProfile{}, fmt.Errorf("inspection image profiles are not configured")
	}
	return s.profiles.Profile(ctx, inspectionTime, waferKey)
}

func (s *scRoutes) CreateSCGalleryDownload(ctx context.Context, req GalleryDownloadRequest) (GalleryDownloadResult, error) {
	if s.downloads == nil {
		return GalleryDownloadResult{}, fmt.Errorf("gallery image downloads are not configured")
	}
	return s.downloads.Create(ctx, req)
}

func (s *scRoutes) GetSCImage(ctx context.Context, req SCImageRequest) (ImageResponse, error) {
	imageType := normalizeImageType(req.ImageType)
	key := display.ImageKey{
		Kind:          display.ImageKindPatch,
		InspectionKey: req.Inspection,
		DefectID:      req.DefectID,
		ImageType:     imageType,
	}
	if imageType == "review" {
		key.Kind = display.ImageKindReview
		key.ReviewImageID = req.ReviewImageID
	}

	result := firstImageResult(s.images.GetImageBytes(ctx, []display.ImageKey{key}))
	if result.Err != nil {
		return ImageResponse{}, result.Err
	}
	return ImageResponse{Data: result.Data, ContentType: result.ContentType}, nil
}

func (s *scRoutes) GetSCSprite(ctx context.Context, req SCSpriteRequest) (ImageResponse, error) {
	pngs := make([][]byte, 0, len(req.Images))
	for _, image := range req.Images {
		switch image.Kind {
		case display.ImageKindPatch:
			resized, err := patchSpriteCell(ctx, s.images, req.Inspection, req.DefectID, image.ImageType, req.CellSize, req.GrayMappings.ForImageType(image.ImageType))
			if err != nil {
				return ImageResponse{}, err
			}
			pngs = append(pngs, resized)
		case display.ImageKindReview:
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

func patchSpriteCell(ctx context.Context, images display.Reader, inspection display.InspectionKey, defectID string, imageType string, cellSize int, mapping *GrayMapping) ([]byte, error) {
	result := firstImageResult(images.GetImageBytes(ctx, []display.ImageKey{{
		Kind:          display.ImageKindPatch,
		InspectionKey: inspection,
		DefectID:      defectID,
		ImageType:     imageType,
	}}))
	if result.Err != nil {
		return blankSquarePNG(cellSize)
	}
	acquireResize()
	var resized []byte
	var err error
	if mapping == nil {
		resized, err = resizeSquarePNG(result.Data, cellSize)
	} else {
		resized, err = resizeSquarePNGWithGrayMapping(result.Data, cellSize, *mapping)
	}
	releaseResize()
	if err != nil {
		return blankSquarePNG(cellSize)
	}
	return resized, nil
}

func reviewSpriteCell(ctx context.Context, images display.Reader, inspection display.InspectionKey, defectID string, reviewImageID int, cellSize int) ([]byte, error) {
	result := firstImageResult(images.GetImageBytes(ctx, []display.ImageKey{{
		Kind:          display.ImageKindReview,
		InspectionKey: inspection,
		DefectID:      defectID,
		ReviewImageID: reviewImageID,
	}}))
	if result.Err != nil {
		return blankSquarePNG(cellSize)
	}
	acquireResize()
	resized, err := resizeSquarePNG(result.Data, cellSize)
	releaseResize()
	if err != nil {
		return blankSquarePNG(cellSize)
	}
	return resized, nil
}

func firstImageResult(results []display.ImageBytes) display.ImageBytes {
	if len(results) == 0 {
		return display.ImageBytes{Err: fmt.Errorf("no image result")}
	}
	return results[0]
}
