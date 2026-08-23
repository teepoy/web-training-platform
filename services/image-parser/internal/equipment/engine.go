// Package equipment routes an Inspection to one code-registered equipment
// image entry. Runtime requests cannot choose a parser implementation.
package equipment

import (
	"context"
	"fmt"
	"strings"

	"image-parser/internal/artifactcache"
	"image-parser/internal/imagestream"
)

type Inspection struct {
	InspectionTime string
	WaferKey       int32
	EquipmentID    string
	LotID          string
	WaferID        string
	Device         string
	LayerID        string
}

type InspectionLookup interface {
	Resolve(ctx context.Context, inspectionTime string, waferKey int32) (Inspection, error)
}

type OpenParams struct {
	UseCase    imagestream.UseCase
	Inspection Inspection
	Roles      []string
	Cache      artifactcache.Cache
}

type Factory interface {
	Open(ctx context.Context, params OpenParams) (imagestream.Context, error)
}

type PatchImageProfile struct {
	ImageType string
	ImageID   *int
	BitDepth  int
	ZMin      uint16
	ZMax      uint16
}

type InspectionImageProfile struct {
	InspectionTime string
	WaferKey       int32
	Patches        []PatchImageProfile
}

type ProfileParams struct {
	Inspection Inspection
	Cache      artifactcache.Cache
}

// ProfileFactory is an optional equipment-entry capability. Implementations
// inspect the artifacts selected for one Inspection and return the patch
// instances and their native grayscale domains.
type ProfileFactory interface {
	Profile(ctx context.Context, params ProfileParams) (InspectionImageProfile, error)
}

type ImageProfiler interface {
	Profile(ctx context.Context, inspectionTime string, waferKey int32) (InspectionImageProfile, error)
}

type Registration struct {
	EquipmentIDs []string
	Factory      Factory
}

type Registry struct {
	factories map[string]Factory
}

func NewRegistry(registrations []Registration) (*Registry, error) {
	if len(registrations) == 0 {
		return nil, fmt.Errorf("at least one equipment image entry is required")
	}
	factories := make(map[string]Factory)
	for _, registration := range registrations {
		if registration.Factory == nil {
			return nil, fmt.Errorf("equipment image entry factory is required")
		}
		if len(registration.EquipmentIDs) == 0 {
			return nil, fmt.Errorf("equipment image entry IDs are required")
		}
		for _, raw := range registration.EquipmentIDs {
			equipmentID := strings.TrimSpace(raw)
			if equipmentID == "" {
				return nil, fmt.Errorf("equipment image entry ID cannot be empty")
			}
			if _, exists := factories[equipmentID]; exists {
				return nil, fmt.Errorf("equipment image entry %q is registered more than once", equipmentID)
			}
			factories[equipmentID] = registration.Factory
		}
	}
	return &Registry{factories: factories}, nil
}

func (r *Registry) resolve(equipmentID string) (Factory, error) {
	if r == nil {
		return nil, fmt.Errorf("equipment image entry registry is required")
	}
	factory, exists := r.factories[equipmentID]
	if !exists {
		return nil, &imagestream.ContextError{Code: "unknown_equipment", Message: fmt.Sprintf("no image entry is registered for equipment %q", equipmentID)}
	}
	return factory, nil
}

type LimitsByUseCase struct {
	Display    imagestream.Limits
	Prediction imagestream.Limits
	Training   imagestream.Limits
	Export     imagestream.Limits
}

func (l LimitsByUseCase) forUseCase(useCase imagestream.UseCase) imagestream.Limits {
	switch useCase {
	case imagestream.UseCaseDisplay:
		return l.Display
	case imagestream.UseCasePrediction:
		return l.Prediction
	case imagestream.UseCaseTraining:
		return l.Training
	case imagestream.UseCaseExport:
		return l.Export
	default:
		return imagestream.Limits{}
	}
}

type Engine struct {
	lookup   InspectionLookup
	registry *Registry
	caches   map[imagestream.UseCase]artifactcache.Cache
	limits   LimitsByUseCase
}

func NewEngine(lookup InspectionLookup, registry *Registry, caches map[imagestream.UseCase]artifactcache.Cache, limits LimitsByUseCase) (*Engine, error) {
	if lookup == nil {
		return nil, fmt.Errorf("inspection lookup is required")
	}
	if registry == nil {
		return nil, fmt.Errorf("equipment image entry registry is required")
	}
	installedCaches := make(map[imagestream.UseCase]artifactcache.Cache, len(caches))
	for useCase, cache := range caches {
		if cache == nil {
			return nil, fmt.Errorf("%s image artifact cache is required", useCase)
		}
		installedCaches[useCase] = cache
	}
	return &Engine{lookup: lookup, registry: registry, caches: installedCaches, limits: limits}, nil
}

func (e *Engine) Limits(useCase imagestream.UseCase) imagestream.Limits {
	return e.limits.forUseCase(useCase)
}

func (e *Engine) Open(ctx context.Context, useCase imagestream.UseCase, request imagestream.OpenRequest) (imagestream.Context, error) {
	cache := e.caches[useCase]
	if cache == nil {
		return nil, &imagestream.ContextError{Code: "cache_unavailable", Message: fmt.Sprintf("%s image artifact cache is not configured", useCase)}
	}
	inspection, err := e.lookup.Resolve(ctx, request.InspectionTime, request.WaferKey)
	if err != nil {
		return nil, &imagestream.ContextError{Code: "inspection_unavailable", Message: fmt.Sprintf("resolve inspection: %v", err)}
	}
	inspection.EquipmentID = strings.TrimSpace(inspection.EquipmentID)
	if inspection.EquipmentID == "" {
		return nil, &imagestream.ContextError{Code: "unknown_equipment", Message: "inspection has no equipment ID"}
	}
	factory, err := e.registry.resolve(inspection.EquipmentID)
	if err != nil {
		return nil, err
	}
	opened, err := factory.Open(ctx, OpenParams{UseCase: useCase, Inspection: inspection, Roles: append([]string(nil), request.Roles...), Cache: cache})
	if err != nil {
		return nil, err
	}
	if opened == nil {
		return nil, &imagestream.ContextError{Code: "entry_unavailable", Message: fmt.Sprintf("equipment %q entry returned no context", inspection.EquipmentID)}
	}
	if opened.EquipmentID() != inspection.EquipmentID {
		_ = opened.Close()
		return nil, &imagestream.ContextError{Code: "entry_unavailable", Message: fmt.Sprintf("equipment entry identity mismatch: got %q want %q", opened.EquipmentID(), inspection.EquipmentID)}
	}
	return opened, nil
}

func (e *Engine) Profile(ctx context.Context, inspectionTime string, waferKey int32) (InspectionImageProfile, error) {
	cache := e.caches[imagestream.UseCaseDisplay]
	if cache == nil {
		return InspectionImageProfile{}, &imagestream.ContextError{Code: "cache_unavailable", Message: "display image artifact cache is not configured"}
	}
	inspection, err := e.lookup.Resolve(ctx, inspectionTime, waferKey)
	if err != nil {
		return InspectionImageProfile{}, &imagestream.ContextError{Code: "inspection_unavailable", Message: fmt.Sprintf("resolve inspection: %v", err)}
	}
	inspection.EquipmentID = strings.TrimSpace(inspection.EquipmentID)
	if inspection.EquipmentID == "" {
		return InspectionImageProfile{}, &imagestream.ContextError{Code: "unknown_equipment", Message: "inspection has no equipment ID"}
	}
	factory, err := e.registry.resolve(inspection.EquipmentID)
	if err != nil {
		return InspectionImageProfile{}, err
	}
	profiler, ok := factory.(ProfileFactory)
	if !ok {
		return InspectionImageProfile{}, &imagestream.ContextError{Code: "profile_unavailable", Message: fmt.Sprintf("equipment %q does not expose an image profile", inspection.EquipmentID)}
	}
	profile, err := profiler.Profile(ctx, ProfileParams{Inspection: inspection, Cache: cache})
	if err != nil {
		return InspectionImageProfile{}, err
	}
	profile.InspectionTime = inspection.InspectionTime
	profile.WaferKey = inspection.WaferKey
	return profile, nil
}

var _ imagestream.Engine = (*Engine)(nil)
var _ ImageProfiler = (*Engine)(nil)
