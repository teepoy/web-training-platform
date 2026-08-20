package main

import (
	"archive/zip"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"io"
	"os"
	"sort"
	"strings"
)

func main() {
	if len(os.Args) != 3 {
		fmt.Fprintln(os.Stderr, "usage: hash_module_zip <module.zip> <expected-h1>")
		os.Exit(2)
	}

	actual, err := hashModuleZip(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if actual != os.Args[2] {
		fmt.Fprintf(os.Stderr, "module checksum mismatch: got %s, want %s\n", actual, os.Args[2])
		os.Exit(1)
	}
}

func hashModuleZip(path string) (string, error) {
	archive, err := zip.OpenReader(path)
	if err != nil {
		return "", err
	}
	defer archive.Close()

	files := make(map[string]*zip.File, len(archive.File))
	names := make([]string, 0, len(archive.File))
	for _, file := range archive.File {
		if strings.Contains(file.Name, "\n") {
			return "", fmt.Errorf("module zip contains a newline in filename %q", file.Name)
		}
		files[file.Name] = file
		names = append(names, file.Name)
	}
	sort.Strings(names)

	combined := sha256.New()
	for _, name := range names {
		reader, openErr := files[name].Open()
		if openErr != nil {
			return "", openErr
		}
		content := sha256.New()
		_, copyErr := io.Copy(content, reader)
		closeErr := reader.Close()
		if copyErr != nil {
			return "", copyErr
		}
		if closeErr != nil {
			return "", closeErr
		}
		fmt.Fprintf(combined, "%x  %s\n", content.Sum(nil), name)
	}

	return "h1:" + base64.StdEncoding.EncodeToString(combined.Sum(nil)), nil
}
