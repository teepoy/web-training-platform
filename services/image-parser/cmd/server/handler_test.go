package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"image-parser/internal/display"
	"image-parser/internal/equipment"
	"image-parser/internal/handler"
)

type galleryHTTPHandlerStub struct {
	result  handler.GalleryDownloadResult
	request handler.GalleryDownloadRequest
	profile equipment.InspectionImageProfile
}

func (*galleryHTTPHandlerStub) GetSCImage(context.Context, handler.SCImageRequest) (handler.ImageResponse, error) {
	return handler.ImageResponse{}, nil
}

func (*galleryHTTPHandlerStub) GetSCSprite(context.Context, handler.SCSpriteRequest) (handler.ImageResponse, error) {
	return handler.ImageResponse{}, nil
}

func (s *galleryHTTPHandlerStub) GetSCInspectionImageProfile(context.Context, string, int32) (equipment.InspectionImageProfile, error) {
	return s.profile, nil
}

func (s *galleryHTTPHandlerStub) CreateSCGalleryDownload(_ context.Context, request handler.GalleryDownloadRequest) (handler.GalleryDownloadResult, error) {
	s.request = request
	return s.result, nil
}

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

func TestGrayMappingsFromQueryRequiresCompleteValidWindow(t *testing.T) {
	gin.SetMode(gin.TestMode)
	tests := []struct {
		name    string
		query   string
		wantErr bool
	}{
		{name: "disabled", query: ""},
		{name: "complete", query: "?gray_mode=global&gray_lut=viridis&z_min=0.125&z_max=0.875"},
		{name: "adaptive", query: "?gray_mode=adaptive&gray_lut=viridis&z_min=0&z_max=1"},
		{name: "unknown mode", query: "?gray_mode=local&gray_lut=gray&z_min=0&z_max=1", wantErr: true},
		{name: "unknown LUT", query: "?gray_mode=global&gray_lut=rainbow&z_min=0&z_max=1", wantErr: true},
		{name: "missing z min", query: "?gray_mode=global&gray_lut=gray&z_max=1", wantErr: true},
		{name: "reversed window", query: "?gray_mode=global&gray_lut=gray&z_min=0.8&z_max=0.2", wantErr: true},
		{name: "outside normalized range", query: "?gray_mode=global&gray_lut=gray&z_min=-0.1&z_max=1", wantErr: true},
		{name: "not a number", query: "?gray_mode=global&gray_lut=gray&z_min=NaN&z_max=1", wantErr: true},
		{name: "infinite", query: "?gray_mode=global&gray_lut=gray&z_min=0&z_max=Inf", wantErr: true},
		{name: "window without LUT", query: "?gray_mode=global&z_min=0&z_max=1", wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			ctx, _ := gin.CreateTestContext(httptest.NewRecorder())
			ctx.Request = httptest.NewRequest("GET", "/"+tt.query, nil)

			mappings, err := grayMappingsFromQuery(ctx)
			if tt.wantErr {
				if err == nil {
					t.Fatalf("grayMappingsFromQuery() = %#v, nil; want error", mappings)
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			if tt.query == "" && (mappings.DefectiveReference != nil || mappings.Difference != nil) {
				t.Fatalf("disabled mappings = %#v, want empty", mappings)
			}
			if tt.name == "complete" && (mappings.DefectiveReference == nil || mappings.Difference == nil || mappings.DefectiveReference.Mode != handler.GrayMappingModeGlobal || mappings.DefectiveReference.LUT != handler.GrayLUTViridis || mappings.DefectiveReference.ZMin != 0.125 || mappings.DefectiveReference.ZMax != 0.875) {
				t.Fatalf("mappings = %#v, want legacy global viridis [0.125, 0.875] for both groups", mappings)
			}
			if tt.name == "adaptive" && (mappings.DefectiveReference == nil || mappings.DefectiveReference.Mode != handler.GrayMappingModeAdaptive) {
				t.Fatalf("mappings = %#v, want adaptive mode", mappings)
			}
		})
	}
}

func TestGrayMappingsFromQuerySeparatesDefectiveReferenceAndDifference(t *testing.T) {
	gin.SetMode(gin.TestMode)
	ctx, _ := gin.CreateTestContext(httptest.NewRecorder())
	ctx.Request = httptest.NewRequest("GET", "/?defective_reference_gray_mode=global&defective_reference_gray_lut=viridis&defective_reference_z_min=0.1&defective_reference_z_max=0.8&difference_gray_mode=global&difference_gray_lut=inferno&difference_z_min=0.2&difference_z_max=0.9", nil)

	mappings, err := grayMappingsFromQuery(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if mappings.DefectiveReference == nil || mappings.DefectiveReference.LUT != handler.GrayLUTViridis {
		t.Fatalf("defective/reference mapping = %#v", mappings.DefectiveReference)
	}
	if mappings.Difference == nil || mappings.Difference.LUT != handler.GrayLUTInferno {
		t.Fatalf("difference mapping = %#v", mappings.Difference)
	}
}

func TestGrayMappingsFromQueryReadsNativeBitDepth(t *testing.T) {
	gin.SetMode(gin.TestMode)
	ctx, _ := gin.CreateTestContext(httptest.NewRecorder())
	ctx.Request = httptest.NewRequest("GET", "/?defective_reference_gray_mode=global&defective_reference_gray_lut=gray&defective_reference_z_min=0.1&defective_reference_z_max=0.9&defective_reference_bit_depth=12", nil)

	mappings, err := grayMappingsFromQuery(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if mappings.DefectiveReference == nil || mappings.DefectiveReference.BitDepth != 12 {
		t.Fatalf("mapping = %#v", mappings.DefectiveReference)
	}
}

func TestGalleryDownloadRouteStreamsCompletedAttachment(t *testing.T) {
	gin.SetMode(gin.TestMode)
	path := t.TempDir() + "/download.zip"
	if err := os.WriteFile(path, []byte("zip-bytes"), 0o600); err != nil {
		t.Fatal(err)
	}
	stub := &galleryHTTPHandlerStub{result: handler.GalleryDownloadResult{Path: path, Filename: "gallery-images.zip"}}
	router := gin.New()
	RegisterHandler(router.Group("/"), stub)
	payload := `{"items":[{"inspection_time":"2026-08-21T00:00:00Z","wafer_key":1,"defect_id":"42","patch_image_types":["Defective"],"review_image_ids":[]}],"apply_color_mapping":true,"gray_mappings":{"defective_reference":{"enabled":true,"mode":"global","lut":"viridis","zMin":0.1,"zMax":0.9}}}`
	form := url.Values{"payload": []string{payload}}
	request := httptest.NewRequest(http.MethodPost, "/sc/gallery-downloads", strings.NewReader(form.Encode()))
	request.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK || recorder.Body.String() != "zip-bytes" {
		t.Fatalf("response = %d %q", recorder.Code, recorder.Body.String())
	}
	if disposition := recorder.Header().Get("Content-Disposition"); !strings.Contains(disposition, "gallery-images.zip") {
		t.Fatalf("content disposition = %q", disposition)
	}
	if !stub.request.ApplyColorMapping || stub.request.GrayMappings.DefectiveReference == nil || stub.request.GrayMappings.DefectiveReference.LUT != handler.GrayLUTViridis {
		t.Fatalf("request = %#v", stub.request)
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatalf("temporary archive still exists: %v", err)
	}
}

func TestInspectionImageProfileRouteReturnsMultiplePatchInstances(t *testing.T) {
	gin.SetMode(gin.TestMode)
	zero, one := 0, 1
	stub := &galleryHTTPHandlerStub{profile: equipment.InspectionImageProfile{
		InspectionTime: "2026-08-23T00:00:00Z", WaferKey: 9,
		Patches: []equipment.PatchImageProfile{
			{ImageType: "Reference", ImageID: &zero, BitDepth: 12, ZMin: 200, ZMax: 3000},
			{ImageType: "Reference", ImageID: &one, BitDepth: 12, ZMin: 300, ZMax: 3200},
			{ImageType: "Difference", ImageID: &zero, BitDepth: 12, ZMin: 10, ZMax: 1000},
			{ImageType: "Difference", ImageID: &one, BitDepth: 12, ZMin: 20, ZMax: 2000},
			{ImageType: "Mask", ImageID: &zero, BitDepth: 8, ZMin: 0, ZMax: 1},
		},
	}}
	router := gin.New()
	RegisterHandler(router.Group("/"), stub)
	request := httptest.NewRequest(http.MethodGet, "/sc/inspections/2026-08-23T00:00:00Z/9/image-profile", nil)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("response = %d %s", recorder.Code, recorder.Body.String())
	}
	if got := recorder.Header().Get("Cache-Control"); got != "no-store" {
		t.Fatalf("Cache-Control = %q, want no-store", got)
	}
	for _, expected := range []string{
		`"reference_count":2`, `"difference_count":2`, `"mask_count":1`,
		`"image_type":"Reference"`, `"image_id":1`, `"bit_depth":12`, `"z_max":3200`,
	} {
		if !strings.Contains(recorder.Body.String(), expected) {
			t.Fatalf("response missing %s: %s", expected, recorder.Body.String())
		}
	}
}
