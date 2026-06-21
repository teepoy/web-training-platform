package main

import (
	"net/http/httptest"
	"reflect"
	"testing"

	"github.com/gin-gonic/gin"
	"image-parser/internal/handler"
	imageloader "image-parser/internal/image_loader"
)

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
