package directfiles

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"image-parser/internal/filesource"
	"image-parser/internal/sourceformat"
)

func TestDriverReadsExplicitRolePathsFromDirectory(t *testing.T) {
	root := t.TempDir()
	if err := os.Mkdir(filepath.Join(root, "sample-1"), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "sample-1", "defective.tiff"), []byte("defective"), 0o600); err != nil {
		t.Fatal(err)
	}
	source, err := filesource.Open(root, filesource.KindDirectory, filesource.OwnershipBorrowed)
	if err != nil {
		t.Fatal(err)
	}
	results := (Driver{}).Resolve(context.Background(), source, []sourceformat.Request{{
		RequestID: "request-1",
		SampleID:  "sample-1",
		Roles:     []string{"Defective", "Reference"},
		RolePaths: map[string]string{
			"Defective": "sample-1/defective.tiff",
			"Reference": "../outside.tiff",
		},
	}})
	if len(results) != 2 {
		t.Fatalf("expected two role results, got %d", len(results))
	}
	if string(results[0].Data) != "defective" || results[0].ContentType != "image/tiff" || results[0].Err != nil {
		t.Fatalf("unexpected successful result: %#v", results[0])
	}
	if results[1].Err == nil {
		t.Fatalf("unsafe role path did not produce an item error: %#v", results[1])
	}
}

func TestDriverReadsSingleFileSourceWithoutInventingALayout(t *testing.T) {
	path := filepath.Join(t.TempDir(), "asset.bin")
	if err := os.WriteFile(path, []byte("asset"), 0o600); err != nil {
		t.Fatal(err)
	}
	source, err := filesource.Open(path, filesource.KindFile, filesource.OwnershipBorrowed)
	if err != nil {
		t.Fatal(err)
	}
	results := (Driver{}).Resolve(context.Background(), source, []sourceformat.Request{{
		RequestID: "request-1",
		SampleID:  "sample-1",
		Roles:     []string{"Defective"},
		RolePaths: map[string]string{"Defective": ""},
	}})
	if len(results) != 1 || string(results[0].Data) != "asset" || results[0].Err != nil {
		t.Fatalf("unexpected results: %#v", results)
	}
}
