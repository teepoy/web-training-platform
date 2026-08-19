package service

import (
	"context"
	"errors"
	"testing"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	imageparserv1 "image-parser/gen/go/imageparser/v1"
	imageloader "image-parser/internal/image_loader"
)

type patchResolverLoader struct {
	waitForCancellation bool
	entered             chan struct{}
	cancelObserved      chan struct{}
	lastKeys            []imageloader.ImageKey
}

func (l *patchResolverLoader) GetImageBytes(context.Context, []imageloader.ImageKey) []imageloader.ImageBytes {
	return nil
}

func (l *patchResolverLoader) WarmInspection(context.Context, imageloader.InspectionKey, []string, string) (int, error) {
	return 0, nil
}

func (l *patchResolverLoader) ResolvePatchImageBytes(ctx context.Context, format string, keys []imageloader.ImageKey) ([]imageloader.ImageBytes, error) {
	if format != "known" {
		return nil, errors.New("unknown image source format")
	}
	if len(keys) == 0 {
		return nil, nil
	}
	l.lastKeys = append([]imageloader.ImageKey(nil), keys...)
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
			results[index].Err = errors.New("source object missing")
		}
	}
	return results, nil
}

func TestResolvePatchImagesBatchPreservesCorrelationPathsAndItemErrors(t *testing.T) {
	loader := &patchResolverLoader{}
	response, err := ResolvePatchImagesBatch(
		context.Background(),
		loader,
		&imageparserv1.ResolvePatchImagesRequest{
			SourceFormat: "known",
			Roles:        []string{"patch_template", "patch_defective"},
			Items: []*imageparserv1.ResolvePatchImageItem{
				{RequestId: "r1", SampleId: "s1", InspectionTime: "20260816_100000", WaferKey: 42, DefectId: "1", RolePaths: map[string]string{"patch_template": "sample-1/template.png"}},
				{RequestId: "r2", SampleId: "s2", InspectionTime: "20260816_100000", WaferKey: 42, DefectId: "2"},
			},
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(response.Results) != 4 {
		t.Fatalf("result count = %d, want 4", len(response.Results))
	}
	if first := response.Results[0]; first.RequestId != "r1" || first.SampleId != "s1" || first.Role != "patch_template" || string(first.ImageData) != "fixture" {
		t.Fatalf("first result = %#v", first)
	}
	if failed := response.Results[2]; failed.RequestId != "r2" || failed.Error != "source object missing" {
		t.Fatalf("item error result = %#v", failed)
	}
	if got := loader.lastKeys[0].RolePaths["patch_template"]; got != "sample-1/template.png" {
		t.Fatalf("role path = %q", got)
	}
}

func TestResolvePatchImagesBatchRejectsUnknownFormatAndInvalidRequest(t *testing.T) {
	for _, request := range []*imageparserv1.ResolvePatchImagesRequest{
		{SourceFormat: "unknown", Roles: []string{"patch_template"}, Items: validPatchItems()},
		{SourceFormat: "known", Roles: []string{"review"}, Items: validPatchItems()},
		{SourceFormat: "known", Roles: []string{"patch_template"}, Items: []*imageparserv1.ResolvePatchImageItem{{RequestId: "r1"}}},
	} {
		_, err := ResolvePatchImagesBatch(context.Background(), &patchResolverLoader{}, request)
		if status.Code(err) != codes.InvalidArgument {
			t.Fatalf("status = %v, want InvalidArgument", err)
		}
	}
}

func TestResolvePatchImagesBatchDoesNotImposeLegacyIdentityOnExplicitPaths(t *testing.T) {
	loader := &patchResolverLoader{}
	response, err := ResolvePatchImagesBatch(
		context.Background(),
		loader,
		&imageparserv1.ResolvePatchImagesRequest{
			SourceFormat: "known",
			Roles:        []string{"patch_defective"},
			Items: []*imageparserv1.ResolvePatchImageItem{{
				RequestId: "r1",
				SampleId:  "s1",
				RolePaths: map[string]string{"patch_defective": "sample/defective.tiff"},
			}},
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(response.Results) != 1 || string(response.Results[0].ImageData) != "fixture" {
		t.Fatalf("unexpected response: %#v", response)
	}
	if loader.lastKeys[0].InspectionTime != "" || loader.lastKeys[0].WaferKey != 0 || loader.lastKeys[0].DefectID != "" {
		t.Fatalf("generic request was assigned legacy identity: %#v", loader.lastKeys[0])
	}
}

func TestResolvePatchImagesBatchPropagatesCancellation(t *testing.T) {
	loader := &patchResolverLoader{
		waitForCancellation: true,
		entered:             make(chan struct{}),
		cancelObserved:      make(chan struct{}),
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() {
		_, err := ResolvePatchImagesBatch(ctx, loader, &imageparserv1.ResolvePatchImagesRequest{
			SourceFormat: "known",
			Roles:        []string{"patch_template"},
			Items:        validPatchItems(),
		})
		done <- err
	}()
	select {
	case <-loader.entered:
	case <-time.After(time.Second):
		t.Fatal("resolver did not start")
	}
	cancel()
	if err := <-done; !errors.Is(err, context.Canceled) {
		t.Fatalf("error = %v, want context.Canceled", err)
	}
	select {
	case <-loader.cancelObserved:
	case <-time.After(time.Second):
		t.Fatal("resolver did not observe canceled context")
	}
}

func TestDisplayServiceDoesNotExposeBatchResolveRPC(t *testing.T) {
	for _, stream := range imageparserv1.ImageParser_ServiceDesc.Streams {
		if stream.StreamName == "ResolvePatchImages" {
			t.Fatal("display service exposes job batch resolution RPC")
		}
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
