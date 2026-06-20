package handler

import (
	"net/http/httptest"
	"reflect"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestReviewSpritePatchPrefixOrder(t *testing.T) {
	want := []string{"defective", "template", "difference"}
	if !reflect.DeepEqual(reviewSpritePatchImageTypes, want) {
		t.Fatalf("reviewSpritePatchImageTypes = %#v, want %#v", reviewSpritePatchImageTypes, want)
	}
}

func TestPatchSpriteOrderRemainsDefectiveFirst(t *testing.T) {
	want := []string{"defective", "template", "difference"}
	if !reflect.DeepEqual(patchSpriteImageTypes, want) {
		t.Fatalf("patchSpriteImageTypes = %#v, want %#v", patchSpriteImageTypes, want)
	}
}

func TestPatchImageTypesFromQuery(t *testing.T) {
	gin.SetMode(gin.TestMode)
	ctx, _ := gin.CreateTestContext(httptest.NewRecorder())
	req := httptest.NewRequest("GET", "/?image_types=difference&image_types=reference&image_types=review", nil)
	ctx.Request = req

	got := patchImageTypesFromQuery(ctx, patchSpriteImageTypes)
	want := []string{"difference", "template"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("patchImageTypesFromQuery = %#v, want %#v", got, want)
	}
}
