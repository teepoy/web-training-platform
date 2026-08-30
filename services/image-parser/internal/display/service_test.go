package display

import (
	"context"
	"fmt"
	"testing"

	scv1 "image-parser/gen/go/sc/v1"
	"image-parser/internal/imagestream"
)

type displayUpstreamStub struct{}

func (displayUpstreamStub) GetInspection(context.Context, string, int32) (*scv1.GetInspectionResponse, error) {
	return nil, fmt.Errorf("unexpected inspection lookup")
}

func (displayUpstreamStub) GetReviewImageFileSpec(context.Context, string, int32, int32, int32) (*scv1.GetReviewImageFileSpecResponse, error) {
	return nil, fmt.Errorf("unexpected review lookup")
}

type reviewSourceStub struct{}

func (reviewSourceStub) ReadReviewImage(context.Context, string) ([]byte, error) {
	return nil, fmt.Errorf("unexpected review read")
}

type recordingStreamEngine struct {
	useCases []imagestream.UseCase
	context  *recordingStreamContext
}

func (e *recordingStreamEngine) Limits(imagestream.UseCase) imagestream.Limits {
	return imagestream.Limits{MaxBatchItems: 512, MaxResponseBytes: 64 << 20, MaxActiveContexts: 4}
}

func (e *recordingStreamEngine) Open(_ context.Context, useCase imagestream.UseCase, _ imagestream.OpenRequest) (imagestream.Context, error) {
	e.useCases = append(e.useCases, useCase)
	e.context = &recordingStreamContext{}
	return e.context, nil
}

type recordingStreamContext struct{ batchSizes []int }

func (*recordingStreamContext) EquipmentID() string { return "test" }

func (c *recordingStreamContext) Resolve(_ context.Context, requests []imagestream.SampleRequest) ([]imagestream.SampleResult, error) {
	c.batchSizes = append(c.batchSizes, len(requests))
	results := make([]imagestream.SampleResult, len(requests))
	for index, request := range requests {
		results[index] = imagestream.SampleResult{
			Sequence: request.Sequence, SampleID: request.SampleID, DefectID: request.DefectID,
			Images: []imagestream.RoleResult{{Role: "Defective", Data: []byte(request.DefectID), ContentType: "image/png"}},
		}
	}
	return results, nil
}

func (*recordingStreamContext) Close() error { return nil }

func TestExportReaderUsesExportLaneAndBoundedBatches(t *testing.T) {
	engine := &recordingStreamEngine{}
	reader, err := NewForUseCase(displayUpstreamStub{}, reviewSourceStub{}, engine, imagestream.UseCaseExport)
	if err != nil {
		t.Fatal(err)
	}
	keys := make([]ImageKey, 600)
	for index := range keys {
		keys[index] = ImageKey{
			Kind: ImageKindPatch, InspectionKey: InspectionKey{InspectionTime: "2026-08-21T00:00:00Z", WaferKey: 1},
			DefectID: fmt.Sprint(index + 1), ImageType: "Defective",
		}
	}
	results := reader.GetImageBytes(context.Background(), keys)
	if len(results) != len(keys) || results[599].Err != nil {
		t.Fatalf("results = %d, last error = %v", len(results), results[599].Err)
	}
	if len(engine.useCases) != 1 || engine.useCases[0] != imagestream.UseCaseExport {
		t.Fatalf("opened use cases = %v, want export", engine.useCases)
	}
	if got := engine.context.batchSizes; len(got) != 2 || got[0] != 512 || got[1] != 88 {
		t.Fatalf("resolve batch sizes = %v, want [512 88]", got)
	}
}
