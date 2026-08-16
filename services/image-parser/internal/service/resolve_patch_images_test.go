package service

import (
	"context"
	"errors"
	"io"
	"net"
	"testing"
	"time"

	imageparserv1 "image-parser/gen/go/imageparser/v1"
	imageloader "image-parser/internal/image_loader"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
)

type patchResolverLoader struct {
	waitForCancellation bool
	entered             chan struct{}
	cancelObserved      chan struct{}
}

func (l *patchResolverLoader) GetImageBytes(context.Context, []imageloader.ImageKey) []imageloader.ImageBytes {
	return nil
}

func (l *patchResolverLoader) WarmInspection(context.Context, imageloader.InspectionKey, []string, string) (int, error) {
	return 0, nil
}

func (l *patchResolverLoader) ResolvePatchImageBytes(ctx context.Context, profile string, keys []imageloader.ImageKey) ([]imageloader.ImageBytes, error) {
	if profile != "known" {
		return nil, errors.New("unknown image source profile")
	}
	if len(keys) == 0 {
		return nil, nil
	}
	if l.waitForCancellation {
		close(l.entered)
		<-ctx.Done()
		close(l.cancelObserved)
		return nil, ctx.Err()
	}
	results := make([]imageloader.ImageBytes, len(keys))
	for index, key := range keys {
		results[index] = imageloader.ImageBytes{
			Key:         key,
			Data:        []byte("fixture"),
			ContentType: "image/png",
		}
		if key.DefectID == "2" {
			results[index].Data = nil
			results[index].Err = errors.New("archive missing")
		}
	}
	return results, nil
}

func TestResolvePatchImagesPreservesCorrelationAndItemErrors(t *testing.T) {
	client, cleanup := startPatchResolverServer(t, &patchResolverLoader{})
	defer cleanup()
	stream, err := client.ResolvePatchImages(context.Background(), &imageparserv1.ResolvePatchImagesRequest{
		SourceProfile: "known",
		Roles:         []string{"patch_template", "patch_defective"},
		Items: []*imageparserv1.ResolvePatchImageItem{
			{RequestId: "r1", SampleId: "s1", InspectionTime: "20260816_100000", WaferKey: 42, DefectId: "1"},
			{RequestId: "r2", SampleId: "s2", InspectionTime: "20260816_100000", WaferKey: 42, DefectId: "2"},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	var results []*imageparserv1.ResolvePatchImageResult
	for {
		result, recvErr := stream.Recv()
		if recvErr == io.EOF {
			break
		}
		if recvErr != nil {
			t.Fatal(recvErr)
		}
		results = append(results, result)
	}
	if len(results) != 4 {
		t.Fatalf("result count = %d, want 4", len(results))
	}
	if results[0].RequestId != "r1" || results[0].SampleId != "s1" || results[0].Role != "patch_template" {
		t.Fatalf("first result correlation = %#v", results[0])
	}
	if results[0].Error != "" || string(results[0].ImageData) != "fixture" {
		t.Fatalf("first result payload = %#v", results[0])
	}
	if results[2].RequestId != "r2" || results[2].Error != "archive missing" {
		t.Fatalf("item error result = %#v", results[2])
	}
}

func TestResolvePatchImagesRejectsUnknownProfileAndInvalidRequest(t *testing.T) {
	client, cleanup := startPatchResolverServer(t, &patchResolverLoader{})
	defer cleanup()
	for _, request := range []*imageparserv1.ResolvePatchImagesRequest{
		{SourceProfile: "unknown", Roles: []string{"patch_template"}, Items: validPatchItems()},
		{SourceProfile: "known", Roles: []string{"review"}, Items: validPatchItems()},
		{SourceProfile: "known", Roles: []string{"patch_template"}, Items: []*imageparserv1.ResolvePatchImageItem{{RequestId: "r1", SampleId: "s1", InspectionTime: "../bad", WaferKey: 42, DefectId: "1"}}},
	} {
		stream, err := client.ResolvePatchImages(context.Background(), request)
		if err == nil {
			_, err = stream.Recv()
		}
		if status.Code(err) != codes.InvalidArgument {
			t.Fatalf("status = %v, want InvalidArgument", err)
		}
	}
}

func TestResolvePatchImagesPropagatesClientCancellation(t *testing.T) {
	loader := &patchResolverLoader{
		waitForCancellation: true,
		entered:             make(chan struct{}),
		cancelObserved:      make(chan struct{}),
	}
	client, cleanup := startPatchResolverServer(t, loader)
	defer cleanup()
	ctx, cancel := context.WithCancel(context.Background())
	stream, err := client.ResolvePatchImages(ctx, &imageparserv1.ResolvePatchImagesRequest{
		SourceProfile: "known",
		Roles:         []string{"patch_template"},
		Items:         validPatchItems(),
	})
	if err != nil {
		t.Fatal(err)
	}
	select {
	case <-loader.entered:
	case <-time.After(time.Second):
		t.Fatal("resolver did not start")
	}
	cancel()
	_, err = stream.Recv()
	if status.Code(err) != codes.Canceled {
		t.Fatalf("status = %v, want Canceled", err)
	}
	select {
	case <-loader.cancelObserved:
	case <-time.After(time.Second):
		t.Fatal("resolver did not observe canceled RPC context")
	}
}

func validPatchItems() []*imageparserv1.ResolvePatchImageItem {
	return []*imageparserv1.ResolvePatchImageItem{{
		RequestId:      "r1",
		SampleId:       "s1",
		InspectionTime: "20260816_100000",
		WaferKey:       42,
		DefectId:       "1",
	}}
}

func startPatchResolverServer(t *testing.T, loader imageloader.ImageLoader) (imageparserv1.ImageParserClient, func()) {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	server := grpc.NewServer()
	imageparserv1.RegisterImageParserServer(server, NewScImageService(loader))
	go func() {
		_ = server.Serve(listener)
	}()
	connection, err := grpc.NewClient(
		listener.Addr().String(),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		server.Stop()
		_ = listener.Close()
		t.Fatal(err)
	}
	return imageparserv1.NewImageParserClient(connection), func() {
		_ = connection.Close()
		server.Stop()
		_ = listener.Close()
	}
}
