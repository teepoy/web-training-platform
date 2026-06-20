package resolve

import (
	"context"

	scv1 "image-parser/gen/go/sc/v1"
	"image-parser/internal/s3client"
	"image-parser/internal/zipreader"
)

type UpstreamSource interface {
	GetInspection(ctx context.Context, inspectionTime string, waferKey int32) (*scv1.GetInspectionResponse, error)
	GetInspectionPatchZips(ctx context.Context, inspectionTime, lotID, waferID, device, layerID string) (*scv1.GetInspectionPatchZipsResponse, error)
	GetReviewImageFileSpec(ctx context.Context, inspectionTime string, waferKey, defectID, imageID int32) (*scv1.GetReviewImageFileSpecResponse, error)
	ListReviewImages(ctx context.Context, inspectionTime string, waferKey, defectID int32) (*scv1.ListReviewImagesResponse, error)
}

type ObjectReader interface {
	DownloadPatchZip(bucket, key string) ([]byte, error)
	DownloadReviewObject(bucket, key string) ([]byte, error)
}

type ImageBytesSource interface {
	ResolveMetadataForWarm(ctx context.Context, inspectionTime string, waferKey int) (lotID, waferID, device, layerID string, err error)
	ResolvePatchZipsForWarm(ctx context.Context, inspectionTime, lotID, waferID, device, layerID string) ([]CacheZipRef, error)
	GetMetaAndZips(ctx context.Context, inspectionTime string, waferKey int) (lotID, waferID, device, layerID string, zips []CacheZipRef, err error)
	GetPatchImageBytes(ctx context.Context, inspectionTime string, waferKey int, defectIDStr string, imageType string) ([]byte, error)
	GetPatchImageBytesFromZips(ctx context.Context, zips []CacheZipRef, defectIDStr string, imageType string) ([]byte, error)
	GetPatchImageBytesBatchFromZips(ctx context.Context, zips []CacheZipRef, lookups []PatchImageLookup) []PatchImageLookupResult
	GetReviewImageBytes(ctx context.Context, inspectionTime string, waferKey int, defectIDStr string, reviewImageID int) ([]byte, error)
	GetReviewImages(ctx context.Context, inspectionTime string, waferKey int, defectIDStr string) ([]string, error)
	GetReviewObjectBytes(ctx context.Context, bucket, key string) ([]byte, error)
	WarmAsync(record, bucket string, keys []string)
}

type _MockObjectReader struct{}

func (r _MockObjectReader) DownloadPatchZip(bucket, key string) ([]byte, error) {
	return zipreader.DownloadFullZip(s3client.GetZips(), bucket, key)
}

func (r _MockObjectReader) DownloadReviewObject(bucket, key string) ([]byte, error) {
	return zipreader.DownloadFullZip(s3client.GetReview(), bucket, key)
}
