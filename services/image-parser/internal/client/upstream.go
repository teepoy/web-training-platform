package client

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	scv1 "image-parser/gen/go/sc/v1"
	"image-parser/internal/display"
	"image-parser/internal/equipment"
)

type UpstreamClient struct {
	conn *grpc.ClientConn
	stub scv1.ScUpstreamClient
}

var _ display.UpstreamSource = (*UpstreamClient)(nil)

func NewUpstreamClient() (*UpstreamClient, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	address, err := upstreamGRPCAddress()
	if err != nil {
		return nil, err
	}
	conn, err := grpc.DialContext(ctx, address,
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

func upstreamGRPCAddress() (string, error) {
	if address := strings.TrimSpace(os.Getenv("SC_UPSTREAM_ADDR")); address != "" {
		return strings.TrimPrefix(address, "grpc://"), nil
	}
	return "", fmt.Errorf("SC_UPSTREAM_ADDR is required")
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

func (c *UpstreamClient) Resolve(ctx context.Context, inspectionTime string, waferKey int32) (equipment.Inspection, error) {
	response, err := c.GetInspection(ctx, inspectionTime, waferKey)
	if err != nil {
		return equipment.Inspection{}, err
	}
	return equipment.Inspection{
		InspectionTime: response.InspectionTime,
		WaferKey:       response.WaferKey,
		EquipmentID:    response.EqpId,
		LotID:          response.LotId,
		WaferID:        response.WaferId,
		Device:         response.Device,
		LayerID:        response.LayerId,
	}, nil
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
