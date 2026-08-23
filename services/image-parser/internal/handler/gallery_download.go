package handler

import (
	"archive/zip"
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	scv1 "image-parser/gen/go/sc/v1"
	"image-parser/internal/display"
)

const galleryDownloadImageBatch = 256

type GalleryDownloadMetadataSource interface {
	GetInspection(ctx context.Context, inspectionTime string, waferKey int32) (*scv1.GetInspectionResponse, error)
}

type GalleryDownloadItem struct {
	InspectionTime  string   `json:"inspection_time"`
	WaferKey        int      `json:"wafer_key"`
	DefectID        string   `json:"defect_id"`
	PatchImageTypes []string `json:"patch_image_types"`
	ReviewImageIDs  []int    `json:"review_image_ids"`
}

type GalleryDownloadRequest struct {
	Items             []GalleryDownloadItem `json:"items"`
	ApplyColorMapping bool                  `json:"apply_color_mapping"`
	GrayMappings      PatchGrayMappings     `json:"-"`
}

type GalleryDownloadResult struct {
	Path     string
	Filename string
}

type galleryArchiveEntry struct {
	key     display.ImageKey
	name    string
	mapping *GrayMapping
}

type GalleryDownloadService struct {
	images   display.Reader
	metadata GalleryDownloadMetadataSource
	tempDir  string
}

func NewGalleryDownloadService(images display.Reader, metadata GalleryDownloadMetadataSource, tempDir string) (*GalleryDownloadService, error) {
	if images == nil || metadata == nil {
		return nil, fmt.Errorf("gallery download requires image and inspection readers")
	}
	if !filepath.IsAbs(tempDir) {
		return nil, fmt.Errorf("gallery download temp directory must be absolute")
	}
	if err := os.MkdirAll(tempDir, 0o700); err != nil {
		return nil, fmt.Errorf("create gallery download temp directory: %w", err)
	}
	return &GalleryDownloadService{images: images, metadata: metadata, tempDir: tempDir}, nil
}

func (s *GalleryDownloadService) Create(ctx context.Context, request GalleryDownloadRequest) (result GalleryDownloadResult, resultErr error) {
	if len(request.Items) == 0 {
		return GalleryDownloadResult{}, fmt.Errorf("gallery download requires at least one item")
	}
	entries, err := s.planEntries(ctx, request)
	if err != nil {
		return GalleryDownloadResult{}, err
	}
	file, err := os.CreateTemp(s.tempDir, "gallery-images-*.zip")
	if err != nil {
		return GalleryDownloadResult{}, fmt.Errorf("create gallery download: %w", err)
	}
	path := file.Name()
	defer func() {
		if resultErr != nil {
			_ = file.Close()
			_ = os.Remove(path)
		}
	}()

	archive := zip.NewWriter(file)
	for start := 0; start < len(entries); start += galleryDownloadImageBatch {
		end := min(start+galleryDownloadImageBatch, len(entries))
		keys := make([]display.ImageKey, end-start)
		for index := start; index < end; index++ {
			keys[index-start] = entries[index].key
		}
		images := s.images.GetImageBytes(ctx, keys)
		if len(images) != len(keys) {
			return GalleryDownloadResult{}, fmt.Errorf("image reader returned %d results for %d gallery images", len(images), len(keys))
		}
		for index, imageBytes := range images {
			entry := entries[start+index]
			if imageBytes.Err != nil {
				return GalleryDownloadResult{}, fmt.Errorf("read %s: %w", entry.name, imageBytes.Err)
			}
			data := imageBytes.Data
			contentType := canonicalImageContentType(imageBytes.ContentType)
			if entry.mapping != nil {
				data, err = originalSizePNGWithGrayMapping(data, *entry.mapping)
				if err != nil {
					return GalleryDownloadResult{}, fmt.Errorf("map %s: %w", entry.name, err)
				}
				contentType = "image/png"
			}
			extension, err := galleryImageExtension(contentType)
			if err != nil {
				return GalleryDownloadResult{}, fmt.Errorf("write %s: %w", entry.name, err)
			}
			header := &zip.FileHeader{Name: entry.name + extension, Method: zip.Store}
			writer, err := archive.CreateHeader(header)
			if err != nil {
				return GalleryDownloadResult{}, fmt.Errorf("create ZIP entry: %w", err)
			}
			if _, err := writer.Write(data); err != nil {
				return GalleryDownloadResult{}, fmt.Errorf("write ZIP entry: %w", err)
			}
		}
	}
	if err := archive.Close(); err != nil {
		return GalleryDownloadResult{}, fmt.Errorf("finalize gallery ZIP: %w", err)
	}
	if err := file.Sync(); err != nil {
		return GalleryDownloadResult{}, fmt.Errorf("sync gallery ZIP: %w", err)
	}
	if err := file.Close(); err != nil {
		return GalleryDownloadResult{}, fmt.Errorf("close gallery ZIP: %w", err)
	}
	return GalleryDownloadResult{Path: path, Filename: "gallery-images.zip"}, nil
}

func (s *GalleryDownloadService) planEntries(ctx context.Context, request GalleryDownloadRequest) ([]galleryArchiveEntry, error) {
	type inspectionIdentity struct {
		time     string
		waferKey int
	}
	roots := make(map[inspectionIdentity]string)
	seenNames := make(map[string]struct{})
	entries := make([]galleryArchiveEntry, 0, len(request.Items)*3)
	for _, item := range request.Items {
		if strings.TrimSpace(item.InspectionTime) == "" || item.WaferKey <= 0 || strings.TrimSpace(item.DefectID) == "" {
			return nil, fmt.Errorf("gallery item requires inspection_time, positive wafer_key, and defect_id")
		}
		identity := inspectionIdentity{time: item.InspectionTime, waferKey: item.WaferKey}
		root, ok := roots[identity]
		if !ok {
			inspection, err := s.metadata.GetInspection(ctx, item.InspectionTime, int32(item.WaferKey))
			if err != nil {
				return nil, fmt.Errorf("query inspection metadata: %w", err)
			}
			if strings.TrimSpace(inspection.GetWaferId()) == "" {
				return nil, fmt.Errorf("inspection wafer_id is required for gallery archive paths")
			}
			root = safeArchiveComponent(item.InspectionTime) + "-" + safeArchiveComponent(inspection.GetWaferId())
			roots[identity] = root
		}
		base := root + "/" + safeArchiveComponent(item.DefectID) + "-"
		for _, rawRole := range item.PatchImageTypes {
			role := display.NormalizeImageType(rawRole)
			baseRole, _, _ := strings.Cut(role, ":")
			if baseRole != "Defective" && baseRole != "Reference" && baseRole != "Difference" && baseRole != "Mask" {
				return nil, fmt.Errorf("unsupported gallery patch image type %q", rawRole)
			}
			mapping := (*GrayMapping)(nil)
			if request.ApplyColorMapping && baseRole != "Mask" {
				mapping = request.GrayMappings.ForImageType(role)
			}
			entry := galleryArchiveEntry{
				key:  display.ImageKey{Kind: display.ImageKindPatch, InspectionKey: display.InspectionKey{InspectionTime: item.InspectionTime, WaferKey: item.WaferKey}, DefectID: item.DefectID, ImageType: role},
				name: base + strings.ToLower(strings.ReplaceAll(role, ":", "-")), mapping: mapping,
			}
			if err := claimGalleryArchiveName(seenNames, entry.name); err != nil {
				return nil, err
			}
			entries = append(entries, entry)
		}
		for _, imageID := range item.ReviewImageIDs {
			if imageID <= 0 {
				return nil, fmt.Errorf("review image IDs must be positive")
			}
			entry := galleryArchiveEntry{
				key:  display.ImageKey{Kind: display.ImageKindReview, InspectionKey: display.InspectionKey{InspectionTime: item.InspectionTime, WaferKey: item.WaferKey}, DefectID: item.DefectID, ReviewImageID: imageID},
				name: fmt.Sprintf("%sreview-%d", base, imageID),
			}
			if err := claimGalleryArchiveName(seenNames, entry.name); err != nil {
				return nil, err
			}
			entries = append(entries, entry)
		}
	}
	if len(entries) == 0 {
		return nil, fmt.Errorf("gallery download contains no images")
	}
	return entries, nil
}

func claimGalleryArchiveName(seen map[string]struct{}, name string) error {
	if _, exists := seen[name]; exists {
		return fmt.Errorf("duplicate gallery archive entry %q", name)
	}
	seen[name] = struct{}{}
	return nil
}

func safeArchiveComponent(value string) string {
	value = strings.TrimSpace(value)
	value = strings.NewReplacer("/", "_", "\\", "_", "\x00", "_").Replace(value)
	if value == "" || value == "." || value == ".." {
		return "_"
	}
	return value
}

func canonicalImageContentType(value string) string {
	value = strings.ToLower(strings.TrimSpace(strings.SplitN(value, ";", 2)[0]))
	if value == "image/jpg" {
		return "image/jpeg"
	}
	return value
}

func galleryImageExtension(contentType string) (string, error) {
	switch contentType {
	case "image/png":
		return ".png", nil
	case "image/jpeg":
		return ".jpg", nil
	default:
		return "", fmt.Errorf("unsupported original image content type %q", contentType)
	}
}
