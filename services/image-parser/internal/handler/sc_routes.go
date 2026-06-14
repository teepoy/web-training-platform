package handler

import (
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/h2non/bimg"
	"image-parser/internal/resolve"
	"image-parser/internal/sprite"
)

type SCRoutes struct {
	r *resolve.Resolver
}

func NewSCRoutes(resolver *resolve.Resolver) *SCRoutes {
	return &SCRoutes{r: resolver}
}

func (s *SCRoutes) Register(r *gin.RouterGroup) {
	r.GET("/sc/images/:inspection_time/:wafer_key/:defect_id/:image_type", s.HandleSCImage)
	r.GET("/sc/sprites/patch/:inspection_time/:wafer_key/:defect_id", s.HandleSCPatchSprite)
	r.GET("/sc/sprites/review/:inspection_time/:wafer_key/:defect_id", s.HandleSCReviewSprite)
	r.GET("/sc/sprites/patch-batch/:inspection_time/:wafer_key", s.HandleSCPatchBatchSprite)
	r.GET("/sc/sprites/review-batch/:inspection_time/:wafer_key", s.HandleSCReviewBatchSprite)
	r.POST("/sc/warm/:inspection_time/:wafer_key", s.HandleSCWarm)
}

func (s *SCRoutes) HandleSCImage(c *gin.Context) {
	inspectionTime := normalizeInspectionTime(c.Param("inspection_time"))
	waferKey, err := strconv.Atoi(c.Param("wafer_key"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid wafer_key"})
		return
	}
	defectID := c.Param("defect_id")
	imageType := c.Param("image_type")

	normalized := normalizeImageType(imageType)

	if normalized == "review" {
		reviewImageID, err := strconv.Atoi(c.Query("review_image_id"))
		if err != nil || reviewImageID <= 0 {
			c.JSON(http.StatusBadRequest, gin.H{"error": "review_image_id is required"})
			return
		}
		data, err := s.r.GetReviewImage(inspectionTime, waferKey, defectID, reviewImageID)
		if err != nil {
			c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
			return
		}
		c.Header("Content-Type", "image/jpeg")
		c.Header("Cache-Control", "public, max-age=1200")
		c.Data(http.StatusOK, "image/jpeg", data)
		return
	}

	data, err := s.r.GetPatchImage(inspectionTime, waferKey, defectID, normalized)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	c.Header("Content-Type", "image/png")
	c.Header("Cache-Control", "public, max-age=1200")
	c.Data(http.StatusOK, "image/png", data)
}

func (s *SCRoutes) HandleSCPatchSprite(c *gin.Context) {
	inspectionTime := normalizeInspectionTime(c.Param("inspection_time"))
	waferKey, err := strconv.Atoi(c.Param("wafer_key"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid wafer_key"})
		return
	}
	defectID := c.Param("defect_id")

	cellSize := 64
	if v := c.Query("cell_size"); v != "" {
		cellSize, _ = strconv.Atoi(v)
		if cellSize < 16 {
			cellSize = 16
		}
		if cellSize > 512 {
			cellSize = 512
		}
	}

	_, _, _, _, allZips, err := s.r.GetMetaAndZips(inspectionTime, waferKey)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": fmt.Sprintf("resolve: %v", err)})
		return
	}

	types := []string{"template", "defective", "difference"}
	pngs := make([][]byte, 0, len(types))

	for _, t := range types {
		data, err := s.r.GetPatchImageFromZips(allZips, defectID, t)
		if err != nil {
			c.JSON(http.StatusNotFound, gin.H{"error": fmt.Sprintf("%s: %v", t, err)})
			return
		}
		resized, err := bimg.Resize(data, bimg.Options{Width: cellSize, Height: cellSize, Force: true, Type: bimg.PNG})
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		pngs = append(pngs, resized)
	}

	result, err := sprite.CreateSpriteFromResized(pngs, cellSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.Header("Content-Type", "image/png")
	c.Header("Cache-Control", "public, max-age=1200")
	c.Data(http.StatusOK, "image/png", result)
}

func (s *SCRoutes) HandleSCReviewSprite(c *gin.Context) {
	inspectionTime := normalizeInspectionTime(c.Param("inspection_time"))
	waferKey, err := strconv.Atoi(c.Param("wafer_key"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid wafer_key"})
		return
	}
	defectID := c.Param("defect_id")

	cellSize := 224
	if v := c.Query("cell_size"); v != "" {
		cellSize, _ = strconv.Atoi(v)
		if cellSize < 16 {
			cellSize = 16
		}
		if cellSize > 512 {
			cellSize = 512
		}
	}

	reviewCount := 3
	if v := c.Query("review_count"); v != "" {
		reviewCount, _ = strconv.Atoi(v)
		if reviewCount < 1 {
			reviewCount = 1
		}
		if reviewCount > 20 {
			reviewCount = 20
		}
	}

	refs, err := s.r.GetReviewImages(inspectionTime, waferKey, defectID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	if len(refs) > reviewCount {
		refs = refs[:reviewCount]
	}

	pngs := make([][]byte, 0, len(refs))
	for _, filespec := range refs {
		bucket, key := parseReviewFileSpec(filespec)
		if bucket == "" || key == "" {
			continue
		}
		data, err := resolve.GetRawS3Object(bucket, key)
		if err != nil {
			c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
			return
		}
		resized, err := bimg.Resize(data, bimg.Options{Width: cellSize, Height: cellSize, Force: true, Type: bimg.PNG})
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		pngs = append(pngs, resized)
	}

	result, err := sprite.CreateSpriteFromResized(pngs, cellSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.Header("Content-Type", "image/png")
	c.Header("Cache-Control", "public, max-age=1200")
	c.Data(http.StatusOK, "image/png", result)
}

func (s *SCRoutes) HandleSCPatchBatchSprite(c *gin.Context) {
	inspectionTime := normalizeInspectionTime(c.Param("inspection_time"))
	waferKey, err := strconv.Atoi(c.Param("wafer_key"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid wafer_key"})
		return
	}

	cellSize := 64
	if v := c.Query("cell_size"); v != "" {
		cellSize, _ = strconv.Atoi(v)
		if cellSize < 16 {
			cellSize = 16
		}
		if cellSize > 512 {
			cellSize = 512
		}
	}

	defectIDs := c.QueryArray("defect_ids")
	if len(defectIDs) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "at least one defect_id required"})
		return
	}
	if len(defectIDs) > 200 {
		defectIDs = defectIDs[:200]
	}

	_, _, _, _, allZips, err := s.r.GetMetaAndZips(inspectionTime, waferKey)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": fmt.Sprintf("resolve: %v", err)})
		return
	}

	types := []string{"template", "defective", "difference"}
	pngs := make([][]byte, 0, len(defectIDs)*len(types))

	for _, did := range defectIDs {
		for _, t := range types {
			data, err := s.r.GetPatchImageFromZips(allZips, did, t)
			if err != nil {
				c.JSON(http.StatusNotFound, gin.H{"error": fmt.Sprintf("defect %s %s: %v", did, t, err)})
				return
			}
			resized, err := bimg.Resize(data, bimg.Options{Width: cellSize, Height: cellSize, Force: true, Type: bimg.PNG})
			if err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				return
			}
			pngs = append(pngs, resized)
		}
	}

	result, err := sprite.CreateSpriteFromResized(pngs, cellSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.Header("Content-Type", "image/png")
	c.Header("Cache-Control", "public, max-age=1200")
	c.Data(http.StatusOK, "image/png", result)
}

func (s *SCRoutes) HandleSCReviewBatchSprite(c *gin.Context) {
	inspectionTime := normalizeInspectionTime(c.Param("inspection_time"))
	waferKey, err := strconv.Atoi(c.Param("wafer_key"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid wafer_key"})
		return
	}

	cellSize := 224
	if v := c.Query("cell_size"); v != "" {
		cellSize, _ = strconv.Atoi(v)
		if cellSize < 16 {
			cellSize = 16
		}
		if cellSize > 512 {
			cellSize = 512
		}
	}

	reviewCount := 3
	if v := c.Query("review_count"); v != "" {
		reviewCount, _ = strconv.Atoi(v)
		if reviewCount < 1 {
			reviewCount = 1
		}
		if reviewCount > 20 {
			reviewCount = 20
		}
	}

	defectIDs := c.QueryArray("defect_ids")
	if len(defectIDs) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "at least one defect_id required"})
		return
	}
	if len(defectIDs) > 200 {
		defectIDs = defectIDs[:200]
	}

	pngs := make([][]byte, 0)

	for _, did := range defectIDs {
		refs, err := s.r.GetReviewImages(inspectionTime, waferKey, did)
		if err != nil {
			continue
		}
		count := reviewCount
		if len(refs) < count {
			count = len(refs)
		}
		for i := 0; i < count; i++ {
			bucket, key := parseReviewFileSpec(refs[i])
			if bucket == "" || key == "" {
				continue
			}
			data, err := resolve.GetRawS3Object(bucket, key)
			if err != nil {
				continue
			}
			resized, err := bimg.Resize(data, bimg.Options{Width: cellSize, Height: cellSize, Force: true, Type: bimg.PNG})
			if err != nil {
				continue
			}
			pngs = append(pngs, resized)
		}
	}

	result, err := sprite.CreateSpriteFromResized(pngs, cellSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.Header("Content-Type", "image/png")
	c.Header("Cache-Control", "public, max-age=1200")
	c.Data(http.StatusOK, "image/png", result)
}

type WarmRequest struct {
	DefectIDs []string `json:"defect_ids"`
}

func (s *SCRoutes) HandleSCWarm(c *gin.Context) {
	inspectionTime := normalizeInspectionTime(c.Param("inspection_time"))
	waferKey, err := strconv.Atoi(c.Param("wafer_key"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid wafer_key"})
		return
	}

	var req WarmRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		req = WarmRequest{}
	}

	lotID, waferID, device, layerID, err := s.r.ResolveMetadataForWarm(inspectionTime, waferKey)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": fmt.Sprintf("inspection not found: %v", err)})
		return
	}

	allZips, err := s.r.ResolvePatchZipsForWarm(inspectionTime, lotID, waferID, device, layerID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("resolve zips: %v", err)})
		return
	}

	var zipsToWarm []resolve.CacheZipRef

	if len(req.DefectIDs) > 0 {
		var numericIDs []int
		for _, did := range req.DefectIDs {
			n, err := resolve.ParseDefectID(did)
			if err != nil {
				continue
			}
			numericIDs = append(numericIDs, n)
		}
		zipsToWarm = resolve.FilterZipsByDefectIDs(allZips, numericIDs)
	} else {
		zipsToWarm = allZips
	}

	keys := make([]string, len(zipsToWarm))
	bucket := ""
	for i, ref := range zipsToWarm {
		keys[i] = ref.Key
		if bucket == "" {
			bucket = ref.Bucket
		}
	}

	if s.r.Warmer != nil {
		s.r.Warmer.WarmAsync(fmt.Sprintf("warm:%s:%d", inspectionTime, waferKey), bucket, keys)
	}

	c.JSON(http.StatusAccepted, gin.H{"status": "warming", "zips": len(keys)})
}

func normalizeImageType(imageType string) string {
	lower := strings.ToLower(imageType)
	switch lower {
	case "patch_template", "template":
		return "template"
	case "patch_defective", "defective":
		return "defective"
	case "patch_difference", "difference":
		return "difference"
	case "review", "review_high_mag":
		return "review"
	default:
		return lower
	}
}

func parseReviewFileSpec(filespec string) (bucket, key string) {
	s := filespec
	if after, ok := strings.CutPrefix(s, "s3://"); ok {
		s = after
	}
	idx := strings.Index(s, "/")
	if idx < 0 {
		return "", s
	}
	return s[:idx], s[idx+1:]
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
