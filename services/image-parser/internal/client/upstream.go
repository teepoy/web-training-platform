package client

import (
	"context"
	"fmt"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	scv1 "image-parser/gen/go/sc/v1"
	imageloader "image-parser/internal/image_loader"
	"image-parser/internal/mocksource"
)

type UpstreamClient struct {
	conn *grpc.ClientConn
	stub scv1.ScUpstreamClient
}

var _ imageloader.UpstreamSource = (*UpstreamClient)(nil)

func NewUpstreamClient() (*UpstreamClient, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	conn, err := grpc.DialContext(ctx, mocksource.UpstreamGRPCAddress,
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
