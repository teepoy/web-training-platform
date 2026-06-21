package service

import (
	"context"
	"io"
	"net"
	"testing"

	imageparserv1 "image-parser/gen/go/imageparser/v1"
	imageloader "image-parser/internal/image_loader"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

const rpcBenchmarkDefects = 300_000

func BenchmarkStreamScInspectionImagesRPC300KDefects(b *testing.B) {
	imageParserAddr, imageParserCleanup := startBenchmarkImageParser(b, NewScImageService(benchmarkImageLoader{
		image: []byte{0x89, 'P', 'N', 'G'},
	}))
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
		ImageTypes:     []string{"Reference", "Defective"},
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

type benchmarkImageLoader struct {
	image []byte
}

func (l benchmarkImageLoader) GetImageBytes(ctx context.Context, keys []imageloader.ImageKey) []imageloader.ImageBytes {
	results := make([]imageloader.ImageBytes, len(keys))
	for i, key := range keys {
		results[i] = imageloader.ImageBytes{Key: key, Data: l.image, ContentType: "image/png"}
	}
	return results
}

func (l benchmarkImageLoader) WarmInspection(context.Context, imageloader.InspectionKey, []string, string) (int, error) {
	return 0, nil
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
