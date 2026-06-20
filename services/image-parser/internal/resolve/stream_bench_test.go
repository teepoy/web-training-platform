package resolve

import (
	"archive/zip"
	"bytes"
	"context"
	"fmt"
	"testing"
	"time"

	"image-parser/internal/cache"
)

const benchmarkDefects = 300_000
const benchmarkImagesPerDefect = 2

func BenchmarkStreamCore300KDefects(b *testing.B) {
	zipCache, err := cache.New(1024, 10*time.Minute)
	if err != nil {
		b.Fatal(err)
	}
	defer zipCache.Close()

	zipCount := benchmarkDefects / defectsPerZip
	zips := make([]CacheZipRef, 0, zipCount)
	for i := range zipCount {
		ref := CacheZipRef{Bucket: "bench", Key: fmt.Sprintf("patch-%04d.zip", i)}
		zips = append(zips, ref)
		zipBytes := makeBenchmarkZip(b, i*defectsPerZip, defectsPerZip)
		if err := zipCache.Set(cache.CacheKey(ref.Bucket, ref.Key), zipBytes); err != nil {
			b.Fatal(err)
		}
	}

	lookups := make([]PatchImageLookup, 0, benchmarkDefects*benchmarkImagesPerDefect)
	idx := 0
	for defectID := range benchmarkDefects {
		for _, imageType := range []string{"template", "defective"} {
			lookups = append(lookups, PatchImageLookup{
				Index:     idx,
				DefectID:  fmt.Sprintf("%d", defectID),
				ImageType: imageType,
			})
			idx++
		}
	}

	resolver := &Resolver{ZipCache: zipCache}
	b.ReportAllocs()
	b.SetBytes(int64(len(lookups)))
	b.ResetTimer()
	for range b.N {
		results := resolver.GetPatchImageBytesBatchFromZips(context.Background(), zips, lookups)
		if len(results) != len(lookups) {
			b.Fatalf("result count mismatch: got %d want %d", len(results), len(lookups))
		}
		for i, result := range results {
			if result.Err != nil {
				b.Fatalf("result %d failed: %v", i, result.Err)
			}
		}
	}
}

func makeBenchmarkZip(b *testing.B, startDefectID int, defects int) []byte {
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
