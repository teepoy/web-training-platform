package main

import (
	"bytes"
	"context"
	"encoding/binary"
	"strconv"
	"testing"

	"google.golang.org/protobuf/proto"
	imageparserv1 "image-parser/gen/go/imageparser/v1"
	imageloader "image-parser/internal/image_loader"
)

type orderedBatchLoader struct{}

func (orderedBatchLoader) GetImageBytes(context.Context, []imageloader.ImageKey) []imageloader.ImageBytes {
	return nil
}

func (orderedBatchLoader) WarmInspection(context.Context, imageloader.InspectionKey, []string, string) (int, error) {
	return 0, nil
}

func (orderedBatchLoader) ResolvePatchImageBytes(_ context.Context, profile string, keys []imageloader.ImageKey) ([]imageloader.ImageBytes, error) {
	results := make([]imageloader.ImageBytes, len(keys))
	for index, key := range keys {
		results[index] = imageloader.ImageBytes{
			Key:         key,
			Data:        []byte(profile + ":" + key.DefectID + ":" + key.ImageType),
			ContentType: "image/png",
		}
	}
	return results, nil
}

func TestRunPreservesRequestAndRoleOrderAcrossOneBatchFrame(t *testing.T) {
	request := &imageparserv1.ResolvePatchImagesRequest{
		SourceProfile: "local-profile",
		Roles:         []string{"patch_template", "patch_defective"},
		Items: []*imageparserv1.ResolvePatchImageItem{
			{RequestId: "first", SampleId: "sample-1", InspectionTime: "20260816_100000", WaferKey: 42, DefectId: "1"},
			{RequestId: "second", SampleId: "sample-2", InspectionTime: "20260816_100000", WaferKey: 42, DefectId: "2"},
		},
	}
	payload, err := proto.Marshal(request)
	if err != nil {
		t.Fatal(err)
	}
	var input bytes.Buffer
	if err := binary.Write(&input, binary.BigEndian, uint32(len(payload))); err != nil {
		t.Fatal(err)
	}
	if _, err := input.Write(payload); err != nil {
		t.Fatal(err)
	}
	var output bytes.Buffer

	if err := run(context.Background(), &input, &output, orderedBatchLoader{}); err != nil {
		t.Fatal(err)
	}

	var responseSize uint32
	if err := binary.Read(&output, binary.BigEndian, &responseSize); err != nil {
		t.Fatal(err)
	}
	responsePayload := make([]byte, responseSize)
	if _, err := output.Read(responsePayload); err != nil {
		t.Fatal(err)
	}
	response := &imageparserv1.ResolvePatchImagesBatchResponse{}
	if err := proto.Unmarshal(responsePayload, response); err != nil {
		t.Fatal(err)
	}
	got := make([]string, 0, len(response.Results))
	for _, result := range response.Results {
		got = append(got, result.RequestId+":"+result.Role+":"+string(result.ImageData))
	}
	want := []string{
		"first:patch_template:local-profile:1:patch_template",
		"first:patch_defective:local-profile:1:patch_defective",
		"second:patch_template:local-profile:2:patch_template",
		"second:patch_defective:local-profile:2:patch_defective",
	}
	if len(got) != len(want) {
		t.Fatalf("result count = %d, want %d: %#v", len(got), len(want), got)
	}
	for index := range want {
		if got[index] != want[index] {
			t.Fatalf("result %d = %q, want %q", index, got[index], want[index])
		}
	}
}

func BenchmarkRunBatchFrame512(b *testing.B) {
	items := make([]*imageparserv1.ResolvePatchImageItem, 512)
	for index := range items {
		items[index] = &imageparserv1.ResolvePatchImageItem{
			RequestId:      "request-" + strconv.Itoa(index),
			SampleId:       "sample-" + strconv.Itoa(index),
			InspectionTime: "20260816_100000",
			WaferKey:       42,
			DefectId:       "1",
		}
	}
	request := &imageparserv1.ResolvePatchImagesRequest{
		SourceProfile: "local-profile",
		Roles:         []string{"patch_template", "patch_defective"},
		Items:         items,
	}
	payload, err := proto.Marshal(request)
	if err != nil {
		b.Fatal(err)
	}
	var input bytes.Buffer
	if err := binary.Write(&input, binary.BigEndian, uint32(len(payload))); err != nil {
		b.Fatal(err)
	}
	if _, err := input.Write(payload); err != nil {
		b.Fatal(err)
	}
	frame := append([]byte(nil), input.Bytes()...)
	b.ReportAllocs()
	b.ResetTimer()
	for range b.N {
		var output bytes.Buffer
		if err := run(context.Background(), bytes.NewReader(frame), &output, orderedBatchLoader{}); err != nil {
			b.Fatal(err)
		}
	}
	b.StopTimer()
	b.ReportMetric(float64(512*b.N)/b.Elapsed().Seconds(), "samples/s")
}
