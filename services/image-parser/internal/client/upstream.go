package client

import (
	"context"
	"fmt"
	"os"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	scv1 "image-parser/gen/go/sc/v1"
)

type UpstreamClient struct {
	conn *grpc.ClientConn
	stub scv1.ScUpstreamClient
}

func NewUpstreamClient() (*UpstreamClient, error) {
	addr := os.Getenv("SC_UPSTREAM_ADDR")
	if addr == "" {
		addr = "localhost:9091"
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	conn, err := grpc.DialContext(ctx, addr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithBlock(),
	)
	if err != nil {
		return nil, fmt.Errorf("dial sc-upstream: %w", err)
	}

	return &UpstreamClient{
		conn: conn,
		stub: scv1.NewScUpstreamClient(conn),
	}, nil
}

func (c *UpstreamClient) Close() error {
	return c.conn.Close()
}

func (c *UpstreamClient) GetInspection(ctx context.Context, inspectionTime string, waferKey int32) (*scv1.GetInspectionResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	return c.stub.GetInspection(ctx, &scv1.GetInspectionRequest{
		InspectionTime: inspectionTime,
		WaferKey:       waferKey,
	})
}

func (c *UpstreamClient) GetInspectionPatchZips(ctx context.Context, inspectionTime, lotID, waferID, device, layerID string) (*scv1.GetInspectionPatchZipsResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	return c.stub.GetInspectionPatchZips(ctx, &scv1.GetInspectionPatchZipsRequest{
		InspectionTime: inspectionTime,
		LotId:          lotID,
		WaferId:        waferID,
		Device:         device,
		LayerId:        layerID,
	})
}

func (c *UpstreamClient) GetReviewImageFileSpec(ctx context.Context, inspectionTime string, waferKey, defectID, imageID int32) (*scv1.GetReviewImageFileSpecResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	return c.stub.GetReviewImageFileSpec(ctx, &scv1.GetReviewImageFileSpecRequest{
		InspectionTime: inspectionTime,
		WaferKey:       waferKey,
		DefectId:       defectID,
		ImageId:        imageID,
	})
}

func (c *UpstreamClient) ListReviewImages(ctx context.Context, inspectionTime string, waferKey, defectID int32) (*scv1.ListReviewImagesResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	return c.stub.ListReviewImages(ctx, &scv1.ListReviewImagesRequest{
		InspectionTime: inspectionTime,
		WaferKey:       waferKey,
		DefectId:       defectID,
	})
}
