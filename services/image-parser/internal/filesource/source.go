// Package filesource owns the safe, representation-neutral boundary to an
// already-local file or directory. A mounted SMB share is intentionally just a
// borrowed directory source here; downloading, retrying, and cache eviction are
// entrypoint policies and do not belong in this package.
package filesource

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type Kind string

const (
	KindFile      Kind = "file"
	KindDirectory Kind = "directory"
)

type Ownership string

const (
	OwnershipBorrowed    Ownership = "borrowed"
	OwnershipJobOwned    Ownership = "job_owned"
	OwnershipSharedCache Ownership = "shared_cache"
)

var ErrNotJobOwned = errors.New("filesystem source is not job-owned")
var ErrReadOnlySource = errors.New("borrowed filesystem source is read-only")

type Source struct {
	path      string
	kind      Kind
	ownership Ownership
}

func Open(path string, kind Kind, ownership Ownership) (*Source, error) {
	if !filepath.IsAbs(path) {
		return nil, fmt.Errorf("filesystem source path must be absolute")
	}
	resolved, err := filepath.EvalSymlinks(filepath.Clean(path))
	if err != nil {
		return nil, fmt.Errorf("resolve filesystem source: %w", err)
	}
	info, err := os.Stat(resolved)
	if err != nil {
		return nil, fmt.Errorf("stat filesystem source: %w", err)
	}
	switch kind {
	case KindFile:
		if !info.Mode().IsRegular() {
			return nil, fmt.Errorf("filesystem source is not a regular file")
		}
	case KindDirectory:
		if !info.IsDir() {
			return nil, fmt.Errorf("filesystem source is not a directory")
		}
	default:
		return nil, fmt.Errorf("unsupported filesystem source kind %q", kind)
	}
	switch ownership {
	case OwnershipBorrowed, OwnershipJobOwned, OwnershipSharedCache:
	default:
		return nil, fmt.Errorf("unsupported filesystem source ownership %q", ownership)
	}
	return &Source{path: resolved, kind: kind, ownership: ownership}, nil
}

func (s *Source) Path() string { return s.path }

func (s *Source) Kind() Kind { return s.kind }

func (s *Source) Ownership() Ownership { return s.ownership }

func (s *Source) ReadFile(relative string) ([]byte, error) {
	path, err := s.Resolve(relative)
	if err != nil {
		return nil, err
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	if s.ownership == OwnershipSharedCache {
		now := time.Now()
		if err := os.Chtimes(path, now, now); err != nil && !errors.Is(err, os.ErrNotExist) {
			return nil, fmt.Errorf("touch shared cache source: %w", err)
		}
	}
	return data, nil
}

func (s *Source) HasFile(relative string) (bool, error) {
	_, err := s.Resolve(relative)
	if errors.Is(err, os.ErrNotExist) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}

func (s *Source) WriteFile(relative string, data []byte) error {
	if s.ownership == OwnershipBorrowed {
		return ErrReadOnlySource
	}
	if s.kind != KindDirectory {
		return fmt.Errorf("cannot stage into a file source")
	}
	if filepath.IsAbs(relative) {
		return fmt.Errorf("source path must be relative")
	}
	clean := filepath.Clean(relative)
	if clean == "." || clean == "" {
		return fmt.Errorf("source path must identify a file")
	}
	target := filepath.Join(s.path, clean)
	if !withinRoot(s.path, target) {
		return fmt.Errorf("source path escapes configured root")
	}
	parent := filepath.Dir(target)
	if err := makeSafeDirectories(s.path, parent); err != nil {
		return err
	}
	resolvedParent, err := filepath.EvalSymlinks(parent)
	if err != nil {
		return fmt.Errorf("resolve staged file parent: %w", err)
	}
	if !withinRoot(s.path, resolvedParent) {
		return fmt.Errorf("staged file parent escapes configured root")
	}
	temporary, err := os.CreateTemp(resolvedParent, ".stage-")
	if err != nil {
		return fmt.Errorf("create staged file: %w", err)
	}
	temporaryPath := temporary.Name()
	defer func() {
		_ = temporary.Close()
		_ = os.Remove(temporaryPath)
	}()
	if err := temporary.Chmod(0o600); err != nil {
		return fmt.Errorf("set staged file permissions: %w", err)
	}
	if _, err := temporary.Write(data); err != nil {
		return fmt.Errorf("write staged file: %w", err)
	}
	if err := temporary.Sync(); err != nil {
		return fmt.Errorf("sync staged file: %w", err)
	}
	if err := temporary.Close(); err != nil {
		return fmt.Errorf("close staged file: %w", err)
	}
	if err := os.Rename(temporaryPath, target); err != nil {
		return fmt.Errorf("publish staged file: %w", err)
	}
	return nil
}

func (s *Source) Resolve(relative string) (string, error) {
	if s.kind == KindFile {
		if strings.TrimSpace(relative) != "" {
			return "", fmt.Errorf("file source does not accept a relative path")
		}
		return s.path, nil
	}
	if filepath.IsAbs(relative) {
		return "", fmt.Errorf("source path must be relative")
	}
	clean := filepath.Clean(relative)
	if clean == "." || clean == "" {
		return "", fmt.Errorf("source path must identify a file")
	}
	candidate := filepath.Join(s.path, clean)
	if !withinRoot(s.path, candidate) {
		return "", fmt.Errorf("source path escapes configured root")
	}
	resolved, err := filepath.EvalSymlinks(candidate)
	if err != nil {
		return "", fmt.Errorf("resolve source path: %w", err)
	}
	if !withinRoot(s.path, resolved) {
		return "", fmt.Errorf("source path symlink escapes configured root")
	}
	info, err := os.Stat(resolved)
	if err != nil {
		return "", fmt.Errorf("stat source path: %w", err)
	}
	if !info.Mode().IsRegular() {
		return "", fmt.Errorf("source path is not a regular file")
	}
	return resolved, nil
}

func (s *Source) Cleanup() error {
	if s.ownership != OwnershipJobOwned {
		return ErrNotJobOwned
	}
	return os.RemoveAll(s.path)
}

func withinRoot(root, candidate string) bool {
	relative, err := filepath.Rel(root, candidate)
	if err != nil {
		return false
	}
	return relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator))
}

func makeSafeDirectories(root, target string) error {
	relative, err := filepath.Rel(root, target)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return fmt.Errorf("staged file parent escapes configured root")
	}
	current := root
	for _, part := range strings.Split(relative, string(filepath.Separator)) {
		if part == "" || part == "." {
			continue
		}
		current = filepath.Join(current, part)
		info, err := os.Lstat(current)
		if errors.Is(err, os.ErrNotExist) {
			if err := os.Mkdir(current, 0o750); err != nil && !errors.Is(err, os.ErrExist) {
				return fmt.Errorf("create staged file directory: %w", err)
			}
			continue
		}
		if err != nil {
			return fmt.Errorf("inspect staged file directory: %w", err)
		}
		if info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
			return fmt.Errorf("staged file parent contains a symlink or non-directory")
		}
	}
	return nil
}
