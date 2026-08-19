package legacyrangezip

import (
	"archive/zip"
	"bytes"
	"context"
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"image-parser/internal/filesource"
	"image-parser/internal/sourceformat"
)

func TestLegacyDriverContainsAllRangeZipAndMemberNamingAssumptions(t *testing.T) {
	root := t.TempDir()
	archivePath := filepath.Join(root, "20260301_120000", "7", "000501-001000.zip")
	if err := os.MkdirAll(filepath.Dir(archivePath), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(archivePath, zipBytes(t, map[string]string{
		"000501_PatchDefective.png": "defective",
		"000501_PatchReference.png": "reference",
	}), 0o600); err != nil {
		t.Fatal(err)
	}
	source, err := filesource.Open(root, filesource.KindDirectory, filesource.OwnershipBorrowed)
	if err != nil {
		t.Fatal(err)
	}
	results := (Driver{}).Resolve(context.Background(), source, []sourceformat.Request{{
		RequestID: "request-1",
		SampleID:  "sample-1",
		Roles:     []string{"Defective", "Reference"},
		Fields: map[string]string{
			FieldInspectionTime: "2026-03-01T12:00:00Z",
			FieldWaferKey:       "7",
			FieldDefectID:       "501",
		},
	}})
	if len(results) != 2 {
		t.Fatalf("expected two role results, got %d", len(results))
	}
	if string(results[0].Data) != "defective" || string(results[1].Data) != "reference" {
		t.Fatalf("unexpected results: %#v", results)
	}
}

func TestLegacyDriverReturnsStablePerRoleErrors(t *testing.T) {
	source, err := filesource.Open(t.TempDir(), filesource.KindDirectory, filesource.OwnershipBorrowed)
	if err != nil {
		t.Fatal(err)
	}
	results := (Driver{}).Resolve(context.Background(), source, []sourceformat.Request{{
		RequestID: "request-1",
		Roles:     []string{"Defective"},
		Fields: map[string]string{
			FieldInspectionTime: "bad-time",
			FieldWaferKey:       "7",
			FieldDefectID:       "501",
		},
	}})
	if len(results) != 1 || results[0].Err == nil {
		t.Fatalf("expected one item error, got %#v", results)
	}
}

func zipBytes(t *testing.T, files map[string]string) []byte {
	t.Helper()
	var buffer bytes.Buffer
	writer := zip.NewWriter(&buffer)
	for name, contents := range files {
		entry, err := writer.Create(name)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := entry.Write([]byte(contents)); err != nil {
			t.Fatal(err)
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	return buffer.Bytes()
}

func BenchmarkDriverResolve500Samples(b *testing.B) {
	root := b.TempDir()
	archivePath := filepath.Join(root, "20260301_120000", "7", "000001-000500.zip")
	if err := os.MkdirAll(filepath.Dir(archivePath), 0o700); err != nil {
		b.Fatal(err)
	}
	files := make(map[string]string, 1_000)
	requests := make([]sourceformat.Request, 500)
	for index := range 500 {
		defectID := index + 1
		files[fmt.Sprintf("%06d_PatchDefective.png", defectID)] = "defective"
		files[fmt.Sprintf("%06d_PatchReference.png", defectID)] = "reference"
		requests[index] = sourceformat.Request{
			RequestID: fmt.Sprintf("request-%d", defectID),
			Roles:     []string{"Defective", "Reference"},
			Fields: map[string]string{
				FieldInspectionTime: "2026-03-01T12:00:00Z",
				FieldWaferKey:       "7",
				FieldDefectID:       fmt.Sprintf("%d", defectID),
			},
		}
	}
	if err := os.WriteFile(archivePath, benchmarkZipBytes(b, files), 0o600); err != nil {
		b.Fatal(err)
	}
	source, err := filesource.Open(root, filesource.KindDirectory, filesource.OwnershipBorrowed)
	if err != nil {
		b.Fatal(err)
	}
	driver := Driver{}
	b.ReportAllocs()
	b.ResetTimer()
	for range b.N {
		results := driver.Resolve(context.Background(), source, requests)
		if len(results) != 1_000 {
			b.Fatalf("unexpected result count %d", len(results))
		}
	}
	b.StopTimer()
	b.ReportMetric(float64(500*b.N)/b.Elapsed().Seconds(), "samples/s")
}

func benchmarkZipBytes(b *testing.B, files map[string]string) []byte {
	b.Helper()
	var buffer bytes.Buffer
	writer := zip.NewWriter(&buffer)
	for name, contents := range files {
		entry, err := writer.Create(name)
		if err != nil {
			b.Fatal(err)
		}
		if _, err := entry.Write([]byte(contents)); err != nil {
			b.Fatal(err)
		}
	}
	if err := writer.Close(); err != nil {
		b.Fatal(err)
	}
	return buffer.Bytes()
}
