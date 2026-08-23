package handler

import (
	"archive/zip"
	"bytes"
	"context"
	"image"
	"image/color"
	"image/jpeg"
	"io"
	"os"
	"testing"

	scv1 "image-parser/gen/go/sc/v1"
	"image-parser/internal/display"
)

type galleryMetadataStub struct{ waferID string }

func (s galleryMetadataStub) GetInspection(_ context.Context, inspectionTime string, waferKey int32) (*scv1.GetInspectionResponse, error) {
	return &scv1.GetInspectionResponse{InspectionTime: inspectionTime, WaferKey: waferKey, WaferId: s.waferID}, nil
}

type galleryImageReaderStub struct {
	patch  []byte
	review []byte
}

func (s galleryImageReaderStub) GetImageBytes(_ context.Context, keys []display.ImageKey) []display.ImageBytes {
	results := make([]display.ImageBytes, len(keys))
	for index, key := range keys {
		data, contentType := s.patch, "image/png"
		if key.Kind == display.ImageKindReview {
			data, contentType = s.review, "image/jpeg"
		}
		results[index] = display.ImageBytes{Key: key, Data: data, ContentType: contentType}
	}
	return results
}

func TestGalleryDownloadPreservesOriginalBytesAndNames(t *testing.T) {
	patch := encodeTestPNG(t, image.NewGray(image.Rect(0, 0, 3, 2)))
	review := encodeTestJPEG(t, image.NewGray(image.Rect(0, 0, 4, 3)))
	service, err := NewGalleryDownloadService(
		galleryImageReaderStub{patch: patch, review: review},
		galleryMetadataStub{waferID: "W01"},
		t.TempDir(),
	)
	if err != nil {
		t.Fatal(err)
	}

	result, err := service.Create(context.Background(), GalleryDownloadRequest{Items: []GalleryDownloadItem{{
		InspectionTime: "2026-08-21T00:00:00Z", WaferKey: 1, DefectID: "42",
		PatchImageTypes: []string{"Defective", "Reference", "Difference"}, ReviewImageIDs: []int{7},
	}}})
	if err != nil {
		t.Fatal(err)
	}
	defer os.Remove(result.Path)
	entries := readGalleryZIP(t, result.Path)
	want := map[string][]byte{
		"2026-08-21T00:00:00Z-W01/42-defective.png":  patch,
		"2026-08-21T00:00:00Z-W01/42-reference.png":  patch,
		"2026-08-21T00:00:00Z-W01/42-difference.png": patch,
		"2026-08-21T00:00:00Z-W01/42-review-7.jpg":   review,
	}
	if len(entries) != len(want) {
		t.Fatalf("ZIP entries = %v", entries)
	}
	for name, data := range want {
		if !bytes.Equal(entries[name], data) {
			t.Fatalf("entry %s did not preserve original bytes", name)
		}
	}
}

func TestGalleryDownloadAppliesGroupedMappingWithoutResizing(t *testing.T) {
	gray := image.NewGray16(image.Rect(0, 0, 3, 2))
	gray.SetGray16(1, 1, color.Gray16{Y: 32768})
	patch := encodeTestPNG(t, gray)
	service, err := NewGalleryDownloadService(
		galleryImageReaderStub{patch: patch, review: encodeTestJPEG(t, image.NewGray(image.Rect(0, 0, 1, 1)))},
		galleryMetadataStub{waferID: "W01"},
		t.TempDir(),
	)
	if err != nil {
		t.Fatal(err)
	}
	result, err := service.Create(context.Background(), GalleryDownloadRequest{
		Items:             []GalleryDownloadItem{{InspectionTime: "2026-08-21T00:00:00Z", WaferKey: 1, DefectID: "42", PatchImageTypes: []string{"Defective", "Difference"}}},
		ApplyColorMapping: true,
		GrayMappings: PatchGrayMappings{
			DefectiveReference: &GrayMapping{LUT: GrayLUTViridis, ZMin: 0, ZMax: 1},
			Difference:         &GrayMapping{LUT: GrayLUTInferno, ZMin: 0, ZMax: 1},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	defer os.Remove(result.Path)
	entries := readGalleryZIP(t, result.Path)
	defective := decodeImage(t, entries["2026-08-21T00:00:00Z-W01/42-defective.png"])
	difference := decodeImage(t, entries["2026-08-21T00:00:00Z-W01/42-difference.png"])
	if defective.Bounds().Dx() != 3 || defective.Bounds().Dy() != 2 {
		t.Fatalf("mapped dimensions = %v, want 3x2", defective.Bounds())
	}
	if defective.At(1, 1) == difference.At(1, 1) {
		t.Fatal("defective/reference and difference mappings produced the same mapped color")
	}
}

func readGalleryZIP(t *testing.T, path string) map[string][]byte {
	t.Helper()
	reader, err := zip.OpenReader(path)
	if err != nil {
		t.Fatal(err)
	}
	defer reader.Close()
	entries := make(map[string][]byte, len(reader.File))
	for _, file := range reader.File {
		opened, err := file.Open()
		if err != nil {
			t.Fatal(err)
		}
		entries[file.Name], err = io.ReadAll(opened)
		_ = opened.Close()
		if err != nil {
			t.Fatal(err)
		}
	}
	return entries
}

func encodeTestJPEG(t *testing.T, source image.Image) []byte {
	t.Helper()
	var output bytes.Buffer
	if err := jpeg.Encode(&output, source, &jpeg.Options{Quality: 90}); err != nil {
		t.Fatal(err)
	}
	return output.Bytes()
}

func decodeImage(t *testing.T, data []byte) image.Image {
	t.Helper()
	decoded, _, err := image.Decode(bytes.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	return decoded
}
