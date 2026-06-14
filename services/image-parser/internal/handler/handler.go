package handler

import (
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
	imageparserv1 "ft-platform/protos/gen/go/imageparser/v1"
)

type Handler struct {
	svc imageparserv1.ImageParserServer
}

func New(svc imageparserv1.ImageParserServer) *Handler {
	return &Handler{svc: svc}
}

func (h *Handler) Health(c *gin.Context) {
	resp, err := h.svc.Health(c, &imageparserv1.HealthRequest{})
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"status": resp.Status})
}

func (h *Handler) GetImage(c *gin.Context) {
	bucket := c.Query("bucket")
	key := c.Query("key")
	prefix := c.Query("prefix")
	useCache := c.Query("cache") == "true" || c.Query("cache") == "1"

	if bucket == "" || key == "" || prefix == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "bucket, key, and prefix are required"})
		return
	}

	resp, err := h.svc.GetImage(c, &imageparserv1.GetImageRequest{
		Bucket: bucket,
		Key:    key,
		Prefix: prefix,
		Cache:  useCache,
	})
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	c.Header("Content-Type", "image/png")
	c.Data(http.StatusOK, "image/png", resp.ImageData)
}

func (h *Handler) Sprite(c *gin.Context) {
	bucket := c.Query("bucket")
	key := c.Query("key")
	useCache := c.Query("cache") == "true" || c.Query("cache") == "1"

	req, err := parseSpriteRequest(bucket, key, c.Query("prefix"), c.Query("size"), useCache)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	resp, err := h.svc.Sprite(c, req)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	c.Header("Content-Type", "image/png")
	c.Data(http.StatusOK, "image/png", resp.ImageData)
}

func (h *Handler) HandleV2Sprite(c *gin.Context) {
	bucket := c.Query("bucket")
	if bucket == "" {
		bucket = "images"
	}
	record := c.Query("record")
	if record == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "record is required"})
		return
	}

	req, err := parseV2SpriteRequest(bucket, record, c.Query("items"), c.Query("size"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	resp, err := h.svc.V2Sprite(c, req)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	c.Header("Content-Type", "image/png")
	c.Data(http.StatusOK, "image/png", resp.ImageData)
}

func parseSpriteRequest(bucket, key, rawPrefix, rawSize string, useCache bool) (*imageparserv1.SpriteRequest, error) {
	if bucket == "" || key == "" || rawPrefix == "" {
		return nil, http.ErrNotSupported
	}

	parts := strings.Split(rawPrefix, ",")
	if len(parts) > 20 {
		return nil, http.ErrNotSupported
	}

	prefixes := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			prefixes = append(prefixes, p)
		}
	}
	if len(prefixes) == 0 {
		return nil, http.ErrNotSupported
	}

	sz, err := parseSize(rawSize)
	if err != nil {
		return nil, err
	}

	return &imageparserv1.SpriteRequest{
		Bucket:   bucket,
		Key:      key,
		Prefixes: prefixes,
		Size:     int32(sz),
		Cache:    useCache,
	}, nil
}

func parseV2SpriteRequest(bucket, record, rawItems, rawSize string) (*imageparserv1.V2SpriteRequest, error) {
	if rawItems == "" {
		return nil, http.ErrNotSupported
	}

	parts := strings.Split(rawItems, ",")
	if len(parts) > 20 {
		return nil, http.ErrNotSupported
	}

	items := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			items = append(items, p)
		}
	}
	if len(items) == 0 {
		return nil, http.ErrNotSupported
	}

	sz, err := parseSize(rawSize)
	if err != nil {
		return nil, err
	}

	return &imageparserv1.V2SpriteRequest{
		Bucket: bucket,
		Record: record,
		Items:  items,
		Size:   int32(sz),
	}, nil
}

func parseSize(raw string) (int, error) {
	if raw == "" {
		return 64, nil
	}
	s, err := strconv.Atoi(raw)
	if err != nil {
		return 0, err
	}
	if s < 1 {
		return 0, err
	}
	return s, nil
}
