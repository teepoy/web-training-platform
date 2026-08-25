package handler

import (
	"context"
	"fmt"
	"strings"

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
	type resolvedCell struct {
		image  SCSpriteImage
		result display.ImageBytes
	}
	cells := make([]resolvedCell, len(req.Images))
	for index, spriteImage := range req.Images {
		cells[index].image = spriteImage
		var key display.ImageKey
		switch spriteImage.Kind {
		case display.ImageKindPatch:
			key = display.ImageKey{
				Kind: display.ImageKindPatch, InspectionKey: req.Inspection,
				DefectID: req.DefectID, ImageType: spriteImage.ImageType,
			}
		case display.ImageKindReview:
			key = display.ImageKey{
				Kind: display.ImageKindReview, InspectionKey: req.Inspection,
				DefectID: req.DefectID, ReviewImageID: spriteImage.ReviewImageID,
			}
		default:
			continue
		}
		cells[index].result = firstImageResult(s.images.GetImageBytes(ctx, []display.ImageKey{key}))
	}

	var defectiveReferenceWindow *grayWindow
	if mapping := req.GrayMappings.DefectiveReference; mapping != nil && mapping.Mode == GrayMappingModeAdaptive {
		rawImages := make([][]byte, 0, 2)
		for _, cell := range cells {
			if cell.image.Kind == display.ImageKindPatch && isDefectiveReferenceImageType(cell.image.ImageType) && cell.result.Err == nil {
				rawImages = append(rawImages, cell.result.Data)
			}
		}
		if len(rawImages) > 0 {
			window, err := adaptiveGrayWindowForImages(rawImages, *mapping)
			if err != nil {
				return ImageResponse{}, fmt.Errorf("resolve adaptive defective/reference range: %w", err)
			}
			defectiveReferenceWindow = &window
		}
	}

	pngs := make([][]byte, 0, len(req.Images))
	for _, cell := range cells {
		switch cell.image.Kind {
		case display.ImageKindPatch:
			window := (*grayWindow)(nil)
			if isDefectiveReferenceImageType(cell.image.ImageType) {
				window = defectiveReferenceWindow
			}
			resized, err := patchSpriteCell(cell.result, req.CellSize, req.GrayMappings.ForImageType(cell.image.ImageType), window)
			if err != nil {
				return ImageResponse{}, err
			}
			pngs = append(pngs, resized)
		case display.ImageKindReview:
			resized, err := reviewSpriteCell(cell.result, req.CellSize)
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

func patchSpriteCell(result display.ImageBytes, cellSize int, mapping *GrayMapping, window *grayWindow) ([]byte, error) {
	if result.Err != nil {
		return blankSquarePNG(cellSize)
	}
	acquireResize()
	var resized []byte
	var err error
	if mapping == nil {
		resized, err = resizeSquarePNGPixelFill(result.Data, cellSize)
	} else {
		resized, err = renderPNGWithGrayMapping(result.Data, cellSize, cellSize, *mapping, window)
	}
	releaseResize()
	if err != nil {
		return blankSquarePNG(cellSize)
	}
	return resized, nil
}

func reviewSpriteCell(result display.ImageBytes, cellSize int) ([]byte, error) {
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

func isDefectiveReferenceImageType(imageType string) bool {
	base, _, _ := strings.Cut(display.NormalizeImageType(imageType), ":")
	return base == "Defective" || base == "Reference"
}

func firstImageResult(results []display.ImageBytes) display.ImageBytes {
	if len(results) == 0 {
		return display.ImageBytes{Err: fmt.Errorf("no image result")}
	}
	return results[0]
}
