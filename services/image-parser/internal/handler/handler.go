package handler

import (
	"bytes"
	"context"
	"fmt"
	"image"
	"image/png"
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
		source image.Image
	}
	cells := make([]resolvedCell, len(req.Images))
	keys := make([]display.ImageKey, 0, len(req.Images))
	keyIndexes := make([]int, 0, len(req.Images))
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
		keys = append(keys, key)
		keyIndexes = append(keyIndexes, index)
	}
	resolved := s.images.GetImageBytes(ctx, keys)
	if len(resolved) != len(keys) {
		return ImageResponse{}, fmt.Errorf(
			"image reader returned %d results for %d sprite cells",
			len(resolved),
			len(keys),
		)
	}
	for resultIndex, cellIndex := range keyIndexes {
		cells[cellIndex].result = resolved[resultIndex]
	}
	for index := range cells {
		cell := &cells[index]
		if cell.result.Err != nil || len(cell.result.Data) == 0 {
			continue
		}
		decoded, _, err := image.Decode(bytes.NewReader(cell.result.Data))
		if err != nil {
			cell.result.Err = err
			continue
		}
		cell.source = decoded
	}

	var defectiveReferenceWindow *grayWindow
	if mapping := req.GrayMappings.DefectiveReference; mapping != nil && mapping.Mode == GrayMappingModeAdaptive {
		decodedImages := make([]image.Image, 0, 2)
		for _, cell := range cells {
			if cell.image.Kind == display.ImageKindPatch && isDefectiveReferenceImageType(cell.image.ImageType) && cell.result.Err == nil && cell.source != nil {
				decodedImages = append(decodedImages, cell.source)
			}
		}
		if len(decodedImages) > 0 {
			window, err := adaptiveGrayWindowForDecodedImages(decodedImages, *mapping)
			if err != nil {
				return ImageResponse{}, fmt.Errorf("resolve adaptive defective/reference range: %w", err)
			}
			defectiveReferenceWindow = &window
		}
	}

	canvas := image.NewNRGBA(image.Rect(0, 0, req.CellSize*len(cells), req.CellSize))
	acquireResize()
	defer releaseResize()
	for index, cell := range cells {
		destination := image.Rect(index*req.CellSize, 0, (index+1)*req.CellSize, req.CellSize)
		if cell.result.Err != nil || cell.source == nil {
			drawBlankCell(canvas, destination)
			continue
		}
		switch cell.image.Kind {
		case display.ImageKindPatch:
			window := (*grayWindow)(nil)
			if isDefectiveReferenceImageType(cell.image.ImageType) {
				window = defectiveReferenceWindow
			}
			mapping := req.GrayMappings.ForImageType(cell.image.ImageType)
			if mapping == nil {
				resizeNearestInto(canvas, destination, cell.source)
				continue
			}
			if err := renderDecodedGrayMappingInto(canvas, destination, cell.source, *mapping, window); err != nil {
				drawBlankCell(canvas, destination)
			}
		case display.ImageKindReview:
			resizeBilinearInto(canvas, destination, cell.source)
		default:
			drawBlankCell(canvas, destination)
		}
	}

	var output bytes.Buffer
	if err := png.Encode(&output, canvas); err != nil {
		return ImageResponse{}, err
	}
	return ImageResponse{Data: output.Bytes(), ContentType: "image/png"}, nil
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
