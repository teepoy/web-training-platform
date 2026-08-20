package equipment_test

import (
	"context"
	"errors"
	"testing"

	"image-parser/internal/artifactcache"
	"image-parser/internal/equipment"
	"image-parser/internal/imagestream"
)

type inspectionLookup struct {
	calls int
}

func (l *inspectionLookup) Resolve(_ context.Context, inspectionTime string, waferKey int32) (equipment.Inspection, error) {
	l.calls++
	return equipment.Inspection{InspectionTime: inspectionTime, WaferKey: waferKey, EquipmentID: "EQP01"}, nil
}

type entryFactory struct {
	opened equipment.OpenParams
}

func (f *entryFactory) Open(_ context.Context, params equipment.OpenParams) (imagestream.Context, error) {
	f.opened = params
	return entryContext{}, nil
}

type entryContext struct{}

func (entryContext) EquipmentID() string { return "EQP01" }
func (entryContext) Resolve(context.Context, []imagestream.SampleRequest) ([]imagestream.SampleResult, error) {
	return nil, nil
}
func (entryContext) Close() error { return nil }

type testCache struct{}

func (testCache) GetOrDownload(context.Context, artifactcache.Ref, artifactcache.DownloadFunc) (string, error) {
	return "", nil
}

func TestEngineResolvesInspectionOnceAndSelectsExactEquipmentEntry(t *testing.T) {
	lookup := &inspectionLookup{}
	factory := &entryFactory{}
	registry, err := equipment.NewRegistry([]equipment.Registration{{EquipmentIDs: []string{"EQP01"}, Factory: factory}})
	if err != nil {
		t.Fatal(err)
	}
	engine, err := equipment.NewEngine(lookup, registry, map[imagestream.UseCase]artifactcache.Cache{
		imagestream.UseCasePrediction: testCache{},
	}, equipment.LimitsByUseCase{Prediction: imagestream.Limits{MaxBatchItems: 512, MaxResponseBytes: 16 << 20, MaxActiveContexts: 8}})
	if err != nil {
		t.Fatal(err)
	}

	opened, err := engine.Open(context.Background(), imagestream.UseCasePrediction, imagestream.OpenRequest{
		ContextID: "context-1", InspectionTime: "2026-08-21T00:00:00Z", WaferKey: 7, Roles: []string{"patch_defective"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if lookup.calls != 1 {
		t.Fatalf("inspection lookup calls = %d", lookup.calls)
	}
	if opened.EquipmentID() != "EQP01" || factory.opened.Inspection.EquipmentID != "EQP01" {
		t.Fatalf("wrong equipment entry: %#v", factory.opened)
	}
	if factory.opened.UseCase != imagestream.UseCasePrediction || factory.opened.Roles[0] != "patch_defective" {
		t.Fatalf("wrong open params: %#v", factory.opened)
	}
}

func TestRegistryRejectsDuplicateAndEngineRejectsUnknownEquipment(t *testing.T) {
	factory := &entryFactory{}
	_, err := equipment.NewRegistry([]equipment.Registration{
		{EquipmentIDs: []string{"EQP01"}, Factory: factory},
		{EquipmentIDs: []string{"EQP01"}, Factory: factory},
	})
	if err == nil {
		t.Fatal("expected duplicate equipment registration error")
	}

	registry, err := equipment.NewRegistry([]equipment.Registration{{EquipmentIDs: []string{"OTHER"}, Factory: factory}})
	if err != nil {
		t.Fatal(err)
	}
	engine, err := equipment.NewEngine(&inspectionLookup{}, registry, map[imagestream.UseCase]artifactcache.Cache{
		imagestream.UseCasePrediction: testCache{},
	}, equipment.LimitsByUseCase{
		Prediction: imagestream.Limits{MaxBatchItems: 1, MaxResponseBytes: 1, MaxActiveContexts: 1},
	})
	if err != nil {
		t.Fatal(err)
	}
	_, err = engine.Open(context.Background(), imagestream.UseCasePrediction, imagestream.OpenRequest{
		ContextID: "context-1", InspectionTime: "2026-08-21T00:00:00Z", WaferKey: 7, Roles: []string{"patch_defective"},
	})
	var contextErr *imagestream.ContextError
	if !errors.As(err, &contextErr) || contextErr.Code != "unknown_equipment" {
		t.Fatalf("error = %#v", err)
	}
}
