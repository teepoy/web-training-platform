package image_loader

import (
	"archive/zip"
	"bytes"
	"context"
	"fmt"
	"io"
	"path/filepath"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

func findImageInZipReader(zipReader *zip.Reader, prefix string) ([]byte, string, error) {
	for _, f := range zipReader.File {
		if strings.HasPrefix(f.Name, prefix) {
			rc, err := f.Open()
			if err != nil {
				return nil, "", err
			}
			defer rc.Close()

			buf := new(bytes.Buffer)
			if _, err := io.Copy(buf, rc); err != nil {
				return nil, "", err
			}
			return buf.Bytes(), f.Name, nil
		}
	}
	return nil, "", fmt.Errorf("image with prefix %q not found in zip", prefix)
}

func getImageFromBytes(zipData []byte, prefix string) ([]byte, string, error) {
	zipReader, err := zip.NewReader(bytes.NewReader(zipData), int64(len(zipData)))
	if err != nil {
		return nil, "", fmt.Errorf("open zip from bytes: %w", err)
	}

	return findImageInZipReader(zipReader, prefix)
}

type imageMatch struct {
	Data []byte
	Name string
	Err  error
}

func getImagesFromBytes(zipData []byte, prefixes []string) map[string]imageMatch {
	results := make(map[string]imageMatch, len(prefixes))
	zipReader, err := zip.NewReader(bytes.NewReader(zipData), int64(len(zipData)))
	if err != nil {
		for _, prefix := range prefixes {
			results[prefix] = imageMatch{Err: fmt.Errorf("open zip from bytes: %w", err)}
		}
		return results
	}

	for _, prefix := range prefixes {
		results[prefix] = imageMatch{Err: fmt.Errorf("image with prefix %q not found in zip", prefix)}
	}
	wanted := make(map[string]string, len(prefixes))
	for _, prefix := range prefixes {
		wanted[prefix] = prefix
	}
	for _, f := range zipReader.File {
		stem := strings.TrimSuffix(filepath.Base(f.Name), filepath.Ext(f.Name))
		prefix, ok := wanted[stem]
		if !ok {
			continue
		}
		if results[prefix].Data != nil {
			continue
		}
		data, err := readZipFile(f)
		if err != nil {
			results[prefix] = imageMatch{Err: err}
		} else {
			results[prefix] = imageMatch{Data: data, Name: f.Name}
		}
	}
	for _, f := range zipReader.File {
		for _, prefix := range prefixes {
			if results[prefix].Data != nil {
				continue
			}
			if !strings.HasPrefix(f.Name, prefix) {
				continue
			}
			data, err := readZipFile(f)
			if err != nil {
				results[prefix] = imageMatch{Err: err}
			} else {
				results[prefix] = imageMatch{Data: data, Name: f.Name}
			}
		}
	}
	return results
}

func readZipFile(f *zip.File) ([]byte, error) {
	rc, err := f.Open()
	if err != nil {
		return nil, err
	}
	defer rc.Close()

	buf := new(bytes.Buffer)
	if _, err := io.Copy(buf, rc); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

func downloadFullZip(client *s3.Client, bucket, key string) ([]byte, error) {
	resp, err := client.GetObject(context.TODO(), &s3.GetObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return nil, fmt.Errorf("get object: %w", err)
	}
	defer resp.Body.Close()

	buf := new(bytes.Buffer)
	if _, err := io.Copy(buf, resp.Body); err != nil {
		return nil, fmt.Errorf("read object: %w", err)
	}
	return buf.Bytes(), nil
}
