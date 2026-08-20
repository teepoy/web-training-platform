package handler

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
)

func TestSafeRequestLoggerDoesNotLogQueryToken(t *testing.T) {
	gin.SetMode(gin.TestMode)
	var output bytes.Buffer
	previous := gin.DefaultWriter
	gin.DefaultWriter = &output
	t.Cleanup(func() { gin.DefaultWriter = previous })

	router := gin.New()
	router.Use(SafeRequestLogger())
	router.GET("/sc/images/:id", func(c *gin.Context) { c.Status(http.StatusNoContent) })
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/sc/images/1?token=secret-token&org_id=org", nil))

	if strings.Contains(output.String(), "secret-token") || strings.Contains(output.String(), "org_id") {
		t.Fatalf("request log exposed query parameters: %q", output.String())
	}
	if !strings.Contains(output.String(), "/sc/images/1") {
		t.Fatalf("request log omitted safe path: %q", output.String())
	}
}

func TestJWTAuthAcceptsBrowserQueryTokenAndBearerHeader(t *testing.T) {
	gin.SetMode(gin.TestMode)
	secret := []byte("test-image-parser-secret")
	token := signedToken(t, secret)
	for name, configure := range map[string]func(*http.Request){
		"query":  func(request *http.Request) { request.URL.RawQuery = "token=" + token },
		"header": func(request *http.Request) { request.Header.Set("Authorization", "Bearer "+token) },
	} {
		t.Run(name, func(t *testing.T) {
			router := gin.New()
			router.Use(JWTAuth(secret))
			router.GET("/image", func(ctx *gin.Context) { ctx.Status(http.StatusNoContent) })
			request := httptest.NewRequest(http.MethodGet, "/image", nil)
			configure(request)
			response := httptest.NewRecorder()
			router.ServeHTTP(response, request)
			if response.Code != http.StatusNoContent {
				t.Fatalf("status = %d, body=%s", response.Code, response.Body.String())
			}
		})
	}
}

func TestJWTAuthRejectsMissingOrConflictingTokens(t *testing.T) {
	gin.SetMode(gin.TestMode)
	secret := []byte("test-image-parser-secret")
	valid := signedToken(t, secret)
	for name, request := range map[string]*http.Request{
		"missing": httptest.NewRequest(http.MethodGet, "/image", nil),
		"conflicting": httptest.NewRequest(
			http.MethodGet, "/image?token="+valid+"-different", nil,
		),
	} {
		t.Run(name, func(t *testing.T) {
			if name == "conflicting" {
				request.Header.Set("Authorization", "Bearer "+valid)
			}
			router := gin.New()
			router.Use(JWTAuth(secret))
			router.GET("/image", func(ctx *gin.Context) { ctx.Status(http.StatusNoContent) })
			response := httptest.NewRecorder()
			router.ServeHTTP(response, request)
			if response.Code != http.StatusUnauthorized {
				t.Fatalf("status = %d, body=%s", response.Code, response.Body.String())
			}
		})
	}
}

func TestJWTAuthFromEnvironmentRequiresSigningKey(t *testing.T) {
	t.Setenv("JWT_SECRET_KEY", "")
	if _, err := JWTAuthFromEnvironment(); err == nil {
		t.Fatal("missing JWT_SECRET_KEY was accepted")
	}
}

func signedToken(t *testing.T, secret []byte) string {
	t.Helper()
	claims := jwt.MapClaims{"sub": "user-1", "exp": time.Now().Add(time.Hour).Unix()}
	token, err := jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString(secret)
	if err != nil {
		t.Fatal(err)
	}
	return token
}
