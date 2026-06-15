package zipreader

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

type ZipSizeCache interface {
	GetZipSize(bucket, key string) (int64, bool)
	SetZipSize(bucket, key string, size int64)
}

type S3ReaderAt struct {
	Client *s3.Client
	Bucket string
	Key    string
}

func (r *S3ReaderAt) ReadAt(p []byte, off int64) (n int, err error) {
	rangeHeader := fmt.Sprintf("bytes=%d-%d", off, off+int64(len(p))-1)

	resp, err := r.Client.GetObject(context.TODO(), &s3.GetObjectInput{
		Bucket: aws.String(r.Bucket),
		Key:    aws.String(r.Key),
		Range:  aws.String(rangeHeader),
	})
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()

	return io.ReadFull(resp.Body, p)
}

func GetZipSize(client *s3.Client, bucket, key string) (int64, error) {
	headResp, err := client.HeadObject(context.TODO(), &s3.HeadObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return 0, err
	}
	return aws.ToInt64(headResp.ContentLength), nil
}

func FindImageInZipReader(zipReader *zip.Reader, prefix string) ([]byte, string, error) {
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

func GetImageFromS3Zip(client *s3.Client, bucket, key, prefix string, sizeCache ZipSizeCache) ([]byte, string, error) {
	var fileSize int64
	var err error

	if sizeCache != nil {
		if sz, ok := sizeCache.GetZipSize(bucket, key); ok {
			fileSize = sz
		} else {
			fileSize, err = GetZipSize(client, bucket, key)
			if err != nil {
				return nil, "", fmt.Errorf("head object: %w", err)
			}
			sizeCache.SetZipSize(bucket, key, fileSize)
		}
	} else {
		fileSize, err = GetZipSize(client, bucket, key)
		if err != nil {
			return nil, "", fmt.Errorf("head object: %w", err)
		}
	}

	s3Reader := &S3ReaderAt{
		Client: client,
		Bucket: bucket,
		Key:    key,
	}

	zipReader, err := zip.NewReader(s3Reader, fileSize)
	if err != nil {
		return nil, "", fmt.Errorf("open zip: %w", err)
	}

	return FindImageInZipReader(zipReader, prefix)
}

func GetImageFromBytes(zipData []byte, prefix string) ([]byte, string, error) {
	zipReader, err := zip.NewReader(bytes.NewReader(zipData), int64(len(zipData)))
	if err != nil {
		return nil, "", fmt.Errorf("open zip from bytes: %w", err)
	}

	return FindImageInZipReader(zipReader, prefix)
}

type ImageMatch struct {
	Data []byte
	Name string
	Err  error
}

func GetImagesFromBytes(zipData []byte, prefixes []string) map[string]ImageMatch {
	results := make(map[string]ImageMatch, len(prefixes))
	zipReader, err := zip.NewReader(bytes.NewReader(zipData), int64(len(zipData)))
	if err != nil {
		for _, prefix := range prefixes {
			results[prefix] = ImageMatch{Err: fmt.Errorf("open zip from bytes: %w", err)}
		}
		return results
	}

	for _, prefix := range prefixes {
		results[prefix] = ImageMatch{Err: fmt.Errorf("image with prefix %q not found in zip", prefix)}
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
			results[prefix] = ImageMatch{Err: err}
		} else {
			results[prefix] = ImageMatch{Data: data, Name: f.Name}
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
				results[prefix] = ImageMatch{Err: err}
			} else {
				results[prefix] = ImageMatch{Data: data, Name: f.Name}
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

func DownloadFullZip(client *s3.Client, bucket, key string) ([]byte, error) {
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
