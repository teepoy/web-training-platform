package sqliteimagerows_test

import (
	"context"
	"database/sql"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"image-parser/internal/artifactcache"
	"image-parser/internal/equipment"
	"image-parser/internal/equipment/sqliteimagerows"
	"image-parser/internal/imagestream"

	_ "modernc.org/sqlite"
)

type sqliteSource struct {
	database  []byte
	downloads int
}

func (s *sqliteSource) Describe(
	context.Context,
	equipment.Inspection,
) (sqliteimagerows.Artifact, error) {
	return sqliteimagerows.Artifact{
		SourceIdentity: "fixtures/inspection.sqlite",
		Revision:       "etag:fixture-1",
	}, nil
}

func (s *sqliteSource) Download(
	_ context.Context,
	_ sqliteimagerows.Artifact,
	destination string,
) error {
	s.downloads++
	return os.WriteFile(destination, s.database, 0o600)
}

func TestEntryCachesSQLiteArtifactAndResolvesOrderedRolesInOneContext(t *testing.T) {
	database := makeSQLiteFixture(t)
	source := &sqliteSource{database: database}
	cache, err := artifactcache.New(
		filepath.Join(t.TempDir(), "prediction"),
		artifactcache.Options{
			TTL: time.Hour, CleanupInterval: time.Hour, MaxBytes: 1 << 30,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(cache.Close)

	factory := sqliteimagerows.NewFactory(source)
	params := equipment.OpenParams{
		UseCase: imagestream.UseCasePrediction,
		Inspection: equipment.Inspection{
			InspectionTime: "2026-08-21T00:00:00Z",
			WaferKey:       7,
			EquipmentID:    "EQ-SQLITE-A1",
		},
		Roles: []string{"patch_defective", "patch_template"},
		Cache: cache,
	}
	opened, err := factory.Open(context.Background(), params)
	if err != nil {
		t.Fatal(err)
	}

	results, err := opened.Resolve(
		context.Background(),
		[]imagestream.SampleRequest{
			{Sequence: 10, SampleID: "sample-2", DefectID: "2"},
			{Sequence: 11, SampleID: "sample-1", DefectID: "1"},
			{Sequence: 12, SampleID: "sample-missing", DefectID: "3"},
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if got := string(results[0].Images[0].Data); got != "defective-2" {
		t.Fatalf("first image = %q", got)
	}
	if got := string(results[1].Images[1].Data); got != "template-1" {
		t.Fatalf("ordered role image = %q", got)
	}
	if results[2].Images[0].Err == nil || results[2].Images[1].Err == nil {
		t.Fatalf("missing sample must return per-role errors: %#v", results[2])
	}
	if source.downloads != 1 {
		t.Fatalf("downloads = %d", source.downloads)
	}

	second, err := factory.Open(context.Background(), params)
	if err != nil {
		t.Fatal(err)
	}
	if source.downloads != 1 {
		t.Fatalf("cached artifact downloaded again: %d", source.downloads)
	}
	removed, err := cache.Cleanup(time.Now().Add(2 * time.Hour))
	if err != nil {
		t.Fatal(err)
	}
	if removed != 0 {
		t.Fatalf("removed = %d, want 0 while SQLite contexts hold artifact leases", removed)
	}
	if err := opened.Close(); err != nil {
		t.Fatal(err)
	}
	removed, err = cache.Cleanup(time.Now().Add(2 * time.Hour))
	if err != nil {
		t.Fatal(err)
	}
	if removed != 0 {
		t.Fatalf("removed = %d, want 0 while the second SQLite context remains open", removed)
	}
	if err := second.Close(); err != nil {
		t.Fatal(err)
	}
	removed, err = cache.Cleanup(time.Now().Add(2 * time.Hour))
	if err != nil {
		t.Fatal(err)
	}
	if removed != 1 {
		t.Fatalf("removed = %d, want 1 after SQLite contexts released their artifact leases", removed)
	}
}

func TestEntryRejectsSQLiteArtifactWithoutTheFixedImagesSchema(t *testing.T) {
	path := filepath.Join(t.TempDir(), "invalid.sqlite")
	database, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := database.Exec("CREATE TABLE other_table (value TEXT)"); err != nil {
		_ = database.Close()
		t.Fatal(err)
	}
	if err := database.Close(); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	cache, err := artifactcache.New(
		filepath.Join(t.TempDir(), "prediction"),
		artifactcache.Options{
			TTL: time.Hour, CleanupInterval: time.Hour, MaxBytes: 1 << 30,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(cache.Close)

	_, err = sqliteimagerows.NewFactory(&sqliteSource{database: data}).Open(
		context.Background(),
		equipment.OpenParams{
			UseCase: imagestream.UseCasePrediction,
			Inspection: equipment.Inspection{
				InspectionTime: "2026-08-21T00:00:00Z",
				WaferKey:       7,
				EquipmentID:    "EQ-SQLITE-A1",
			},
			Roles: []string{"patch_defective"},
			Cache: cache,
		},
	)
	var contextErr *imagestream.ContextError
	if !errors.As(err, &contextErr) || contextErr.Code != "parser_unavailable" {
		t.Fatalf("error = %#v", err)
	}
}

func makeSQLiteFixture(t *testing.T) []byte {
	t.Helper()
	path := filepath.Join(t.TempDir(), "fixture.sqlite")
	database, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := database.Exec(`
		CREATE TABLE images (
			sample_id TEXT NOT NULL,
			role TEXT NOT NULL,
			image_bytes BLOB NOT NULL,
			content_type TEXT NOT NULL,
			PRIMARY KEY (sample_id, role)
		)
	`); err != nil {
		_ = database.Close()
		t.Fatal(err)
	}
	for _, row := range []struct {
		sampleID string
		role     string
		data     string
	}{
		{sampleID: "sample-1", role: "patch_defective", data: "defective-1"},
		{sampleID: "sample-1", role: "patch_template", data: "template-1"},
		{sampleID: "sample-2", role: "patch_defective", data: "defective-2"},
		{sampleID: "sample-2", role: "patch_template", data: "template-2"},
	} {
		if _, err := database.Exec(
			"INSERT INTO images(sample_id, role, image_bytes, content_type) VALUES (?, ?, ?, ?)",
			row.sampleID,
			row.role,
			[]byte(row.data),
			"image/png",
		); err != nil {
			_ = database.Close()
			t.Fatal(err)
		}
	}
	if err := database.Close(); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return data
}
