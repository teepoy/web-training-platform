package main

import (
	"net/http/httptest"
	"reflect"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"image-parser/internal/handler"
	imageloader "image-parser/internal/image_loader"
)

func TestApplyEnvironmentParsesCacheConfiguration(t *testing.T) {
	t.Setenv("CACHE_DIR", "/cache")
	t.Setenv("CACHE_SIZE_MB", "128")
	t.Setenv("CACHE_TTL", "2h")
	t.Setenv("CACHE_CLEANUP_INTERVAL", "15m")
	t.Setenv("CACHE_MAX_BYTES", "4096")
	cacheDir := "/default"
	cacheSizeMB := 1
	cacheTTL := time.Minute
	cleanupInterval := time.Minute
	var maxBytes int64

	err := applyEnvironment(
		&cacheSizeMB,
		&cacheDir,
		&cacheTTL,
		&cleanupInterval,
		&maxBytes,
	)
	if err != nil {
		t.Fatal(err)
	}
	if cacheSizeMB != 128 || cacheDir != "/cache" || cacheTTL != 2*time.Hour ||
		cleanupInterval != 15*time.Minute || maxBytes != 4096 {
		t.Fatalf(
			"unexpected config: memory_mb=%d dir=%s ttl=%s cleanup=%s max=%d",
			cacheSizeMB,
			cacheDir,
			cacheTTL,
			cleanupInterval,
			maxBytes,
		)
	}
}

func TestApplyEnvironmentRejectsInvalidValues(t *testing.T) {
	tests := map[string]string{
		"CACHE_SIZE_MB":          "large",
		"CACHE_TTL":              "soon",
		"CACHE_CLEANUP_INTERVAL": "later",
		"CACHE_MAX_BYTES":        "large",
	}
	for name, value := range tests {
		t.Run(name, func(t *testing.T) {
			t.Setenv(name, value)
			cacheDir := "/cache"
			cacheSizeMB := 1
			cacheTTL := time.Minute
			cleanupInterval := time.Minute
			var maxBytes int64
			if err := applyEnvironment(
				&cacheSizeMB,
				&cacheDir,
				&cacheTTL,
				&cleanupInterval,
				&maxBytes,
			); err == nil {
				t.Fatal("applyEnvironment() error = nil")
			}
		})
	}
}

func TestSpriteImagesFromQueryPreservesOrder(t *testing.T) {
	gin.SetMode(gin.TestMode)
	ctx, _ := gin.CreateTestContext(httptest.NewRecorder())
	req := httptest.NewRequest("GET", "/?image_types=patchDefective,Review1,reference,review_2,difference", nil)
	ctx.Request = req

	got, err := spriteImagesFromQuery(ctx)
	if err != nil {
		t.Fatalf("spriteImagesFromQuery returned error: %v", err)
	}
	want := []handler.SCSpriteImage{
		{Kind: imageloader.ImageKindPatch, ImageType: "Defective"},
		{Kind: imageloader.ImageKindReview, ReviewImageID: 1},
		{Kind: imageloader.ImageKindPatch, ImageType: "Reference"},
		{Kind: imageloader.ImageKindReview, ReviewImageID: 2},
		{Kind: imageloader.ImageKindPatch, ImageType: "Difference"},
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("spriteImagesFromQuery = %#v, want %#v", got, want)
	}
}

func TestSpriteImagesFromQueryRequiresExplicitImages(t *testing.T) {
	gin.SetMode(gin.TestMode)
	ctx, _ := gin.CreateTestContext(httptest.NewRecorder())
	ctx.Request = httptest.NewRequest("GET", "/", nil)

	if _, err := spriteImagesFromQuery(ctx); err == nil {
		t.Fatal("spriteImagesFromQuery error = nil, want error")
	}
}

func TestSpriteImagesFromQueryRequiresReviewImageID(t *testing.T) {
	gin.SetMode(gin.TestMode)
	ctx, _ := gin.CreateTestContext(httptest.NewRecorder())
	ctx.Request = httptest.NewRequest("GET", "/?image_types=review", nil)

	if _, err := spriteImagesFromQuery(ctx); err == nil {
		t.Fatal("spriteImagesFromQuery error = nil, want error")
	}
}
