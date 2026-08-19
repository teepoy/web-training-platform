package sourceformat

import (
	"context"
	"os"
	"path/filepath"
	"reflect"
	"testing"

	"image-parser/internal/filesource"
)

type recordingStager struct {
	calls *[]string
}

func (s recordingStager) Stage(_ context.Context, _ *filesource.Source, _ []Request) error {
	*s.calls = append(*s.calls, "stage")
	return nil
}

type recordingDriver struct {
	calls *[]string
}

func (d recordingDriver) Format() string { return "test.files.v1" }

func (d recordingDriver) Resolve(_ context.Context, _ *filesource.Source, requests []Request) []Result {
	*d.calls = append(*d.calls, "resolve")
	return []Result{{RequestID: requests[0].RequestID, Role: "Defective", Data: []byte("ok")}}
}

func TestResolverStagesThenUsesExactlyConfiguredFormat(t *testing.T) {
	root := t.TempDir()
	source, err := filesource.Open(root, filesource.KindDirectory, filesource.OwnershipBorrowed)
	if err != nil {
		t.Fatal(err)
	}
	calls := []string{}
	resolver, err := NewResolver(source, recordingDriver{calls: &calls}, recordingStager{calls: &calls})
	if err != nil {
		t.Fatal(err)
	}
	results, err := resolver.Resolve(context.Background(), "test.files.v1", []Request{{RequestID: "r1"}})
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(calls, []string{"stage", "resolve"}) {
		t.Fatalf("unexpected calls: %#v", calls)
	}
	if got := string(results[0].Data); got != "ok" {
		t.Fatalf("unexpected result %q", got)
	}

	if _, err := resolver.Resolve(context.Background(), "another.format.v1", []Request{{RequestID: "r2"}}); err == nil {
		t.Fatal("format mismatch did not fail")
	}
	if !reflect.DeepEqual(calls, []string{"stage", "resolve"}) {
		t.Fatalf("mismatch invoked a fallback: %#v", calls)
	}
}

func TestResolverCanRunWithoutAStagerForMountedSource(t *testing.T) {
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "ready"), []byte("ready"), 0o600); err != nil {
		t.Fatal(err)
	}
	source, err := filesource.Open(root, filesource.KindDirectory, filesource.OwnershipBorrowed)
	if err != nil {
		t.Fatal(err)
	}
	calls := []string{}
	resolver, err := NewResolver(source, recordingDriver{calls: &calls}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := resolver.Resolve(context.Background(), "test.files.v1", []Request{{RequestID: "r1"}}); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(calls, []string{"resolve"}) {
		t.Fatalf("unexpected calls: %#v", calls)
	}
}
