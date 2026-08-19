package legacyrangezip

import (
	"context"
	"fmt"
	"strconv"

	scv1 "image-parser/gen/go/sc/v1"
	"image-parser/internal/filesource"
	"image-parser/internal/sourceformat"
)

type UpstreamCatalog interface {
	GetInspection(ctx context.Context, inspectionTime string, waferKey int32) (*scv1.GetInspectionResponse, error)
	GetInspectionPatchZips(ctx context.Context, inspectionTime, lotID, waferID, device, layerID string) (*scv1.GetInspectionPatchZipsResponse, error)
}

type ObjectLoader interface {
	LoadPatchObject(ctx context.Context, bucket, key string) ([]byte, error)
}

type UpstreamStager struct {
	upstream UpstreamCatalog
	objects  ObjectLoader
}

func NewUpstreamStager(upstream UpstreamCatalog, objects ObjectLoader) *UpstreamStager {
	return &UpstreamStager{upstream: upstream, objects: objects}
}

func (s *UpstreamStager) Stage(ctx context.Context, source *filesource.Source, requests []sourceformat.Request) error {
	if s.upstream == nil || s.objects == nil {
		return fmt.Errorf("upstream stager dependencies are required")
	}
	type inspectionKey struct {
		time  string
		wafer int
	}
	type requiredArchive struct {
		path  string
		index int
	}
	groups := map[inspectionKey]map[string]requiredArchive{}
	for _, request := range requests {
		path, defectID, err := archiveLocation(request.Fields)
		if err != nil {
			return fmt.Errorf("plan staged source for request %q: %w", request.RequestID, err)
		}
		wafer, _ := strconv.Atoi(request.Fields[FieldWaferKey])
		key := inspectionKey{time: request.Fields[FieldInspectionTime], wafer: wafer}
		if groups[key] == nil {
			groups[key] = map[string]requiredArchive{}
		}
		groups[key][path] = requiredArchive{path: path, index: (defectID - 1) / defectsPerArchive}
	}
	for key, archives := range groups {
		if err := ctx.Err(); err != nil {
			return err
		}
		metadata, err := s.upstream.GetInspection(ctx, key.time, int32(key.wafer))
		if err != nil {
			return fmt.Errorf("resolve inspection metadata: %w", err)
		}
		refs, err := s.upstream.GetInspectionPatchZips(
			ctx,
			key.time,
			metadata.LotId,
			metadata.WaferId,
			metadata.Device,
			metadata.LayerId,
		)
		if err != nil {
			return fmt.Errorf("resolve staged source objects: %w", err)
		}
		for _, archive := range archives {
			exists, err := source.HasFile(archive.path)
			if err != nil {
				return fmt.Errorf("inspect staged source object: %w", err)
			}
			if exists {
				continue
			}
			if archive.index < 0 || archive.index >= len(refs.Zips) {
				return fmt.Errorf("upstream has no source object for archive index %d", archive.index)
			}
			ref := refs.Zips[archive.index]
			data, err := s.objects.LoadPatchObject(ctx, ref.S3Bucket, ref.S3Key)
			if err != nil {
				return fmt.Errorf("load staged source object: %w", err)
			}
			if err := source.WriteFile(archive.path, data); err != nil {
				return fmt.Errorf("publish staged source object: %w", err)
			}
		}
	}
	return nil
}
