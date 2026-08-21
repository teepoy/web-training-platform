package main

import (
	"context"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"image-parser/internal/display"
	"image-parser/internal/handler"
)

type HTTPHandler interface {
	GetSCImage(context.Context, handler.SCImageRequest) (handler.ImageResponse, error)
	GetSCSprite(context.Context, handler.SCSpriteRequest) (handler.ImageResponse, error)
}

type routeParams struct {
	inspection display.InspectionKey
	defectID   string
}

func RegisterHandler(r *gin.RouterGroup, h HTTPHandler) {
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
		grayMapping, err := grayMappingFromQuery(c)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		req := handler.SCSpriteRequest{
			Inspection:  params.inspection,
			DefectID:    params.defectID,
			CellSize:    queryInt(c, "cell_size", 64, 16, 512),
			Images:      images,
			GrayMapping: grayMapping,
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

}

func grayMappingFromQuery(c *gin.Context) (*handler.GrayMapping, error) {
	lutRaw, hasLUT := c.GetQuery("gray_lut")
	zMinRaw, hasZMin := c.GetQuery("z_min")
	zMaxRaw, hasZMax := c.GetQuery("z_max")
	if !hasLUT && !hasZMin && !hasZMax {
		return nil, nil
	}
	if !hasLUT || !hasZMin || !hasZMax {
		return nil, fmt.Errorf("gray_lut, z_min, and z_max must be provided together")
	}
	lut, err := handler.ParseGrayLUT(lutRaw)
	if err != nil {
		return nil, err
	}
	zMin, err := strconv.ParseFloat(zMinRaw, 64)
	if err != nil {
		return nil, fmt.Errorf("invalid z_min %q", zMinRaw)
	}
	zMax, err := strconv.ParseFloat(zMaxRaw, 64)
	if err != nil {
		return nil, fmt.Errorf("invalid z_max %q", zMaxRaw)
	}
	mapping := &handler.GrayMapping{LUT: lut, ZMin: zMin, ZMax: zMax}
	if err := mapping.Validate(); err != nil {
		return nil, err
	}
	return mapping, nil
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
	switch normalized {
	case "Defective", "Reference", "Difference":
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
	switch lower {
	case "patch_template", "patchtemplate", "patch_reference", "patchreference", "template", "reference":
		return "Reference"
	case "patch_defective", "patchdefective", "defective":
		return "Defective"
	case "patch_difference", "patchdifference", "difference":
		return "Difference"
	case "review", "review_high_mag":
		return "review"
	default:
		return strings.TrimSpace(imageType)
	}
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
