// Package entrylock coordinates publication and eviction of artifact-cache
// entries across goroutines and processes sharing the same filesystem root.
package entrylock

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"golang.org/x/sys/unix"
)

const coordinationDirectory = ".entry-locks"
const retryInterval = 10 * time.Millisecond

// Lock is an advisory cache-entry lock. Its coordination file intentionally
// survives for the cache-root lifetime: unlinking a lock file can split waiters
// across different inodes. Closing the descriptor (including process exit)
// releases the kernel lock, so stale-lock timeouts are neither needed nor safe.
type Lock struct {
	file       *os.File
	release    sync.Once
	releaseErr error
}

// Acquire waits until the entry is exclusively locked or ctx is canceled.
// Download, publication, and eviction use this mode. Callers own the deadline;
// the cache does not invent an implicit timeout.
func Acquire(ctx context.Context, root string, relative string) (*Lock, error) {
	return acquire(ctx, root, relative, unix.LOCK_EX)
}

// AcquireShared waits until the entry has a shared usage lock or ctx is
// canceled. Multiple artifact readers may hold this lock concurrently while an
// exclusive download, publication, or eviction lock remains blocked.
func AcquireShared(ctx context.Context, root string, relative string) (*Lock, error) {
	return acquire(ctx, root, relative, unix.LOCK_SH)
}

func acquire(ctx context.Context, root string, relative string, mode int) (*Lock, error) {
	for {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		lock, acquired, err := tryAcquire(root, relative, mode)
		if err != nil {
			return nil, err
		}
		if acquired {
			return lock, nil
		}
		timer := time.NewTimer(retryInterval)
		select {
		case <-ctx.Done():
			if !timer.Stop() {
				<-timer.C
			}
			return nil, ctx.Err()
		case <-timer.C:
		}
	}
}

// TryAcquire attempts to lock the entry without waiting.
func TryAcquire(root string, relative string) (*Lock, bool, error) {
	return tryAcquire(root, relative, unix.LOCK_EX)
}

func tryAcquire(root string, relative string, mode int) (*Lock, bool, error) {
	path, err := coordinationPath(root, relative)
	if err != nil {
		return nil, false, err
	}
	fd, err := unix.Open(path, unix.O_CREAT|unix.O_RDWR|unix.O_CLOEXEC|unix.O_NOFOLLOW, 0o600)
	if err != nil {
		return nil, false, fmt.Errorf("open artifact cache entry lock: %w", err)
	}
	file := os.NewFile(uintptr(fd), path)
	if file == nil {
		_ = unix.Close(fd)
		return nil, false, fmt.Errorf("open artifact cache entry lock: invalid file descriptor")
	}
	info, err := file.Stat()
	if err != nil {
		_ = file.Close()
		return nil, false, fmt.Errorf("stat artifact cache entry lock: %w", err)
	}
	if !info.Mode().IsRegular() {
		_ = file.Close()
		return nil, false, fmt.Errorf("artifact cache entry lock is not a regular file")
	}
	if err := unix.Flock(fd, mode|unix.LOCK_NB); err != nil {
		_ = file.Close()
		if errors.Is(err, unix.EWOULDBLOCK) || errors.Is(err, unix.EAGAIN) {
			return nil, false, nil
		}
		return nil, false, fmt.Errorf("acquire artifact cache entry lock: %w", err)
	}
	return &Lock{file: file}, true, nil
}

func (l *Lock) Release() error {
	if l == nil || l.file == nil {
		return nil
	}
	l.release.Do(func() {
		unlockErr := unix.Flock(int(l.file.Fd()), unix.LOCK_UN)
		closeErr := l.file.Close()
		if unlockErr != nil {
			l.releaseErr = fmt.Errorf("release artifact cache entry lock: %w", unlockErr)
		}
		if closeErr != nil {
			l.releaseErr = errors.Join(l.releaseErr, fmt.Errorf("close artifact cache entry lock: %w", closeErr))
		}
	})
	return l.releaseErr
}

func coordinationPath(root string, relative string) (string, error) {
	if !filepath.IsAbs(root) {
		return "", fmt.Errorf("artifact cache entry lock root must be absolute")
	}
	resolvedRoot, err := filepath.EvalSymlinks(filepath.Clean(root))
	if err != nil {
		return "", fmt.Errorf("resolve artifact cache entry lock root: %w", err)
	}
	info, err := os.Stat(resolvedRoot)
	if err != nil || !info.IsDir() {
		return "", fmt.Errorf("artifact cache entry lock root must be an existing directory")
	}
	clean, err := cleanTarget(relative)
	if err != nil {
		return "", err
	}
	lockDirectory := filepath.Join(resolvedRoot, coordinationDirectory)
	if err := ensureCoordinationDirectory(resolvedRoot, lockDirectory); err != nil {
		return "", err
	}
	name := fmt.Sprintf("%x.lock", sha256.Sum256([]byte(clean)))
	return filepath.Join(lockDirectory, name), nil
}

func cleanTarget(relative string) (string, error) {
	if filepath.IsAbs(relative) {
		return "", fmt.Errorf("artifact cache entry lock target must be relative")
	}
	clean := filepath.Clean(relative)
	if clean == "." || strings.TrimSpace(clean) == "" {
		return "", fmt.Errorf("artifact cache entry lock target must identify an entry")
	}
	if clean == ".." || strings.HasPrefix(clean, ".."+string(filepath.Separator)) {
		return "", fmt.Errorf("artifact cache entry lock target escapes configured root")
	}
	if clean == coordinationDirectory || strings.HasPrefix(clean, coordinationDirectory+string(filepath.Separator)) {
		return "", fmt.Errorf("artifact cache entry lock target uses the reserved coordination namespace")
	}
	return clean, nil
}

func ensureCoordinationDirectory(root, path string) error {
	if err := os.Mkdir(path, 0o750); err != nil && !errors.Is(err, os.ErrExist) {
		return fmt.Errorf("create artifact cache entry lock directory: %w", err)
	}
	info, err := os.Lstat(path)
	if err != nil {
		return fmt.Errorf("inspect artifact cache entry lock directory: %w", err)
	}
	if info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return fmt.Errorf("artifact cache entry lock directory is a symlink or non-directory")
	}
	resolved, err := filepath.EvalSymlinks(path)
	if err != nil {
		return fmt.Errorf("resolve artifact cache entry lock directory: %w", err)
	}
	relative, err := filepath.Rel(root, resolved)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return fmt.Errorf("artifact cache entry lock directory escapes configured root")
	}
	return nil
}
