package resolve

import (
	"bytes"
	"context"
	"hash/fnv"
	"image"
	"image/color"
	"image/png"
	"math/rand/v2"
	"strconv"
)

const fallbackImageSize = 64

func NewMockImageSource() ImageBytesSource {
	return _MockImageSource{}
}

func NewFallbackImageSource(inner ImageBytesSource) ImageBytesSource {
	return _FallbackImageSource{inner: inner, mock: _MockImageSource{}}
}

type _MockImageSource struct{}

func (_MockImageSource) ResolveMetadataForWarm(ctx context.Context, inspectionTime string, waferKey int) (string, string, string, string, error) {
	if err := ctx.Err(); err != nil {
		return "", "", "", "", err
	}
	return "mock-lot", "mock-wafer", "mock-device", "mock-layer", nil
}

func (_MockImageSource) ResolvePatchZipsForWarm(ctx context.Context, inspectionTime, lotID, waferID, device, layerID string) ([]CacheZipRef, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return []CacheZipRef{{Bucket: "mock", Key: "patch.zip"}}, nil
}

func (_MockImageSource) GetMetaAndZips(ctx context.Context, inspectionTime string, waferKey int) (string, string, string, string, []CacheZipRef, error) {
	if err := ctx.Err(); err != nil {
		return "", "", "", "", nil, err
	}
	return "mock-lot", "mock-wafer", "mock-device", "mock-layer", []CacheZipRef{{Bucket: "mock", Key: "patch.zip"}}, nil
}

func (_MockImageSource) GetPatchImageBytes(ctx context.Context, inspectionTime string, waferKey int, defectIDStr string, imageType string) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return fallbackGrayPNG("patch:" + inspectionTime + ":" + strconv.Itoa(waferKey) + ":" + defectIDStr + ":" + imageType), nil
}

func (_MockImageSource) GetPatchImageBytesFromZips(ctx context.Context, zips []CacheZipRef, defectIDStr string, imageType string) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return fallbackGrayPNG("patch-zips:" + defectIDStr + ":" + imageType), nil
}

func (m _MockImageSource) GetPatchImageBytesBatchFromZips(ctx context.Context, zips []CacheZipRef, lookups []PatchImageLookup) []PatchImageLookupResult {
	results := make([]PatchImageLookupResult, len(lookups))
	for i, lookup := range lookups {
		results[i] = PatchImageLookupResult{
			Index:     lookup.Index,
			DefectID:  lookup.DefectID,
			ImageType: lookup.ImageType,
		}
		data, err := m.GetPatchImageBytesFromZips(ctx, zips, lookup.DefectID, lookup.ImageType)
		results[i].Data = data
		results[i].Err = err
	}
	return results
}

func (_MockImageSource) GetReviewImageBytes(ctx context.Context, inspectionTime string, waferKey int, defectIDStr string, reviewImageID int) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return fallbackGrayPNG("review:" + inspectionTime + ":" + strconv.Itoa(waferKey) + ":" + defectIDStr + ":" + strconv.Itoa(reviewImageID)), nil
}

func (_MockImageSource) GetReviewImages(ctx context.Context, inspectionTime string, waferKey int, defectIDStr string) ([]string, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return []string{
		"s3://mock/review/" + defectIDStr + "/1.png",
		"s3://mock/review/" + defectIDStr + "/2.png",
		"s3://mock/review/" + defectIDStr + "/3.png",
	}, nil
}

func (_MockImageSource) GetReviewObjectBytes(ctx context.Context, bucket, key string) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return fallbackGrayPNG("review-object:" + bucket + ":" + key), nil
}

func (_MockImageSource) WarmAsync(record, bucket string, keys []string) {}

type _FallbackImageSource struct {
	inner ImageBytesSource
	mock  _MockImageSource
}

func (s _FallbackImageSource) ResolveMetadataForWarm(ctx context.Context, inspectionTime string, waferKey int) (string, string, string, string, error) {
	lotID, waferID, device, layerID, err := s.inner.ResolveMetadataForWarm(ctx, inspectionTime, waferKey)
	if err == nil {
		return lotID, waferID, device, layerID, nil
	}
	return s.mock.ResolveMetadataForWarm(ctx, inspectionTime, waferKey)
}

func (s _FallbackImageSource) ResolvePatchZipsForWarm(ctx context.Context, inspectionTime, lotID, waferID, device, layerID string) ([]CacheZipRef, error) {
	zips, err := s.inner.ResolvePatchZipsForWarm(ctx, inspectionTime, lotID, waferID, device, layerID)
	if err == nil && len(zips) > 0 {
		return zips, nil
	}
	return s.mock.ResolvePatchZipsForWarm(ctx, inspectionTime, lotID, waferID, device, layerID)
}

func (s _FallbackImageSource) GetMetaAndZips(ctx context.Context, inspectionTime string, waferKey int) (string, string, string, string, []CacheZipRef, error) {
	lotID, waferID, device, layerID, zips, err := s.inner.GetMetaAndZips(ctx, inspectionTime, waferKey)
	if err == nil && len(zips) > 0 {
		return lotID, waferID, device, layerID, zips, nil
	}
	return s.mock.GetMetaAndZips(ctx, inspectionTime, waferKey)
}

func (s _FallbackImageSource) GetPatchImageBytes(ctx context.Context, inspectionTime string, waferKey int, defectIDStr string, imageType string) ([]byte, error) {
	data, err := s.inner.GetPatchImageBytes(ctx, inspectionTime, waferKey, defectIDStr, imageType)
	if err == nil {
		return data, nil
	}
	return s.mock.GetPatchImageBytes(ctx, inspectionTime, waferKey, defectIDStr, imageType)
}

func (s _FallbackImageSource) GetPatchImageBytesFromZips(ctx context.Context, zips []CacheZipRef, defectIDStr string, imageType string) ([]byte, error) {
	data, err := s.inner.GetPatchImageBytesFromZips(ctx, zips, defectIDStr, imageType)
	if err == nil {
		return data, nil
	}
	return s.mock.GetPatchImageBytesFromZips(ctx, zips, defectIDStr, imageType)
}

func (s _FallbackImageSource) GetPatchImageBytesBatchFromZips(ctx context.Context, zips []CacheZipRef, lookups []PatchImageLookup) []PatchImageLookupResult {
	results := s.inner.GetPatchImageBytesBatchFromZips(ctx, zips, lookups)
	for i := range results {
		if results[i].Err != nil {
			data, err := s.mock.GetPatchImageBytesFromZips(ctx, zips, results[i].DefectID, results[i].ImageType)
			results[i].Data = data
			results[i].Err = err
		}
	}
	return results
}

func (s _FallbackImageSource) GetReviewImageBytes(ctx context.Context, inspectionTime string, waferKey int, defectIDStr string, reviewImageID int) ([]byte, error) {
	data, err := s.inner.GetReviewImageBytes(ctx, inspectionTime, waferKey, defectIDStr, reviewImageID)
	if err == nil {
		return data, nil
	}
	return s.mock.GetReviewImageBytes(ctx, inspectionTime, waferKey, defectIDStr, reviewImageID)
}

func (s _FallbackImageSource) GetReviewImages(ctx context.Context, inspectionTime string, waferKey int, defectIDStr string) ([]string, error) {
	refs, err := s.inner.GetReviewImages(ctx, inspectionTime, waferKey, defectIDStr)
	if err == nil {
		return refs, nil
	}
	return s.mock.GetReviewImages(ctx, inspectionTime, waferKey, defectIDStr)
}

func (s _FallbackImageSource) GetReviewObjectBytes(ctx context.Context, bucket, key string) ([]byte, error) {
	data, err := s.inner.GetReviewObjectBytes(ctx, bucket, key)
	if err == nil {
		return data, nil
	}
	return s.mock.GetReviewObjectBytes(ctx, bucket, key)
}

func (s _FallbackImageSource) WarmAsync(record, bucket string, keys []string) {
	s.inner.WarmAsync(record, bucket, keys)
}

func fallbackGrayPNG(seed string) []byte {
	h := fnv.New64a()
	_, _ = h.Write([]byte(seed))
	rng := rand.New(rand.NewPCG(h.Sum64(), h.Sum64()^0x9e3779b97f4a7c15))

	img := image.NewGray(image.Rect(0, 0, fallbackImageSize, fallbackImageSize))
	base := uint8(96 + rng.IntN(80))
	for y := 0; y < fallbackImageSize; y++ {
		for x := 0; x < fallbackImageSize; x++ {
			jitter := uint8(rng.IntN(48))
			img.SetGray(x, y, color.Gray{Y: base + jitter})
		}
	}

	var buf bytes.Buffer
	if err := png.Encode(&buf, img); err != nil {
		return nil
	}
	return buf.Bytes()
}
