// Package legacyrangezip is the only place that knows the historical SC
// 500-defect ZIP layout and member naming rules. It is an optional format
// driver, not the platform's generic image source model.
package legacyrangezip

import (
	"archive/zip"
	"bytes"
	"context"
	"fmt"
	"io"
	"mime"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"image-parser/internal/filesource"
	"image-parser/internal/sourceformat"
)

const (
	FormatID            = "sc.legacy-range-zip.v1"
	FieldInspectionTime = "inspection_time"
	FieldWaferKey       = "wafer_key"
	FieldDefectID       = "defect_id"
	defectsPerArchive   = 500
	inspectionLayout    = "20060102_150405"
	archiveWorkerLimit  = 8
)

type Driver struct{}

func (Driver) Format() string { return FormatID }

func (Driver) Resolve(ctx context.Context, source *filesource.Source, requests []sourceformat.Request) []sourceformat.Result {
	totalRoles := 0
	for _, request := range requests {
		totalRoles += len(request.Roles)
	}
	results := make([]sourceformat.Result, totalRoles)
	type plannedAsset struct {
		resultIndex int
		prefix      string
	}
	groups := map[string][]plannedAsset{}
	resultIndex := 0
	for _, request := range requests {
		for _, role := range request.Roles {
			results[resultIndex] = sourceformat.Result{RequestID: request.RequestID, SampleID: request.SampleID, Role: role}
			if err := ctx.Err(); err != nil {
				results[resultIndex].Err = err
				resultIndex++
				continue
			}
			archivePath, memberPrefix, err := locate(request.Fields, role)
			if err != nil {
				results[resultIndex].Err = err
				resultIndex++
				continue
			}
			groups[archivePath] = append(groups[archivePath], plannedAsset{resultIndex: resultIndex, prefix: memberPrefix})
			resultIndex++
		}
	}

	semaphore := make(chan struct{}, archiveWorkerLimit)
	var wait sync.WaitGroup
	for archivePath, assets := range groups {
		wait.Add(1)
		go func(archivePath string, assets []plannedAsset) {
			defer wait.Done()
			semaphore <- struct{}{}
			defer func() { <-semaphore }()
			if err := ctx.Err(); err != nil {
				for _, asset := range assets {
					results[asset.resultIndex].Err = err
				}
				return
			}
			archiveData, err := source.ReadFile(archivePath)
			if err != nil {
				for _, asset := range assets {
					results[asset.resultIndex].Err = fmt.Errorf("read legacy range archive: %w", err)
				}
				return
			}
			prefixes := make([]string, len(assets))
			for index, asset := range assets {
				prefixes[index] = asset.prefix
			}
			matches := readMembers(archiveData, prefixes)
			for _, asset := range assets {
				match := matches[asset.prefix]
				if match.err != nil {
					results[asset.resultIndex].Err = match.err
					continue
				}
				results[asset.resultIndex].Data = match.data
				results[asset.resultIndex].ContentType = mime.TypeByExtension(filepath.Ext(match.name))
				if results[asset.resultIndex].ContentType == "" {
					results[asset.resultIndex].ContentType = "application/octet-stream"
				}
			}
		}(archivePath, assets)
	}
	wait.Wait()
	return results
}

func locate(fields map[string]string, role string) (string, string, error) {
	archivePath, defectID, err := archiveLocation(fields)
	if err != nil {
		return "", "", err
	}
	memberRole, err := memberRole(role)
	if err != nil {
		return "", "", err
	}
	return archivePath, fmt.Sprintf("%06d_%s", defectID, memberRole), nil
}

func archiveLocation(fields map[string]string) (string, int, error) {
	inspection, err := inspectionFolder(fields[FieldInspectionTime])
	if err != nil {
		return "", 0, err
	}
	waferKey, err := strconv.Atoi(strings.TrimSpace(fields[FieldWaferKey]))
	if err != nil || waferKey <= 0 {
		return "", 0, fmt.Errorf("wafer_key must be a positive integer")
	}
	defectID, err := parseDefectID(fields[FieldDefectID])
	if err != nil || defectID <= 0 {
		return "", 0, fmt.Errorf("defect_id must end in a positive integer")
	}
	archiveIndex := (defectID - 1) / defectsPerArchive
	start := archiveIndex*defectsPerArchive + 1
	end := start + defectsPerArchive - 1
	archivePath := filepath.Join(inspection, strconv.Itoa(waferKey), fmt.Sprintf("%06d-%06d.zip", start, end))
	return archivePath, defectID, nil
}

func inspectionFolder(raw string) (string, error) {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return "", fmt.Errorf("inspection_time is required")
	}
	if parsed, err := time.Parse(inspectionLayout, trimmed); err == nil {
		return parsed.Format(inspectionLayout), nil
	}
	parsed, err := time.Parse(time.RFC3339Nano, trimmed)
	if err != nil {
		return "", fmt.Errorf("inspection_time must be RFC3339 or YYYYMMDD_HHMMSS: %w", err)
	}
	return parsed.Format(inspectionLayout), nil
}

func parseDefectID(raw string) (int, error) {
	trimmed := strings.TrimSpace(raw)
	if value, err := strconv.Atoi(trimmed); err == nil {
		return value, nil
	}
	if index := strings.LastIndex(trimmed, "-"); index >= 0 {
		return strconv.Atoi(trimmed[index+1:])
	}
	return 0, fmt.Errorf("invalid defect_id %q", raw)
}

func memberRole(raw string) (string, error) {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "patch_template", "template", "reference", "patchtemplate", "patch_reference", "patchreference":
		return "PatchReference", nil
	case "patch_defective", "defective", "patchdefective":
		return "PatchDefective", nil
	case "patch_difference", "difference", "patchdifference":
		return "PatchDifference", nil
	default:
		return "", fmt.Errorf("unsupported legacy range ZIP role %q", raw)
	}
}

type memberMatch struct {
	data []byte
	name string
	err  error
}

func readMembers(archiveData []byte, prefixes []string) map[string]memberMatch {
	results := make(map[string]memberMatch, len(prefixes))
	wanted := make(map[string]struct{}, len(prefixes))
	for _, prefix := range prefixes {
		results[prefix] = memberMatch{err: fmt.Errorf("image member %q not found in legacy range ZIP", prefix)}
		wanted[prefix] = struct{}{}
	}
	reader, err := zip.NewReader(bytes.NewReader(archiveData), int64(len(archiveData)))
	if err != nil {
		for _, prefix := range prefixes {
			results[prefix] = memberMatch{err: fmt.Errorf("open legacy range ZIP: %w", err)}
		}
		return results
	}
	for _, file := range reader.File {
		stem := strings.TrimSuffix(filepath.Base(file.Name), filepath.Ext(file.Name))
		if _, ok := wanted[stem]; !ok || results[stem].data != nil {
			continue
		}
		prefix := stem
		handle, err := file.Open()
		if err != nil {
			results[prefix] = memberMatch{err: fmt.Errorf("open ZIP member: %w", err)}
			continue
		}
		data, readErr := io.ReadAll(handle)
		closeErr := handle.Close()
		if readErr != nil {
			results[prefix] = memberMatch{err: fmt.Errorf("read ZIP member: %w", readErr)}
			continue
		}
		if closeErr != nil {
			results[prefix] = memberMatch{err: fmt.Errorf("close ZIP member: %w", closeErr)}
			continue
		}
		results[prefix] = memberMatch{data: data, name: file.Name}
	}
	return results
}
