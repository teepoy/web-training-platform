package service

import (
	"context"
	"strconv"
	"strings"

	"github.com/h2non/bimg"
	imageparserv1 "ft-platform/protos/gen/go/imageparser/v1"
	"image-parser/internal/cache"
	"image-parser/internal/s3client"
	"image-parser/internal/sprite"
	"image-parser/internal/zipreader"
)

const imagesPerZip = 2000

type ImageParserService struct {
	imageparserv1.UnimplementedImageParserServer
	cache       *cache.ZipCache
	recordCache *cache.RecordCache
	warmer      *cache.Warmer
	bucket      string
}

func New(zipCache *cache.ZipCache, recordCache *cache.RecordCache, warmer *cache.Warmer, bucket string) *ImageParserService {
	if bucket == "" {
		bucket = "images"
	}
	return &ImageParserService{
		cache:       zipCache,
		recordCache: recordCache,
		warmer:      warmer,
		bucket:      bucket,
	}
}

func (s *ImageParserService) Health(ctx context.Context, req *imageparserv1.HealthRequest) (*imageparserv1.HealthResponse, error) {
	return &imageparserv1.HealthResponse{Status: "ok"}, nil
}

func (s *ImageParserService) GetImage(ctx context.Context, req *imageparserv1.GetImageRequest) (*imageparserv1.GetImageResponse, error) {
	fn := s.fetchFunc(req.Cache)

	imgData, _, err := s.fetchImage(fn, req.Bucket, req.Key, req.Prefix)
	if err != nil {
		return nil, err
	}

	return &imageparserv1.GetImageResponse{ImageData: imgData}, nil
}

func (s *ImageParserService) Sprite(ctx context.Context, req *imageparserv1.SpriteRequest) (*imageparserv1.SpriteResponse, error) {
	sz := int(req.Size)
	if sz == 0 {
		sz = 64
	}

	fn := s.fetchFunc(req.Cache)

	pngs := make([][]byte, 0, len(req.Prefixes))
	for _, prefix := range req.Prefixes {
		raw, _, err := s.fetchImage(fn, req.Bucket, req.Key, prefix)
		if err != nil {
			return nil, err
		}
		resized, err := bimg.Resize(raw, bimg.Options{Width: sz, Height: sz, Force: true})
		if err != nil {
			return nil, err
		}
		pngs = append(pngs, resized)
	}

	result, err := sprite.CreateSpriteFromResized(pngs, sz)
	if err != nil {
		return nil, err
	}

	return &imageparserv1.SpriteResponse{
		ImageData: result,
		Width:     int32(sz * len(req.Prefixes)),
		Height:    int32(sz),
	}, nil
}

func (s *ImageParserService) V2Sprite(ctx context.Context, req *imageparserv1.V2SpriteRequest) (*imageparserv1.V2SpriteResponse, error) {
	sz := int(req.Size)
	if sz == 0 {
		sz = 64
	}

	s3Keys, err := s.recordCache.GetOrLoad(req.Record)
	if err != nil {
		return nil, err
	}

	pngs := make([][]byte, 0, len(req.Items))

	for _, prefix := range req.Items {
		idx, err := extractIndex(prefix)
		if err != nil {
			return nil, err
		}

		zipIdx := idx / imagesPerZip
		if zipIdx >= len(s3Keys) {
			return nil, err
		}

		key := s3Keys[zipIdx]
		ck := cache.CacheKey(req.Bucket, key)

		zipData, err := s.cache.GetOrLoad(ck, func() ([]byte, error) {
			return zipreader.DownloadFullZip(s3client.Get(), req.Bucket, key)
		})
		if err != nil {
			return nil, err
		}

		imgData, _, err := zipreader.GetImageFromBytes(zipData, prefix)
		if err != nil {
			return nil, err
		}

		resized, err := bimg.Resize(imgData, bimg.Options{Width: sz, Height: sz, Force: true})
		if err != nil {
			return nil, err
		}
		pngs = append(pngs, resized)
	}

	if s.warmer != nil {
		s.warmer.WarmAsync(req.Record, req.Bucket, s3Keys)
	}

	result, err := sprite.CreateSpriteFromResized(pngs, sz)
	if err != nil {
		return nil, err
	}

	return &imageparserv1.V2SpriteResponse{
		ImageData: result,
		Width:     int32(sz * len(req.Items)),
		Height:    int32(sz),
	}, nil
}

type fetchFn func(bucket, key, prefix string) ([]byte, string, error)

func (s *ImageParserService) fetchFunc(useCache bool) fetchFn {
	if useCache {
		return func(bucket, key, prefix string) ([]byte, string, error) {
			return s.fetchFromCache(bucket, key, prefix)
		}
	}
	return func(bucket, key, prefix string) ([]byte, string, error) {
		return s.fetchLazy(bucket, key, prefix)
	}
}

func (s *ImageParserService) fetchImage(fn fetchFn, bucket, key, prefix string) ([]byte, string, error) {
	b := bucket
	if b == "" {
		b = s.bucket
	}
	k := key
	if k == "" {
		k = prefix
	}
	return fn(b, k, prefix)
}

func (s *ImageParserService) fetchFromCache(bucket, key, prefix string) ([]byte, string, error) {
	ck := cache.CacheKey(bucket, key)
	zipData, err := s.cache.GetOrLoad(ck, func() ([]byte, error) {
		return zipreader.DownloadFullZip(s3client.Get(), bucket, key)
	})
	if err != nil {
		return nil, "", err
	}
	return zipreader.GetImageFromBytes(zipData, prefix)
}

func (s *ImageParserService) fetchLazy(bucket, key, prefix string) ([]byte, string, error) {
	return zipreader.GetImageFromS3Zip(s3client.Get(), bucket, key, prefix, s.cache)
}

func extractIndex(prefix string) (int, error) {
	i := strings.LastIndex(prefix, "_")
	if i < 0 {
		return strconv.Atoi(prefix)
	}
	return strconv.Atoi(prefix[i+1:])
}
