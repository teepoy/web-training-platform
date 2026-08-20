package metrics

import (
	"context"
	"fmt"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"

	"github.com/gin-gonic/gin"
	"google.golang.org/grpc"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/proto"
	"image-parser/internal/artifactcache"
	"image-parser/internal/imagestream"
)

type counterVec struct {
	mu     sync.RWMutex
	values map[string]*atomic.Int64
}

func newCounterVec() *counterVec {
	return &counterVec{values: map[string]*atomic.Int64{}}
}

func (v *counterVec) add(labels string, value int64) {
	if value < 0 {
		value = 0
	}
	counter := v.get(labels)
	counter.Add(value)
}

func (v *counterVec) get(labels string) *atomic.Int64 {
	v.mu.RLock()
	counter := v.values[labels]
	v.mu.RUnlock()
	if counter != nil {
		return counter
	}

	v.mu.Lock()
	defer v.mu.Unlock()
	counter = v.values[labels]
	if counter == nil {
		counter = &atomic.Int64{}
		v.values[labels] = counter
	}
	return counter
}

func (v *counterVec) snapshot() map[string]int64 {
	v.mu.RLock()
	defer v.mu.RUnlock()
	out := make(map[string]int64, len(v.values))
	for labels, value := range v.values {
		out[labels] = value.Load()
	}
	return out
}

var (
	httpRequestsTotal      = newCounterVec()
	httpRequestBytesTotal  = newCounterVec()
	httpResponseBytesTotal = newCounterVec()
	httpInFlightRequests   atomic.Int64

	grpcRequestsTotal      = newCounterVec()
	grpcRequestBytesTotal  = newCounterVec()
	grpcResponseBytesTotal = newCounterVec()
	grpcInFlightRequests   atomic.Int64
	imageSamplesTotal      = newCounterVec()
	imageSampleErrorsTotal = newCounterVec()
	imageBytesTotal        = newCounterVec()
	artifactCachesMu       sync.RWMutex
	artifactCaches         = map[string]*artifactcache.Manager{}
)

func RegisterArtifactCache(namespace string, manager *artifactcache.Manager) {
	artifactCachesMu.Lock()
	defer artifactCachesMu.Unlock()
	artifactCaches[namespace] = manager
}

func ObserveImageSamples(useCase imagestream.UseCase, samples, errors, bytes int64) {
	label := labels(map[string]string{"use_case": string(useCase)})
	imageSamplesTotal.add(label, samples)
	imageSampleErrorsTotal.add(label, errors)
	imageBytesTotal.add(label, bytes)
}

func GinTrafficMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		httpInFlightRequests.Add(1)
		defer httpInFlightRequests.Add(-1)

		c.Next()

		path := c.FullPath()
		if path == "" {
			path = "unmatched"
		}
		statusCode := strconv.Itoa(c.Writer.Status())
		labels := labels(map[string]string{
			"method": c.Request.Method,
			"path":   path,
			"status": statusCode,
		})
		httpRequestsTotal.add(labels, 1)
		httpRequestBytesTotal.add(labels, c.Request.ContentLength)
		httpResponseBytesTotal.add(labels, int64(c.Writer.Size()))
	}
}

func GRPCUnaryInterceptor() grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req interface{}, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (interface{}, error) {
		grpcInFlightRequests.Add(1)
		defer grpcInFlightRequests.Add(-1)

		resp, err := handler(ctx, req)
		observeGRPC(info.FullMethod, status.Code(err).String(), protoMessageSize(req), protoMessageSize(resp))
		return resp, err
	}
}

func GRPCStreamInterceptor() grpc.StreamServerInterceptor {
	return func(srv interface{}, stream grpc.ServerStream, info *grpc.StreamServerInfo, handler grpc.StreamHandler) error {
		grpcInFlightRequests.Add(1)
		defer grpcInFlightRequests.Add(-1)

		wrapped := &meteredServerStream{ServerStream: stream}
		err := handler(srv, wrapped)
		observeGRPC(info.FullMethod, status.Code(err).String(), wrapped.requestBytes.Load(), wrapped.responseBytes.Load())
		return err
	}
}

func Handler(c *gin.Context) {
	c.Header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
	c.String(http.StatusOK, Render())
}

func Render() string {
	var b strings.Builder
	writeGauge(&b, "image_parser_http_in_flight_requests", "Current image-parser HTTP requests in flight.", httpInFlightRequests.Load())
	writeCounter(&b, "image_parser_http_requests_total", "Total image-parser HTTP requests.", httpRequestsTotal.snapshot())
	writeCounter(&b, "image_parser_http_request_bytes_total", "Total image-parser HTTP request body bytes observed from Content-Length.", httpRequestBytesTotal.snapshot())
	writeCounter(&b, "image_parser_http_response_bytes_total", "Total image-parser HTTP response bytes written.", httpResponseBytesTotal.snapshot())
	writeGauge(&b, "image_parser_grpc_in_flight_requests", "Current image-parser gRPC requests in flight.", grpcInFlightRequests.Load())
	writeCounter(&b, "image_parser_grpc_requests_total", "Total image-parser gRPC requests.", grpcRequestsTotal.snapshot())
	writeCounter(&b, "image_parser_grpc_request_bytes_total", "Total image-parser gRPC protobuf request bytes.", grpcRequestBytesTotal.snapshot())
	writeCounter(&b, "image_parser_grpc_response_bytes_total", "Total image-parser gRPC protobuf response bytes.", grpcResponseBytesTotal.snapshot())
	writeCounter(&b, "image_parser_image_samples_total", "Total image samples resolved by semantic use case.", imageSamplesTotal.snapshot())
	writeCounter(&b, "image_parser_image_sample_errors_total", "Total image sample errors by semantic use case.", imageSampleErrorsTotal.snapshot())
	writeCounter(&b, "image_parser_image_bytes_total", "Total image payload bytes returned by semantic use case.", imageBytesTotal.snapshot())
	writeArtifactCacheCounters(&b)
	return b.String()
}

func writeArtifactCacheCounters(b *strings.Builder) {
	artifactCachesMu.RLock()
	defer artifactCachesMu.RUnlock()
	metrics := []struct {
		name string
		help string
		read func(artifactcache.Stats) int64
	}{
		{"image_parser_artifact_cache_hits_total", "Total artifact cache hits.", func(stats artifactcache.Stats) int64 { return stats.Hits }},
		{"image_parser_artifact_cache_misses_total", "Total artifact cache misses.", func(stats artifactcache.Stats) int64 { return stats.Misses }},
		{"image_parser_artifact_cache_downloads_total", "Total artifacts published after download.", func(stats artifactcache.Stats) int64 { return stats.Downloads }},
		{"image_parser_artifact_cache_evictions_total", "Total artifact cache evictions.", func(stats artifactcache.Stats) int64 { return stats.Evictions }},
	}
	for _, metric := range metrics {
		samples := make(map[string]int64, len(artifactCaches))
		for namespace, manager := range artifactCaches {
			samples[labels(map[string]string{"namespace": namespace})] = metric.read(manager.Stats())
		}
		writeCounter(b, metric.name, metric.help, samples)
	}
}

type meteredServerStream struct {
	grpc.ServerStream
	requestBytes  atomic.Int64
	responseBytes atomic.Int64
}

func (s *meteredServerStream) RecvMsg(m interface{}) error {
	err := s.ServerStream.RecvMsg(m)
	if err == nil {
		s.requestBytes.Add(protoMessageSize(m))
	}
	return err
}

func (s *meteredServerStream) SendMsg(m interface{}) error {
	err := s.ServerStream.SendMsg(m)
	if err == nil {
		s.responseBytes.Add(protoMessageSize(m))
	}
	return err
}

func observeGRPC(method string, code string, requestBytes int64, responseBytes int64) {
	labels := labels(map[string]string{
		"method": method,
		"status": code,
	})
	grpcRequestsTotal.add(labels, 1)
	grpcRequestBytesTotal.add(labels, requestBytes)
	grpcResponseBytesTotal.add(labels, responseBytes)
}

func protoMessageSize(value interface{}) int64 {
	msg, ok := value.(proto.Message)
	if !ok || msg == nil {
		return 0
	}
	return int64(proto.Size(msg))
}

func writeGauge(b *strings.Builder, name string, help string, value int64) {
	fmt.Fprintf(b, "# HELP %s %s\n", name, help)
	fmt.Fprintf(b, "# TYPE %s gauge\n", name)
	fmt.Fprintf(b, "%s %d\n", name, value)
}

func writeCounter(b *strings.Builder, name string, help string, samples map[string]int64) {
	fmt.Fprintf(b, "# HELP %s %s\n", name, help)
	fmt.Fprintf(b, "# TYPE %s counter\n", name)
	keys := make([]string, 0, len(samples))
	for key := range samples {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for _, key := range keys {
		fmt.Fprintf(b, "%s%s %d\n", name, key, samples[key])
	}
}

func labels(items map[string]string) string {
	keys := make([]string, 0, len(items))
	for key := range items {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	parts := make([]string, 0, len(keys))
	for _, key := range keys {
		parts = append(parts, fmt.Sprintf(`%s="%s"`, key, escapeLabel(items[key])))
	}
	return "{" + strings.Join(parts, ",") + "}"
}

func escapeLabel(value string) string {
	value = strings.ReplaceAll(value, `\`, `\\`)
	value = strings.ReplaceAll(value, "\n", `\n`)
	value = strings.ReplaceAll(value, `"`, `\"`)
	return value
}
