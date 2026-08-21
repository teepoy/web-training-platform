package entrylock

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"testing"
	"time"
)

func TestAcquireWaitsForEntryLockAndHonorsContextCancellation(t *testing.T) {
	root := t.TempDir()
	first, err := Acquire(context.Background(), root, "objects/archive.zip")
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	result := make(chan error, 1)
	go func() {
		lock, err := Acquire(ctx, root, "objects/archive.zip")
		if lock != nil {
			_ = lock.Release()
		}
		result <- err
	}()

	select {
	case err := <-result:
		t.Fatalf("second lock completed before release: %v", err)
	case <-time.After(50 * time.Millisecond):
	}
	cancel()
	select {
	case err := <-result:
		if !errors.Is(err, context.Canceled) {
			t.Fatalf("second lock error = %v, want context cancellation", err)
		}
	case <-time.After(time.Second):
		t.Fatal("canceled lock wait did not return")
	}
	if err := first.Release(); err != nil {
		t.Fatal(err)
	}
}

func TestSharedLocksAllowReadersAndBlockExclusiveJanitor(t *testing.T) {
	root := t.TempDir()
	first, err := AcquireShared(context.Background(), root, "objects/folder")
	if err != nil {
		t.Fatal(err)
	}
	second, err := AcquireShared(context.Background(), root, "objects/folder")
	if err != nil {
		t.Fatal(err)
	}
	if lock, acquired, err := TryAcquire(root, "objects/folder"); err != nil {
		t.Fatal(err)
	} else if acquired {
		_ = lock.Release()
		t.Fatal("exclusive janitor lock was acquired while shared leases were active")
	}
	if err := first.Release(); err != nil {
		t.Fatal(err)
	}
	if lock, acquired, err := TryAcquire(root, "objects/folder"); err != nil {
		t.Fatal(err)
	} else if acquired {
		_ = lock.Release()
		t.Fatal("exclusive janitor lock was acquired while one shared lease remained")
	}
	if err := second.Release(); err != nil {
		t.Fatal(err)
	}
	lock, acquired, err := TryAcquire(root, "objects/folder")
	if err != nil {
		t.Fatal(err)
	}
	if !acquired {
		t.Fatal("exclusive janitor lock was not acquired after shared leases were released")
	}
	if err := lock.Release(); err != nil {
		t.Fatal(err)
	}
}

func TestEntryLockCoordinatesAcrossProcesses(t *testing.T) {
	root := t.TempDir()
	command := exec.Command(os.Args[0], "-test.run=^TestEntryLockHelperProcess$")
	command.Env = append(os.Environ(), "IMAGE_PARSER_ENTRY_LOCK_HELPER=1", "IMAGE_PARSER_ENTRY_LOCK_ROOT="+root)
	stdin, err := command.StdinPipe()
	if err != nil {
		t.Fatal(err)
	}
	stdout, err := command.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	command.Stderr = os.Stderr
	if err := command.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_ = stdin.Close()
		if command.ProcessState == nil {
			_ = command.Process.Kill()
			_ = command.Wait()
		}
	})
	reader := bufio.NewReader(stdout)
	line, err := reader.ReadString('\n')
	if err != nil {
		t.Fatalf("wait for helper lock: %v", err)
	}
	if line != "locked\n" {
		t.Fatalf("unexpected helper output %q", line)
	}
	lock, acquired, err := TryAcquire(root, "objects/archive.zip")
	if err != nil {
		t.Fatal(err)
	}
	if acquired {
		_ = lock.Release()
		t.Fatal("entry lock was acquired while another process held it")
	}
	if err := stdin.Close(); err != nil {
		t.Fatal(err)
	}
	if err := command.Wait(); err != nil {
		t.Fatal(err)
	}
	lock, acquired, err = TryAcquire(root, "objects/archive.zip")
	if err != nil {
		t.Fatal(err)
	}
	if !acquired {
		t.Fatal("entry lock remained stale after helper process exited")
	}
	if err := lock.Release(); err != nil {
		t.Fatal(err)
	}
}

func TestSharedEntryLockBlocksExclusiveEvictionAcrossProcesses(t *testing.T) {
	root := t.TempDir()
	command := exec.Command(os.Args[0], "-test.run=^TestEntryLockHelperProcess$")
	command.Env = append(
		os.Environ(),
		"IMAGE_PARSER_ENTRY_LOCK_HELPER=1",
		"IMAGE_PARSER_ENTRY_LOCK_MODE=shared",
		"IMAGE_PARSER_ENTRY_LOCK_ROOT="+root,
	)
	stdin, err := command.StdinPipe()
	if err != nil {
		t.Fatal(err)
	}
	stdout, err := command.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	command.Stderr = os.Stderr
	if err := command.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_ = stdin.Close()
		if command.ProcessState == nil {
			_ = command.Process.Kill()
			_ = command.Wait()
		}
	})
	reader := bufio.NewReader(stdout)
	if line, err := reader.ReadString('\n'); err != nil {
		t.Fatalf("wait for helper shared lock: %v", err)
	} else if line != "locked\n" {
		t.Fatalf("unexpected helper output %q", line)
	}

	readerLock, err := AcquireShared(context.Background(), root, "objects/archive.zip")
	if err != nil {
		t.Fatal(err)
	}
	if lock, acquired, err := TryAcquire(root, "objects/archive.zip"); err != nil {
		t.Fatal(err)
	} else if acquired {
		_ = lock.Release()
		t.Fatal("exclusive eviction lock was acquired while another process held a shared lease")
	}
	if err := readerLock.Release(); err != nil {
		t.Fatal(err)
	}
	if err := stdin.Close(); err != nil {
		t.Fatal(err)
	}
	if err := command.Wait(); err != nil {
		t.Fatal(err)
	}
	lock, acquired, err := TryAcquire(root, "objects/archive.zip")
	if err != nil {
		t.Fatal(err)
	}
	if !acquired {
		t.Fatal("exclusive eviction lock was not acquired after cross-process readers released")
	}
	if err := lock.Release(); err != nil {
		t.Fatal(err)
	}
}

func TestEntryLockHelperProcess(t *testing.T) {
	if os.Getenv("IMAGE_PARSER_ENTRY_LOCK_HELPER") != "1" {
		return
	}
	acquire := Acquire
	if os.Getenv("IMAGE_PARSER_ENTRY_LOCK_MODE") == "shared" {
		acquire = AcquireShared
	}
	lock, err := acquire(context.Background(), os.Getenv("IMAGE_PARSER_ENTRY_LOCK_ROOT"), "objects/archive.zip")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := fmt.Fprintln(os.Stdout, "locked"); err != nil {
		t.Fatal(err)
	}
	if _, err := io.Copy(io.Discard, os.Stdin); err != nil {
		t.Fatal(err)
	}
	if err := lock.Release(); err != nil {
		t.Fatal(err)
	}
}
