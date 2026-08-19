package legacyrangezip

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	scv1 "image-parser/gen/go/sc/v1"
	"image-parser/internal/filesource"
	"image-parser/internal/sourceformat"
)

type fakeUpstream struct{}

func (fakeUpstream) GetInspection(context.Context, string, int32) (*scv1.GetInspectionResponse, error) {
	return &scv1.GetInspectionResponse{LotId: "lot", WaferId: "wafer", Device: "device", LayerId: "layer"}, nil
}

func (fakeUpstream) GetInspectionPatchZips(context.Context, string, string, string, string, string) (*scv1.GetInspectionPatchZipsResponse, error) {
	return &scv1.GetInspectionPatchZipsResponse{Zips: []*scv1.ZipRef{
		{S3Bucket: "bucket", S3Key: "first.zip"},
		{S3Bucket: "bucket", S3Key: "second.zip"},
	}}, nil
}

type fakeObjectLoader struct {
	data []byte
}

func (f fakeObjectLoader) LoadPatchObject(_ context.Context, bucket, key string) ([]byte, error) {
	if bucket != "bucket" || key != "second.zip" {
		return nil, &unexpectedObjectError{bucket: bucket, key: key}
	}
	return f.data, nil
}

type unexpectedObjectError struct {
	bucket string
	key    string
}

func (e *unexpectedObjectError) Error() string { return "unexpected object " + e.bucket + "/" + e.key }

func TestUpstreamStagerPublishesDriverLayoutIntoOwnedSource(t *testing.T) {
	parent := t.TempDir()
	root := filepath.Join(parent, "job")
	if err := os.Mkdir(root, 0o700); err != nil {
		t.Fatal(err)
	}
	source, err := filesource.Open(root, filesource.KindDirectory, filesource.OwnershipJobOwned)
	if err != nil {
		t.Fatal(err)
	}
	archive := zipBytes(t, map[string]string{"000501_PatchDefective.png": "defective"})
	stager := NewUpstreamStager(fakeUpstream{}, fakeObjectLoader{data: archive})
	request := sourceformat.Request{
		RequestID: "request-1",
		Roles:     []string{"Defective"},
		Fields: map[string]string{
			FieldInspectionTime: "2026-03-01T12:00:00Z",
			FieldWaferKey:       "7",
			FieldDefectID:       "501",
		},
	}
	if err := stager.Stage(context.Background(), source, []sourceformat.Request{request}); err != nil {
		t.Fatal(err)
	}
	results := (Driver{}).Resolve(context.Background(), source, []sourceformat.Request{request})
	if len(results) != 1 || results[0].Err != nil || string(results[0].Data) != "defective" {
		t.Fatalf("unexpected results: %#v", results)
	}
}
