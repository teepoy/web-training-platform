package main

import (
	"net/http/httptest"
	"reflect"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"image-parser/internal/display"
	"image-parser/internal/handler"
)

func TestApplyEnvironmentParsesCacheConfiguration(t *testing.T) {
	t.Setenv("CACHE_DIR", "/cache")
	t.Setenv("CACHE_TTL", "2h")
	t.Setenv("CACHE_CLEANUP_INTERVAL", "15m")
	t.Setenv("CACHE_MAX_BYTES", "4096")
	cacheDir := "/default"
	cacheTTL := time.Minute
	cleanupInterval := time.Minute
	var maxBytes int64

	err := applyEnvironment(
		&cacheDir,
		&cacheTTL,
		&cleanupInterval,
		&maxBytes,
	)
	if err != nil {
		t.Fatal(err)
	}
	if cacheDir != "/cache" || cacheTTL != 2*time.Hour ||
		cleanupInterval != 15*time.Minute || maxBytes != 4096 {
		t.Fatalf(
			"unexpected config: dir=%s ttl=%s cleanup=%s max=%d",
			cacheDir,
			cacheTTL,
			cleanupInterval,
			maxBytes,
		)
	}
}

func TestApplyEnvironmentRejectsInvalidValues(t *testing.T) {
	tests := map[string]string{
		"CACHE_TTL":              "soon",
		"CACHE_CLEANUP_INTERVAL": "later",
		"CACHE_MAX_BYTES":        "large",
	}
	for name, value := range tests {
		t.Run(name, func(t *testing.T) {
			t.Setenv(name, value)
			cacheDir := "/cache"
			cacheTTL := time.Minute
			cleanupInterval := time.Minute
			var maxBytes int64
			if err := applyEnvironment(
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
		{Kind: display.ImageKindPatch, ImageType: "Defective"},
		{Kind: display.ImageKindReview, ReviewImageID: 1},
		{Kind: display.ImageKindPatch, ImageType: "Reference"},
		{Kind: display.ImageKindReview, ReviewImageID: 2},
		{Kind: display.ImageKindPatch, ImageType: "Difference"},
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

func TestGrayMappingFromQueryRequiresCompleteValidWindow(t *testing.T) {
	gin.SetMode(gin.TestMode)
	tests := []struct {
		name    string
		query   string
		wantErr bool
	}{
		{name: "disabled", query: ""},
		{name: "complete", query: "?gray_lut=viridis&z_min=0.125&z_max=0.875"},
		{name: "unknown LUT", query: "?gray_lut=rainbow&z_min=0&z_max=1", wantErr: true},
		{name: "missing z min", query: "?gray_lut=gray&z_max=1", wantErr: true},
		{name: "reversed window", query: "?gray_lut=gray&z_min=0.8&z_max=0.2", wantErr: true},
		{name: "outside normalized range", query: "?gray_lut=gray&z_min=-0.1&z_max=1", wantErr: true},
		{name: "not a number", query: "?gray_lut=gray&z_min=NaN&z_max=1", wantErr: true},
		{name: "infinite", query: "?gray_lut=gray&z_min=0&z_max=Inf", wantErr: true},
		{name: "window without LUT", query: "?z_min=0&z_max=1", wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			ctx, _ := gin.CreateTestContext(httptest.NewRecorder())
			ctx.Request = httptest.NewRequest("GET", "/"+tt.query, nil)

			mapping, err := grayMappingFromQuery(ctx)
			if tt.wantErr {
				if err == nil {
					t.Fatalf("grayMappingFromQuery() = %#v, nil; want error", mapping)
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			if tt.query == "" && mapping != nil {
				t.Fatalf("disabled mapping = %#v, want nil", mapping)
			}
			if tt.query != "" && (mapping == nil || mapping.LUT != handler.GrayLUTViridis || mapping.ZMin != 0.125 || mapping.ZMax != 0.875) {
				t.Fatalf("mapping = %#v, want viridis [0.125, 0.875]", mapping)
			}
		})
	}
}
