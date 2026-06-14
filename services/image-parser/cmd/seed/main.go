package main

import (
	"archive/zip"
	"bytes"
	"context"
	"fmt"
	"image"
	"image/png"
	"log"
	"math/rand"
	"sync"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"image-parser/internal/s3client"
)

const (
	totalZips      = 500
	imagesPerZip   = 2000
	imageSize      = 32
	bucketName     = "images"
	workerCount    = 10
)

func main() {
	client := s3client.Get()

	if err := ensureBucket(client); err != nil {
		log.Fatalf("failed to ensure bucket: %v", err)
	}

	zipCh := make(chan int, totalZips)
	var wg sync.WaitGroup

	for i := 0; i < workerCount; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for idx := range zipCh {
				if err := generateAndUploadZip(client, idx); err != nil {
					log.Printf("ERROR zip %d: %v", idx, err)
				} else {
					log.Printf("OK zip %d (%s)", idx, zipKey(idx))
				}
			}
		}()
	}

	for i := 0; i < totalZips; i++ {
		zipCh <- i
	}
	close(zipCh)
	wg.Wait()

	log.Println("seed complete")
}

func ensureBucket(client *s3.Client) error {
	_, err := client.HeadBucket(context.TODO(), &s3.HeadBucketInput{
		Bucket: aws.String(bucketName),
	})
	if err == nil {
		log.Printf("bucket %q already exists", bucketName)
		return nil
	}

	_, err = client.CreateBucket(context.TODO(), &s3.CreateBucketInput{
		Bucket: aws.String(bucketName),
	})
	if err != nil {
		return fmt.Errorf("create bucket %q: %w", bucketName, err)
	}
	log.Printf("bucket %q created", bucketName)
	return nil
}

func zipKey(idx int) string {
	return fmt.Sprintf("batch_%05d.zip", idx)
}

func generateAndUploadZip(client *s3.Client, idx int) error {
	startImg := idx * imagesPerZip

	buf := new(bytes.Buffer)
	zipWriter := zip.NewWriter(buf)

	for i := 0; i < imagesPerZip; i++ {
		name := fmt.Sprintf("img_%06d.png", startImg+i)
		w, err := zipWriter.Create(name)
		if err != nil {
			return fmt.Errorf("create %s: %w", name, err)
		}

		img := generateGrayImage()
		if err := png.Encode(w, img); err != nil {
			return fmt.Errorf("encode %s: %w", name, err)
		}
	}

	if err := zipWriter.Close(); err != nil {
		return fmt.Errorf("close zip: %w", err)
	}

	key := zipKey(idx)
	_, err := client.PutObject(context.TODO(), &s3.PutObjectInput{
		Bucket: aws.String(bucketName),
		Key:    aws.String(key),
		Body:   bytes.NewReader(buf.Bytes()),
	})

	return err
}

func generateGrayImage() *image.Gray {
	img := image.NewGray(image.Rect(0, 0, imageSize, imageSize))
	pix := img.Pix
	for i := range pix {
		pix[i] = byte(rand.Intn(256))
	}
	return img
}
