package service_test

import (
	"archive/zip"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"io"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"testing"
	"time"

	imageparserv1 "image-parser/gen/go/imageparser/v1"
	scv1 "image-parser/gen/go/sc/v1"
	"image-parser/internal/artifactcache"
	"image-parser/internal/equipment"
	legacyrangezip "image-parser/internal/equipment/legacyrangezip"
	"image-parser/internal/imagestream"
	"image-parser/internal/service"

	"google.golang.org/grpc"
)

const (
	acceptanceSamples    = 300_000
	acceptanceWaferKey   = 7
	acceptanceInspection = "2026-08-21T00:00:00Z"
)

// TestPredictionImageStreamWarmCache300KToPython is an explicit hardware gate,
// not a default unit test. It exercises the production range-ZIP parser and
// public gRPC stream, then measures receipt in the generated Python client.
func TestPredictionImageStreamWarmCache300KToPython(t *testing.T) {
	if os.Getenv("SC_IMAGE_STREAM_ACCEPTANCE") != "1" {
		t.Skip("set SC_IMAGE_STREAM_ACCEPTANCE=1 to run the 300k throughput gate")
	}
	fixtureRoot := filepath.Join(t.TempDir(), "fixtures")
	refs, fixtures := writeRangeZIPFixtures(t, fixtureRoot, acceptanceSamples)
	store := &acceptanceObjectStore{fixtures: fixtures}
	cache, err := artifactcache.New(filepath.Join(t.TempDir(), "cache"), artifactcache.Options{
		TTL: time.Hour, CleanupInterval: time.Hour, MaxBytes: 1 << 30,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(cache.Close)
	for _, ref := range refs {
		lease, err := cache.Acquire(context.Background(), artifactcache.Ref{
			EntryID: legacyrangezip.EntryID, SourceIdentity: ref.S3Bucket + "/" + ref.S3Key,
			Revision: store.revision(ref.S3Key), Kind: artifactcache.KindFile,
		}, func(ctx context.Context, destination string) error {
			return store.DownloadPatchObject(ctx, ref.S3Bucket, ref.S3Key, destination)
		})
		if err != nil {
			t.Fatalf("warm fixture %s: %v", ref.S3Key, err)
		}
		if err := lease.Release(); err != nil {
			t.Fatal(err)
		}
	}

	lookup := acceptanceLookup{}
	catalog := acceptanceCatalog{refs: refs}
	registry, err := equipment.NewRegistry([]equipment.Registration{{
		EquipmentIDs: []string{"EQP01"}, Factory: legacyrangezip.NewFactory(catalog, store),
	}})
	if err != nil {
		t.Fatal(err)
	}
	engine, err := equipment.NewEngine(lookup, registry, map[imagestream.UseCase]artifactcache.Cache{
		imagestream.UseCasePrediction: cache,
	}, equipment.LimitsByUseCase{
		Prediction: imagestream.Limits{MaxBatchItems: 512, MaxResponseBytes: 64 << 20, MaxActiveContexts: 2},
	})
	if err != nil {
		t.Fatal(err)
	}

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	grpcServer := grpc.NewServer(grpc.MaxRecvMsgSize(72<<20), grpc.MaxSendMsgSize(72<<20))
	imageparserv1.RegisterImageParserServer(grpcServer, service.NewScImageService(engine))
	go func() { _ = grpcServer.Serve(listener) }()
	t.Cleanup(func() {
		grpcServer.Stop()
		_ = listener.Close()
	})

	repoRoot := repositoryRoot(t)
	command := exec.Command(
		"uv", "run", "--directory", filepath.Join(repoRoot, "apps", "api"),
		"python", "scripts/benchmark_sc_image_stream_receipt.py",
		"--addr", listener.Addr().String(),
		"--inspection-time", acceptanceInspection,
		"--wafer-key", strconv.Itoa(acceptanceWaferKey),
		"--samples", strconv.Itoa(acceptanceSamples),
		"--minimum-samples-per-second", "3000",
	)
	command.Env = os.Environ()
	output, err := command.CombinedOutput()
	if err != nil {
		t.Fatalf("Python receipt benchmark failed: %v\n%s", err, output)
	}
	var result map[string]any
	if err := json.Unmarshal([]byte(strings.TrimSpace(string(output))), &result); err != nil {
		t.Fatalf("decode benchmark output %q: %v", output, err)
	}
	t.Logf("warm-cache prediction image stream: %s", output)
}

type acceptanceLookup struct{}

func (acceptanceLookup) Resolve(context.Context, string, int32) (equipment.Inspection, error) {
	return equipment.Inspection{
		InspectionTime: acceptanceInspection, WaferKey: acceptanceWaferKey,
		EquipmentID: "EQP01", LotID: "LOT-A", WaferID: "W01", Device: "DEV", LayerID: "L1",
	}, nil
}

type acceptanceCatalog struct{ refs []*scv1.ZipRef }

func (c acceptanceCatalog) GetInspectionPatchZips(context.Context, string, string, string, string, string) (*scv1.GetInspectionPatchZipsResponse, error) {
	return &scv1.GetInspectionPatchZipsResponse{Zips: c.refs}, nil
}

type acceptanceObjectStore struct{ fixtures map[string]string }

func (s *acceptanceObjectStore) revision(key string) string { return "fixture-v1:" + key }

func (s *acceptanceObjectStore) DescribePatchObject(_ context.Context, _, key string) (legacyrangezip.ObjectRevision, error) {
	path, ok := s.fixtures[key]
	if !ok {
		return legacyrangezip.ObjectRevision{}, fmt.Errorf("unknown fixture %q", key)
	}
	info, err := os.Stat(path)
	if err != nil {
		return legacyrangezip.ObjectRevision{}, err
	}
	return legacyrangezip.ObjectRevision{Revision: s.revision(key), Size: info.Size()}, nil
}

func (s *acceptanceObjectStore) DownloadPatchObject(ctx context.Context, _, key, destination string) (resultErr error) {
	sourcePath, ok := s.fixtures[key]
	if !ok {
		return fmt.Errorf("unknown fixture %q", key)
	}
	source, err := os.Open(sourcePath)
	if err != nil {
		return err
	}
	defer source.Close()
	target, err := os.OpenFile(destination, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	defer func() { resultErr = errors.Join(resultErr, target.Close()) }()
	if _, err := io.Copy(target, &contextReader{ctx: ctx, reader: source}); err != nil {
		return err
	}
	return target.Sync()
}

type contextReader struct {
	ctx    context.Context
	reader io.Reader
}

func (r *contextReader) Read(buffer []byte) (int, error) {
	if err := r.ctx.Err(); err != nil {
		return 0, err
	}
	return r.reader.Read(buffer)
}

func writeRangeZIPFixtures(t *testing.T, root string, samples int) ([]*scv1.ZipRef, map[string]string) {
	t.Helper()
	if err := os.MkdirAll(root, 0o750); err != nil {
		t.Fatal(err)
	}
	const perArchive = 500
	archiveCount := (samples + perArchive - 1) / perArchive
	refs := make([]*scv1.ZipRef, archiveCount)
	fixtures := make(map[string]string, archiveCount)
	patch := image.NewGray(image.Rect(0, 0, 128, 128))
	for y := range 128 {
		for x := range 128 {
			patch.SetGray(x, y, color.Gray{Y: uint8((x*3 + y*5) % 256)})
		}
	}
	var encoded bytes.Buffer
	if err := png.Encode(&encoded, patch); err != nil {
		t.Fatal(err)
	}
	compressedImage := encoded.Bytes()
	for archiveIndex := range archiveCount {
		key := fmt.Sprintf("range-%04d.zip", archiveIndex)
		path := filepath.Join(root, key)
		file, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
		if err != nil {
			t.Fatal(err)
		}
		archive := zip.NewWriter(file)
		start := archiveIndex*perArchive + 1
		stop := min(start+perArchive, samples+1)
		for defectID := start; defectID < stop; defectID++ {
			for _, role := range []string{"PatchDefective", "PatchReference"} {
				member, err := archive.CreateHeader(&zip.FileHeader{
					Name: fmt.Sprintf("%06d_%s.png", defectID, role), Method: zip.Store,
				})
				if err != nil {
					t.Fatal(err)
				}
				if _, err := member.Write(compressedImage); err != nil {
					t.Fatal(err)
				}
			}
		}
		if err := archive.Close(); err != nil {
			t.Fatal(err)
		}
		if err := file.Close(); err != nil {
			t.Fatal(err)
		}
		refs[archiveIndex] = &scv1.ZipRef{S3Bucket: "benchmark", S3Key: key}
		fixtures[key] = path
	}
	return refs, fixtures
}

func repositoryRoot(t *testing.T) string {
	t.Helper()
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve benchmark source path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(filename), "..", "..", "..", ".."))
}
