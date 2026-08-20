package service

import (
	"bytes"
	"context"
	"io"
	"net"
	"testing"
	"time"

	imageparserv1 "image-parser/gen/go/imageparser/v1"
	"image-parser/internal/imagestream"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/test/bufconn"
)

type streamTestEngine struct {
	limits     imagestream.Limits
	imageBytes int
}

func (e streamTestEngine) Limits(imagestream.UseCase) imagestream.Limits {
	if e.limits.MaxBatchItems != 0 {
		return e.limits
	}
	return imagestream.Limits{MaxBatchItems: 512, MaxResponseBytes: 16 << 20, MaxActiveContexts: 8}
}

func (e streamTestEngine) Open(_ context.Context, useCase imagestream.UseCase, request imagestream.OpenRequest) (imagestream.Context, error) {
	return &streamTestContext{useCase: useCase, request: request, imageBytes: e.imageBytes}, nil
}

type streamTestContext struct {
	useCase    imagestream.UseCase
	request    imagestream.OpenRequest
	imageBytes int
}

func (c *streamTestContext) EquipmentID() string { return "EQP01" }

func (c *streamTestContext) Resolve(_ context.Context, samples []imagestream.SampleRequest) ([]imagestream.SampleResult, error) {
	results := make([]imagestream.SampleResult, 0, len(samples))
	for index := len(samples) - 1; index >= 0; index-- {
		sample := samples[index]
		images := make([]imagestream.RoleResult, 0, len(c.request.Roles))
		for _, role := range c.request.Roles {
			data := []byte(string(c.useCase) + ":" + role + ":" + sample.DefectID)
			if c.imageBytes > 0 {
				data = bytes.Repeat([]byte{'x'}, c.imageBytes)
			}
			images = append(images, imagestream.RoleResult{
				Role:        role,
				Data:        data,
				ContentType: "image/png",
			})
		}
		results = append(results, imagestream.SampleResult{
			Sequence: sample.Sequence,
			SampleID: sample.SampleID,
			DefectID: sample.DefectID,
			Images:   images,
		})
	}
	return results, nil
}

func TestPredictionImageStreamSplitsResponsesAtAdvertisedByteLimit(t *testing.T) {
	service := NewScImageService(streamTestEngine{
		limits:     imagestream.Limits{MaxBatchItems: 8, MaxResponseBytes: 700, MaxActiveContexts: 1},
		imageBytes: 400,
	})
	client, cleanup := startImageStreamTestServer(t, service)
	defer cleanup()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	stream, err := client.StreamPredictionImages(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if err := stream.Send(openContextRequest("inspection-1")); err != nil {
		t.Fatal(err)
	}
	if _, err := stream.Recv(); err != nil {
		t.Fatal(err)
	}
	if err := stream.Send(&imageparserv1.StreamImagesRequest{Payload: &imageparserv1.StreamImagesRequest_SampleBatch{
		SampleBatch: &imageparserv1.ImageSampleBatchRequest{ContextId: "inspection-1", Samples: []*imageparserv1.ImageSampleRequest{
			{Sequence: 1, SampleId: "sample-1", DefectId: "1"},
			{Sequence: 2, SampleId: "sample-2", DefectId: "2"},
		}},
	}}); err != nil {
		t.Fatal(err)
	}
	first, err := stream.Recv()
	if err != nil {
		t.Fatal(err)
	}
	second, err := stream.Recv()
	if err != nil {
		t.Fatal(err)
	}
	if len(first.GetSampleBatch().GetSamples()) != 1 || first.GetSampleBatch().GetAckSequence() != 1 {
		t.Fatalf("first response = %#v", first)
	}
	if len(second.GetSampleBatch().GetSamples()) != 1 || second.GetSampleBatch().GetAckSequence() != 2 {
		t.Fatalf("second response = %#v", second)
	}
}

func TestPredictionImageStreamClosesIdleContextWithoutEndingStream(t *testing.T) {
	service := NewScImageService(streamTestEngine{})
	service.contextIdleTimeout = 20 * time.Millisecond
	client, cleanup := startImageStreamTestServer(t, service)
	defer cleanup()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	stream, err := client.StreamPredictionImages(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if err := stream.Send(openContextRequest("idle-context")); err != nil {
		t.Fatal(err)
	}
	if _, err := stream.Recv(); err != nil {
		t.Fatal(err)
	}
	idle, err := stream.Recv()
	if err != nil {
		t.Fatal(err)
	}
	if idle.GetContextError().GetCode() != "context_idle_timeout" {
		t.Fatalf("idle response = %#v", idle)
	}
	if err := stream.Send(openContextRequest("replacement-context")); err != nil {
		t.Fatal(err)
	}
	if opened, err := stream.Recv(); err != nil || opened.GetContextOpened().GetContextId() != "replacement-context" {
		t.Fatalf("replacement open = %#v, %v", opened, err)
	}
}

func openContextRequest(contextID string) *imageparserv1.StreamImagesRequest {
	return &imageparserv1.StreamImagesRequest{Payload: &imageparserv1.StreamImagesRequest_OpenContext{
		OpenContext: &imageparserv1.OpenImageContext{
			ContextId: contextID, InspectionTime: "2026-08-21T00:00:00Z", WaferKey: 7, Roles: []string{"patch_defective"},
		},
	}}
}

func (*streamTestContext) Close() error { return nil }

func TestPredictionImageStreamOpensContextAndReturnsSamplesInSequenceOrder(t *testing.T) {
	service := NewScImageService(streamTestEngine{})
	client, cleanup := startImageStreamTestServer(t, service)
	defer cleanup()

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	stream, err := client.StreamPredictionImages(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if err := stream.Send(&imageparserv1.StreamImagesRequest{Payload: &imageparserv1.StreamImagesRequest_OpenContext{
		OpenContext: &imageparserv1.OpenImageContext{
			ContextId:      "inspection-1",
			InspectionTime: "2026-08-21T00:00:00Z",
			WaferKey:       7,
			Roles:          []string{"patch_defective", "patch_template"},
		},
	}}); err != nil {
		t.Fatal(err)
	}
	opened, err := stream.Recv()
	if err != nil {
		t.Fatal(err)
	}
	if opened.GetContextOpened().GetEqpId() != "EQP01" {
		t.Fatalf("equipment = %q", opened.GetContextOpened().GetEqpId())
	}
	if opened.GetContextOpened().GetLimits().GetMaxBatchItems() != 512 {
		t.Fatalf("limits = %#v", opened.GetContextOpened().GetLimits())
	}

	if err := stream.Send(&imageparserv1.StreamImagesRequest{Payload: &imageparserv1.StreamImagesRequest_SampleBatch{
		SampleBatch: &imageparserv1.ImageSampleBatchRequest{
			ContextId: "inspection-1",
			Samples: []*imageparserv1.ImageSampleRequest{
				{Sequence: 10, SampleId: "sample-10", DefectId: "10"},
				{Sequence: 11, SampleId: "sample-11", DefectId: "11"},
			},
		},
	}}); err != nil {
		t.Fatal(err)
	}
	batch, err := stream.Recv()
	if err != nil {
		t.Fatal(err)
	}
	results := batch.GetSampleBatch().GetSamples()
	if len(results) != 2 || results[0].GetSequence() != 10 || results[1].GetSequence() != 11 {
		t.Fatalf("results not ordered: %#v", results)
	}
	if got := string(results[0].GetImages()[0].GetImageData()); got != "prediction:patch_defective:10" {
		t.Fatalf("image data = %q", got)
	}
	if batch.GetSampleBatch().GetAckSequence() != 11 {
		t.Fatalf("ack = %d", batch.GetSampleBatch().GetAckSequence())
	}

	if err := stream.Send(&imageparserv1.StreamImagesRequest{Payload: &imageparserv1.StreamImagesRequest_CloseContext{
		CloseContext: &imageparserv1.CloseImageContext{ContextId: "inspection-1"},
	}}); err != nil {
		t.Fatal(err)
	}
	closed, err := stream.Recv()
	if err != nil {
		t.Fatal(err)
	}
	if closed.GetContextClosed().GetContextId() != "inspection-1" {
		t.Fatalf("closed = %#v", closed)
	}
	if err := stream.CloseSend(); err != nil {
		t.Fatal(err)
	}
	if _, err := stream.Recv(); err != io.EOF {
		t.Fatalf("final recv = %v, want EOF", err)
	}
}

func startImageStreamTestServer(t *testing.T, service *ScImageService) (imageparserv1.ImageParserClient, func()) {
	t.Helper()
	listener := bufconn.Listen(1 << 20)
	server := grpc.NewServer()
	imageparserv1.RegisterImageParserServer(server, service)
	go func() { _ = server.Serve(listener) }()
	connection, err := grpc.NewClient(
		"passthrough:///image-stream-test",
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithContextDialer(func(context.Context, string) (net.Conn, error) { return listener.Dial() }),
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
