package handler

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	imageparserv1 "ft-platform/protos/gen/go/imageparser/v1"
)

type testService struct {
	imageparserv1.UnimplementedImageParserServer
}

func (ts *testService) Health(ctx context.Context, req *imageparserv1.HealthRequest) (*imageparserv1.HealthResponse, error) {
	return &imageparserv1.HealthResponse{Status: "ok"}, nil
}

func newTestHandler(t *testing.T) *Handler {
	t.Helper()
	return New(&testService{})
}

func setupGin(h *Handler) *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.GET("/health", h.Health)
	r.GET("/image", h.GetImage)
	r.GET("/sprite", h.Sprite)
	return r
}

func TestHealth(t *testing.T) {
	h := newTestHandler(t)
	r := setupGin(h)

	req, _ := http.NewRequest("GET", "/health", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != 200 {
		t.Errorf("status = %d, want 200", w.Code)
	}
	if w.Body.String() != `{"status":"ok"}` {
		t.Errorf("body = %s", w.Body.String())
	}
}

func TestGetImage_MissingParams(t *testing.T) {
	h := newTestHandler(t)
	r := setupGin(h)

	tests := []string{
		"/image",
		"/image?bucket=images",
		"/image?bucket=images&key=z.zip",
		"/image?bucket=images&prefix=img",
		"/image?key=z.zip&prefix=img",
	}

	for _, url := range tests {
		req, _ := http.NewRequest("GET", url, nil)
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)
		if w.Code != 400 {
			t.Errorf("%s: status = %d, want 400", url, w.Code)
		}
	}
}

func TestSprite_MissingParams(t *testing.T) {
	h := newTestHandler(t)
	r := setupGin(h)

	tests := []string{
		"/sprite",
		"/sprite?bucket=images",
		"/sprite?bucket=images&key=z.zip",
	}

	for _, url := range tests {
		req, _ := http.NewRequest("GET", url, nil)
		w := httptest.NewRecorder()
		r.ServeHTTP(w, req)
		if w.Code != 400 {
			t.Errorf("%s: status = %d, want 400", url, w.Code)
		}
	}
}

func TestSprite_TooManyPrefixes(t *testing.T) {
	h := newTestHandler(t)
	r := setupGin(h)

	prefixes := "a"
	for i := 0; i < 21; i++ {
		prefixes += ",a"
	}

	url := "/sprite?bucket=b&key=k&prefix=" + prefixes
	req, _ := http.NewRequest("GET", url, nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	if w.Code != 400 {
		t.Errorf("status = %d, want 400", w.Code)
	}
}
