package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"image-parser/internal/display"
	"image-parser/internal/equipment"
	"image-parser/internal/handler"
)

type HTTPHandler interface {
	GetSCImage(context.Context, handler.SCImageRequest) (handler.ImageResponse, error)
	GetSCSprite(context.Context, handler.SCSpriteRequest) (handler.ImageResponse, error)
	GetSCInspectionImageProfile(context.Context, string, int32) (equipment.InspectionImageProfile, error)
	CreateSCGalleryDownload(context.Context, handler.GalleryDownloadRequest) (handler.GalleryDownloadResult, error)
}

const maxGalleryDownloadRequestBytes = 16 << 20

type galleryGrayMappingPayload struct {
	Enabled  bool    `json:"enabled"`
	LUT      string  `json:"lut"`
	ZMin     float64 `json:"zMin"`
	ZMax     float64 `json:"zMax"`
	BitDepth int     `json:"bitDepth"`
}

type galleryDownloadPayload struct {
	Items             []handler.GalleryDownloadItem `json:"items"`
	ApplyColorMapping bool                          `json:"apply_color_mapping"`
	GrayMappings      struct {
		DefectiveReference *galleryGrayMappingPayload `json:"defective_reference"`
		Difference         *galleryGrayMappingPayload `json:"difference"`
	} `json:"gray_mappings"`
}

type routeParams struct {
	inspection display.InspectionKey
	defectID   string
}

type inspectionImagePatchPayload struct {
	ImageType string `json:"image_type"`
	ImageID   *int   `json:"image_id"`
	BitDepth  int    `json:"bit_depth"`
	ZMin      uint16 `json:"z_min"`
	ZMax      uint16 `json:"z_max"`
}

type inspectionImageProfilePayload struct {
	InspectionTime  string                        `json:"inspection_time"`
	WaferKey        int32                         `json:"wafer_key"`
	ReferenceCount  int                           `json:"reference_count"`
	DifferenceCount int                           `json:"difference_count"`
	MaskCount       int                           `json:"mask_count"`
	Patches         []inspectionImagePatchPayload `json:"patches"`
}

func RegisterHandler(r *gin.RouterGroup, h HTTPHandler) {
	r.GET("/sc/inspections/:inspection_time/:wafer_key/image-profile", func(c *gin.Context) {
		waferKey, err := strconv.Atoi(c.Param("wafer_key"))
		if err != nil || waferKey <= 0 {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid wafer_key"})
			return
		}
		profile, err := h.GetSCInspectionImageProfile(
			c.Request.Context(), normalizeInspectionTime(c.Param("inspection_time")), int32(waferKey),
		)
		if err != nil {
			c.JSON(http.StatusUnprocessableEntity, gin.H{"error": err.Error()})
			return
		}
		c.Header("Cache-Control", "no-store")
		c.JSON(http.StatusOK, imageProfilePayload(profile))
	})

	r.GET("/sc/images/:inspection_time/:wafer_key/:defect_id/:image_type", func(c *gin.Context) {
		params, ok := parseRouteParams(c)
		if !ok {
			return
		}
		req := handler.SCImageRequest{
			Inspection: params.inspection,
			DefectID:   params.defectID,
			ImageType:  c.Param("image_type"),
		}
		if normalizeImageType(req.ImageType) == "review" {
			reviewImageID, err := strconv.Atoi(c.Query("review_image_id"))
			if err != nil || reviewImageID <= 0 {
				c.JSON(http.StatusBadRequest, gin.H{"error": "review_image_id is required"})
				return
			}
			req.ReviewImageID = reviewImageID
		}
		resp, err := h.GetSCImage(c.Request.Context(), req)
		writeImage(c, resp, err, http.StatusNotFound)
	})

	r.GET("/sc/sprites/:mode/:inspection_time/:wafer_key/:defect_id", func(c *gin.Context) {
		params, ok := parseRouteParams(c)
		if !ok {
			return
		}
		images, err := spriteImagesFromQuery(c)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		grayMappings, err := grayMappingsFromQuery(c)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		req := handler.SCSpriteRequest{
			Inspection:   params.inspection,
			DefectID:     params.defectID,
			CellSize:     queryInt(c, "cell_size", 64, 16, 512),
			Images:       images,
			GrayMappings: grayMappings,
		}
		switch c.Param("mode") {
		case "patch", "review":
		default:
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid sprite mode"})
			return
		}
		resp, err := h.GetSCSprite(c.Request.Context(), req)
		writeImage(c, resp, err, http.StatusInternalServerError)
	})

	r.POST("/sc/gallery-downloads", func(c *gin.Context) {
		c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxGalleryDownloadRequestBytes)
		if err := c.Request.ParseForm(); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid gallery download form"})
			return
		}
		var payload galleryDownloadPayload
		if err := json.Unmarshal([]byte(c.Request.PostFormValue("payload")), &payload); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid gallery download payload"})
			return
		}
		mappings, err := galleryMappingsFromPayload(payload)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		result, err := h.CreateSCGalleryDownload(c.Request.Context(), handler.GalleryDownloadRequest{
			Items: payload.Items, ApplyColorMapping: payload.ApplyColorMapping, GrayMappings: mappings,
		})
		if err != nil {
			c.JSON(http.StatusUnprocessableEntity, gin.H{"error": err.Error()})
			return
		}
		defer os.Remove(result.Path)
		c.Header("Cache-Control", "no-store")
		c.Header("X-Content-Type-Options", "nosniff")
		c.FileAttachment(result.Path, result.Filename)
	})

}

func imageProfilePayload(profile equipment.InspectionImageProfile) inspectionImageProfilePayload {
	payload := inspectionImageProfilePayload{
		InspectionTime: profile.InspectionTime,
		WaferKey:       profile.WaferKey,
		Patches:        make([]inspectionImagePatchPayload, len(profile.Patches)),
	}
	for index, patch := range profile.Patches {
		payload.Patches[index] = inspectionImagePatchPayload{
			ImageType: patch.ImageType, ImageID: patch.ImageID, BitDepth: patch.BitDepth, ZMin: patch.ZMin, ZMax: patch.ZMax,
		}
		switch patch.ImageType {
		case "Reference":
			payload.ReferenceCount++
		case "Difference":
			payload.DifferenceCount++
		case "Mask":
			payload.MaskCount++
		}
	}
	return payload
}

func galleryMappingsFromPayload(payload galleryDownloadPayload) (handler.PatchGrayMappings, error) {
	defectiveReference, err := galleryMappingFromPayload(payload.GrayMappings.DefectiveReference)
	if err != nil {
		return handler.PatchGrayMappings{}, fmt.Errorf("invalid defective/reference mapping: %w", err)
	}
	difference, err := galleryMappingFromPayload(payload.GrayMappings.Difference)
	if err != nil {
		return handler.PatchGrayMappings{}, fmt.Errorf("invalid difference mapping: %w", err)
	}
	return handler.PatchGrayMappings{DefectiveReference: defectiveReference, Difference: difference}, nil
}

func galleryMappingFromPayload(payload *galleryGrayMappingPayload) (*handler.GrayMapping, error) {
	if payload == nil || !payload.Enabled {
		return nil, nil
	}
	lut, err := handler.ParseGrayLUT(payload.LUT)
	if err != nil {
		return nil, err
	}
	mapping := &handler.GrayMapping{LUT: lut, ZMin: payload.ZMin, ZMax: payload.ZMax, BitDepth: payload.BitDepth}
	if err := mapping.Validate(); err != nil {
		return nil, err
	}
	return mapping, nil
}

func grayMappingsFromQuery(c *gin.Context) (handler.PatchGrayMappings, error) {
	legacy, legacyPresent, err := grayMappingTupleFromQuery(c, "")
	if err != nil {
		return handler.PatchGrayMappings{}, err
	}
	defectiveReference, defectiveReferencePresent, err := grayMappingTupleFromQuery(c, "defective_reference_")
	if err != nil {
		return handler.PatchGrayMappings{}, err
	}
	difference, differencePresent, err := grayMappingTupleFromQuery(c, "difference_")
	if err != nil {
		return handler.PatchGrayMappings{}, err
	}
	if legacyPresent && (defectiveReferencePresent || differencePresent) {
		return handler.PatchGrayMappings{}, fmt.Errorf("legacy gray mapping cannot be combined with grouped mappings")
	}
	if legacyPresent {
		return handler.PatchGrayMappings{DefectiveReference: legacy, Difference: legacy}, nil
	}
	return handler.PatchGrayMappings{DefectiveReference: defectiveReference, Difference: difference}, nil
}

func grayMappingTupleFromQuery(c *gin.Context, prefix string) (*handler.GrayMapping, bool, error) {
	lutName := prefix + "gray_lut"
	zMinName := prefix + "z_min"
	zMaxName := prefix + "z_max"
	bitDepthName := prefix + "bit_depth"
	lutRaw, hasLUT := c.GetQuery(lutName)
	zMinRaw, hasZMin := c.GetQuery(zMinName)
	zMaxRaw, hasZMax := c.GetQuery(zMaxName)
	bitDepthRaw, hasBitDepth := c.GetQuery(bitDepthName)
	if !hasLUT && !hasZMin && !hasZMax && !hasBitDepth {
		return nil, false, nil
	}
	if !hasLUT || !hasZMin || !hasZMax {
		return nil, true, fmt.Errorf("%s, %s, and %s must be provided together", lutName, zMinName, zMaxName)
	}
	lut, err := handler.ParseGrayLUT(lutRaw)
	if err != nil {
		return nil, true, err
	}
	zMin, err := strconv.ParseFloat(zMinRaw, 64)
	if err != nil {
		return nil, true, fmt.Errorf("invalid %s %q", zMinName, zMinRaw)
	}
	zMax, err := strconv.ParseFloat(zMaxRaw, 64)
	if err != nil {
		return nil, true, fmt.Errorf("invalid %s %q", zMaxName, zMaxRaw)
	}
	bitDepth := 0
	if hasBitDepth {
		bitDepth, err = strconv.Atoi(bitDepthRaw)
		if err != nil {
			return nil, true, fmt.Errorf("invalid %s %q", bitDepthName, bitDepthRaw)
		}
	}
	mapping := &handler.GrayMapping{LUT: lut, ZMin: zMin, ZMax: zMax, BitDepth: bitDepth}
	if err := mapping.Validate(); err != nil {
		return nil, true, err
	}
	return mapping, true, nil
}

func parseRouteParams(c *gin.Context) (routeParams, bool) {
	waferKey, err := strconv.Atoi(c.Param("wafer_key"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid wafer_key"})
		return routeParams{}, false
	}
	return routeParams{
		inspection: display.InspectionKey{
			InspectionTime: normalizeInspectionTime(c.Param("inspection_time")),
			WaferKey:       waferKey,
		},
		defectID: c.Param("defect_id"),
	}, true
}

func writeImage(c *gin.Context, resp handler.ImageResponse, err error, errorStatus int) {
	if err != nil {
		c.JSON(errorStatus, gin.H{"error": err.Error()})
		return
	}
	c.Header("Content-Type", resp.ContentType)
	c.Header("Cache-Control", "public, max-age=1200")
	c.Data(http.StatusOK, resp.ContentType, resp.Data)
}

func queryInt(c *gin.Context, name string, fallback, min, max int) int {
	value := fallback
	if raw := c.Query(name); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err == nil {
			value = parsed
		}
	}
	if value < min {
		return min
	}
	if value > max {
		return max
	}
	return value
}

func spriteImagesFromQuery(c *gin.Context) ([]handler.SCSpriteImage, error) {
	rawTypes := imageTypesFromQuery(c)
	if len(rawTypes) == 0 {
		return nil, fmt.Errorf("image_types is required")
	}
	images := make([]handler.SCSpriteImage, 0, len(rawTypes))
	for _, raw := range rawTypes {
		item, ok, err := parseSpriteImage(strings.TrimSpace(raw))
		if err != nil {
			return nil, err
		}
		if !ok {
			continue
		}
		images = append(images, item)
	}
	if len(images) == 0 {
		return nil, fmt.Errorf("image_types must include at least one patch or review image")
	}
	return images, nil
}

func parseSpriteImage(raw string) (handler.SCSpriteImage, bool, error) {
	if raw == "" {
		return handler.SCSpriteImage{}, false, nil
	}
	if reviewImageID, ok, err := parseReviewSpriteImage(raw); ok || err != nil {
		if err != nil {
			return handler.SCSpriteImage{}, false, err
		}
		return handler.SCSpriteImage{
			Kind:          display.ImageKindReview,
			ReviewImageID: reviewImageID,
		}, true, nil
	}
	normalized := normalizeImageType(raw)
	base, _, _ := strings.Cut(normalized, ":")
	switch base {
	case "Defective", "Reference", "Difference", "Mask":
		return handler.SCSpriteImage{
			Kind:      display.ImageKindPatch,
			ImageType: normalized,
		}, true, nil
	default:
		return handler.SCSpriteImage{}, false, fmt.Errorf("unsupported sprite image type %q", raw)
	}
}

func parseReviewSpriteImage(raw string) (int, bool, error) {
	compact := strings.NewReplacer("_", "", "-", "", ":", "", " ", "").Replace(strings.ToLower(raw))
	if !strings.HasPrefix(compact, "review") {
		return 0, false, nil
	}
	suffix := strings.TrimPrefix(compact, "review")
	if suffix == "" {
		return 0, true, fmt.Errorf("review sprite image %q must include a review image id", raw)
	}
	reviewImageID, err := strconv.Atoi(suffix)
	if err != nil || reviewImageID <= 0 {
		return 0, true, fmt.Errorf("invalid review sprite image %q", raw)
	}
	return reviewImageID, true, nil
}

func imageTypesFromQuery(c *gin.Context) []string {
	rawTypes := c.QueryArray("image_types")
	if csv := c.Query("image_types"); csv != "" && len(rawTypes) == 1 {
		rawTypes = strings.Split(csv, ",")
	}
	return rawTypes
}

func normalizeImageType(imageType string) string {
	lower := strings.ToLower(strings.TrimSpace(imageType))
	base, imageID, hasImageID := strings.Cut(lower, ":")
	var normalized string
	switch base {
	case "patch_template", "patchtemplate", "patch_reference", "patchreference", "template", "reference":
		normalized = "Reference"
	case "patch_defective", "patchdefective", "defective":
		normalized = "Defective"
	case "patch_difference", "patchdifference", "difference":
		normalized = "Difference"
	case "patch_mask", "patchmask", "mask":
		normalized = "Mask"
	case "review", "review_high_mag":
		return "review"
	default:
		return strings.TrimSpace(imageType)
	}
	if !hasImageID {
		return normalized
	}
	if normalized == "Defective" {
		return strings.TrimSpace(imageType)
	}
	parsed, err := strconv.Atoi(strings.TrimSpace(imageID))
	if err != nil || parsed < 0 {
		return strings.TrimSpace(imageType)
	}
	return fmt.Sprintf("%s:%d", normalized, parsed)
}

func normalizeInspectionTime(raw string) string {
	if raw == "" {
		return raw
	}
	if strings.Contains(raw, "-") {
		return raw
	}
	ts, err := strconv.ParseInt(raw, 10, 64)
	if err != nil {
		return raw
	}
	if ts > 999_999_999_999 {
		ts = ts / 1000
	}
	return time.Unix(ts, 0).UTC().Format(time.RFC3339)
}
