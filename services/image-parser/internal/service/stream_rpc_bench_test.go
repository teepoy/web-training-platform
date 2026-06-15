package service

import (
	"archive/zip"
	"bytes"
	"context"
	"fmt"
	"io"
	"net"
	"testing"
	"time"

	imageparserv1 "image-parser/gen/go/imageparser/v1"
	scv1 "image-parser/gen/go/sc/v1"
	"image-parser/internal/cache"
	"image-parser/internal/client"
	"image-parser/internal/resolve"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

const rpcBenchmarkDefects = 300_000
const rpcBenchmarkDefectsPerZip = 500

func BenchmarkStreamScInspectionImagesRPC300KDefects(b *testing.B) {
	upstreamAddr, upstreamCleanup := startBenchmarkUpstream(b)
	defer upstreamCleanup()
	b.Setenv("SC_UPSTREAM_ADDR", upstreamAddr)

	zipCache, err := cache.New(1024, 10*time.Minute)
	if err != nil {
		b.Fatal(err)
	}
	defer zipCache.Close()

	zipCount := rpcBenchmarkDefects / rpcBenchmarkDefectsPerZip
	zips := make([]resolve.CacheZipRef, 0, zipCount)
	for i := range zipCount {
		ref := resolve.CacheZipRef{Bucket: benchmarkBucket, Key: benchmarkZipKey(i)}
		zips = append(zips, ref)
		zipBytes := makeRPCBenchmarkZip(b, i*rpcBenchmarkDefectsPerZip, rpcBenchmarkDefectsPerZip)
		if err := zipCache.Set(cache.CacheKey(ref.Bucket, ref.Key), zipBytes); err != nil {
			b.Fatal(err)
		}
	}
	benchmarkZips = zips

	upstream, err := client.NewUpstreamClient()
	if err != nil {
		b.Fatal(err)
	}
	defer upstream.Close()

	resolver := resolve.New(upstream, zipCache, nil)
	imageParserAddr, imageParserCleanup := startBenchmarkImageParser(b, NewScImageService(resolver))
	defer imageParserCleanup()

	conn, err := grpc.NewClient(imageParserAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		b.Fatal(err)
	}
	defer conn.Close()
	stub := imageparserv1.NewImageParserClient(conn)

	defectIDs := make([]int32, rpcBenchmarkDefects)
	for i := range defectIDs {
		defectIDs[i] = int32(i)
	}
	req := &imageparserv1.StreamScInspectionImagesRequest{
		InspectionTime: "2026-01-01T00:00:00",
		WaferKey:       1,
		DefectIds:      defectIDs,
		ImageTypes:     []string{"patch_template", "patch_defective"},
	}

	b.ReportAllocs()
	b.ResetTimer()
	for range b.N {
		stream, err := stub.StreamScInspectionImages(context.Background(), req)
		if err != nil {
			b.Fatal(err)
		}
		count := 0
		for {
			msg, err := stream.Recv()
			if err == io.EOF {
				break
			}
			if err != nil {
				b.Fatal(err)
			}
			if msg.Error != "" {
				b.Fatalf("stream item failed: %s", msg.Error)
			}
			count++
		}
		want := rpcBenchmarkDefects * 2
		if count != want {
			b.Fatalf("stream count mismatch: got %d want %d", count, want)
		}
	}
}

const benchmarkBucket = "bench"

var benchmarkZips []resolve.CacheZipRef

type benchmarkUpstream struct {
	scv1.UnimplementedScUpstreamServer
}

func (s *benchmarkUpstream) GetInspection(context.Context, *scv1.GetInspectionRequest) (*scv1.GetInspectionResponse, error) {
	return &scv1.GetInspectionResponse{
		InspectionTime: "2026-01-01T00:00:00",
		WaferKey:       1,
		LotId:          "lot",
		WaferId:        "wafer",
		Device:         "device",
		LayerId:        "layer",
		Defects:        rpcBenchmarkDefects,
		Images:         rpcBenchmarkDefects * 2,
	}, nil
}

func (s *benchmarkUpstream) GetInspectionPatchZips(context.Context, *scv1.GetInspectionPatchZipsRequest) (*scv1.GetInspectionPatchZipsResponse, error) {
	zips := make([]*scv1.ZipRef, 0, len(benchmarkZips))
	for _, ref := range benchmarkZips {
		zips = append(zips, &scv1.ZipRef{S3Bucket: ref.Bucket, S3Key: ref.Key})
	}
	return &scv1.GetInspectionPatchZipsResponse{Zips: zips}, nil
}

func startBenchmarkUpstream(b *testing.B) (string, func()) {
	b.Helper()
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		b.Fatal(err)
	}
	server := grpc.NewServer()
	scv1.RegisterScUpstreamServer(server, &benchmarkUpstream{})
	go func() {
		_ = server.Serve(lis)
	}()
	return lis.Addr().String(), func() {
		server.Stop()
		_ = lis.Close()
	}
}

func startBenchmarkImageParser(b *testing.B, svc *ScImageService) (string, func()) {
	b.Helper()
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		b.Fatal(err)
	}
	server := grpc.NewServer()
	imageparserv1.RegisterImageParserServer(server, svc)
	go func() {
		_ = server.Serve(lis)
	}()
	return lis.Addr().String(), func() {
		server.Stop()
		_ = lis.Close()
	}
}

func benchmarkZipKey(index int) string {
	return fmt.Sprintf("patch-%04d.zip", index)
}

func makeRPCBenchmarkZip(b *testing.B, startDefectID int, defects int) []byte {
	b.Helper()
	var buf bytes.Buffer
	zw := zip.NewWriter(&buf)
	for offset := range defects {
		defectID := startDefectID + offset
		for _, suffix := range []string{"Template", "Defective"} {
			w, err := zw.Create(fmt.Sprintf("%06d_Patch%s.png", defectID, suffix))
			if err != nil {
				b.Fatal(err)
			}
			if _, err := w.Write([]byte{0x89, 'P', 'N', 'G', byte(defectID), byte(len(suffix))}); err != nil {
				b.Fatal(err)
			}
		}
	}
	if err := zw.Close(); err != nil {
		b.Fatal(err)
	}
	return buf.Bytes()
}
