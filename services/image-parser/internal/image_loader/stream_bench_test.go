package image_loader

import (
	"archive/zip"
	"bytes"
	"context"
	"fmt"
	"testing"
	"time"

	"image-parser/internal/image_loader/cache"
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
	zips := make(map[int]PatchArchive, zipCount)
	for i := range zipCount {
		ref := cacheZipRef{Bucket: "bench", Key: fmt.Sprintf("patch-%04d.zip", i)}
		zips[i] = PatchArchive{CacheKey: cache.CacheKey(ref.Bucket, ref.Key), Bucket: ref.Bucket, Key: ref.Key}
		zipBytes := makeBenchmarkZip(b, i*defectsPerZip+1, defectsPerZip)
		if err := zipCache.Set(cache.CacheKey(ref.Bucket, ref.Key), zipBytes); err != nil {
			b.Fatal(err)
		}
	}

	lookups := make([]patchImageLookup, 0, benchmarkDefects*benchmarkImagesPerDefect)
	idx := 0
	for offset := range benchmarkDefects {
		defectID := offset + 1
		for _, imageType := range []string{"Reference", "Defective"} {
			lookups = append(lookups, patchImageLookup{
				Index:     idx,
				DefectID:  fmt.Sprintf("%d", defectID),
				ImageType: imageType,
			})
			idx++
		}
	}

	resolver := &Resolver{zipCache: zipCache}
	b.ReportAllocs()
	b.SetBytes(int64(len(lookups)))
	b.ResetTimer()
	for range b.N {
		results := resolver.getPatchImageBytesBatchFromZips(context.Background(), benchmarkPatchProvider{}, zips, lookups)
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

type benchmarkPatchProvider struct{}

func (benchmarkPatchProvider) ResolveArchives(context.Context, InspectionKey, []int) (map[int]PatchArchive, error) {
	panic("benchmark archives are pre-resolved")
}

func (benchmarkPatchProvider) LoadArchive(context.Context, PatchArchive) ([]byte, error) {
	panic("benchmark archives are pre-cached")
}

func makeBenchmarkZip(b *testing.B, startDefectID int, defects int) []byte {
	b.Helper()
	var buf bytes.Buffer
	zw := zip.NewWriter(&buf)
	for offset := range defects {
		defectID := startDefectID + offset
		for _, suffix := range []string{"Reference", "Defective"} {
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
