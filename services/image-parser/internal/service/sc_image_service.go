package service

import (
	"context"
	"fmt"
	"io"
	"strings"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/proto"
	imageparserv1 "image-parser/gen/go/imageparser/v1"
	"image-parser/internal/imagestream"
	"image-parser/internal/metrics"
)

const (
	defaultContextIdleTimeout = 10 * time.Minute
	contextIdleSweepMaximum   = time.Minute
)

type ScImageService struct {
	imageparserv1.UnimplementedImageParserServer
	streams            imagestream.Engine
	contextIdleTimeout time.Duration
	now                func() time.Time
}

func NewScImageService(streams imagestream.Engine) *ScImageService {
	if streams == nil {
		panic("image stream engine is required")
	}
	return &ScImageService{streams: streams, contextIdleTimeout: defaultContextIdleTimeout, now: time.Now}
}

type imageBidiStream interface {
	Context() context.Context
	Recv() (*imageparserv1.StreamImagesRequest, error)
	Send(*imageparserv1.StreamImagesResponse) error
}

func (s *ScImageService) StreamPredictionImages(stream imageparserv1.ImageParser_StreamPredictionImagesServer) error {
	return s.streamImages(imagestream.UseCasePrediction, stream)
}

func (s *ScImageService) StreamTrainingImages(stream imageparserv1.ImageParser_StreamTrainingImagesServer) error {
	return s.streamImages(imagestream.UseCaseTraining, stream)
}

func (s *ScImageService) StreamExportImages(stream imageparserv1.ImageParser_StreamExportImagesServer) error {
	return s.streamImages(imagestream.UseCaseExport, stream)
}

func (s *ScImageService) streamImages(useCase imagestream.UseCase, stream imageBidiStream) error {
	limits := s.streams.Limits(useCase)
	if limits.MaxBatchItems == 0 || limits.MaxResponseBytes == 0 || limits.MaxActiveContexts == 0 {
		return status.Error(codes.Internal, "image stream limits are invalid")
	}
	contexts := make(map[string]*activeImageContext)
	defer func() {
		for _, opened := range contexts {
			_ = opened.Context.Close()
		}
	}()
	sweepEvery := s.contextIdleTimeout / 4
	if sweepEvery <= 0 || sweepEvery > contextIdleSweepMaximum {
		sweepEvery = contextIdleSweepMaximum
	}
	idleTicker := time.NewTicker(sweepEvery)
	defer idleTicker.Stop()
	type receivedRequest struct {
		request *imageparserv1.StreamImagesRequest
		err     error
	}
	received := make(chan receivedRequest, 1)
	go func() {
		for {
			request, err := stream.Recv()
			select {
			case received <- receivedRequest{request: request, err: err}:
			case <-stream.Context().Done():
				return
			}
			if err != nil {
				return
			}
		}
	}()
	var lastSequence uint64
	var hasSequence bool
	for {
		var request *imageparserv1.StreamImagesRequest
		select {
		case <-stream.Context().Done():
			return stream.Context().Err()
		case now := <-idleTicker.C:
			for contextID, opened := range contexts {
				if now.Sub(opened.lastUsed) < s.contextIdleTimeout {
					continue
				}
				_ = opened.Context.Close()
				delete(contexts, contextID)
				if err := sendContextError(stream, contextID, "context_idle_timeout", "image context exceeded its idle timeout"); err != nil {
					return err
				}
			}
			continue
		case item := <-received:
			request = item.request
			err := item.err
			if err == io.EOF {
				return nil
			}
			if err != nil {
				return err
			}
		}
		switch payload := request.Payload.(type) {
		case *imageparserv1.StreamImagesRequest_OpenContext:
			if err := s.openImageContext(stream, useCase, limits, contexts, payload.OpenContext); err != nil {
				return err
			}
		case *imageparserv1.StreamImagesRequest_SampleBatch:
			batch := payload.SampleBatch
			if batch == nil || strings.TrimSpace(batch.ContextId) == "" || len(batch.Samples) == 0 {
				return status.Error(codes.InvalidArgument, "sample_batch context_id and samples are required")
			}
			if len(batch.Samples) > int(limits.MaxBatchItems) {
				return status.Errorf(codes.ResourceExhausted, "sample batch has %d items; maximum is %d", len(batch.Samples), limits.MaxBatchItems)
			}
			opened, ok := contexts[batch.ContextId]
			if !ok {
				if err := sendContextError(stream, batch.ContextId, "context_not_open", "image context is not open"); err != nil {
					return err
				}
				continue
			}
			samples := make([]imagestream.SampleRequest, len(batch.Samples))
			for index, sample := range batch.Samples {
				if sample == nil || strings.TrimSpace(sample.SampleId) == "" || strings.TrimSpace(sample.DefectId) == "" {
					return status.Error(codes.InvalidArgument, "sample_id and defect_id are required")
				}
				if hasSequence && sample.Sequence <= lastSequence {
					return status.Errorf(codes.InvalidArgument, "sample sequence %d is not greater than %d", sample.Sequence, lastSequence)
				}
				hasSequence = true
				lastSequence = sample.Sequence
				samples[index] = imagestream.SampleRequest{Sequence: sample.Sequence, SampleID: sample.SampleId, DefectID: sample.DefectId}
			}
			opened.lastUsed = s.now()
			resolved, resolveErr := opened.Context.Resolve(stream.Context(), samples)
			if resolveErr != nil {
				_ = opened.Context.Close()
				delete(contexts, batch.ContextId)
				if err := sendContextError(stream, batch.ContextId, imagestream.ErrorCode(resolveErr), resolveErr.Error()); err != nil {
					return err
				}
				continue
			}
			ordered, err := orderSampleResults(samples, resolved)
			if err != nil {
				return status.Error(codes.Internal, err.Error())
			}
			if err := sendSampleBatches(stream, batch.ContextId, ordered, limits.MaxResponseBytes); err != nil {
				return err
			}
			sampleCount, errorCount, imageBytes := imageResultMetrics(ordered)
			metrics.ObserveImageSamples(useCase, sampleCount, errorCount, imageBytes)
		case *imageparserv1.StreamImagesRequest_CloseContext:
			contextID := ""
			if payload.CloseContext != nil {
				contextID = strings.TrimSpace(payload.CloseContext.ContextId)
			}
			opened, ok := contexts[contextID]
			if !ok {
				if err := sendContextError(stream, contextID, "context_not_open", "image context is not open"); err != nil {
					return err
				}
				continue
			}
			if err := opened.Context.Close(); err != nil {
				return status.Errorf(codes.Internal, "close image context: %v", err)
			}
			delete(contexts, contextID)
			if err := stream.Send(&imageparserv1.StreamImagesResponse{Payload: &imageparserv1.StreamImagesResponse_ContextClosed{
				ContextClosed: &imageparserv1.ImageContextClosed{ContextId: contextID},
			}}); err != nil {
				return err
			}
		default:
			return status.Error(codes.InvalidArgument, "image stream request payload is required")
		}
	}
}

type activeImageContext struct {
	imagestream.Context
	lastUsed time.Time
}

func imageResultMetrics(samples []*imageparserv1.ImageSampleResult) (int64, int64, int64) {
	var errors int64
	var bytes int64
	for _, sample := range samples {
		if sample.Error != "" {
			errors++
		}
		for _, image := range sample.Images {
			bytes += int64(len(image.ImageData))
			if image.Error != "" {
				errors++
			}
		}
	}
	return int64(len(samples)), errors, bytes
}

func sendSampleBatches(stream imageBidiStream, contextID string, ordered []*imageparserv1.ImageSampleResult, maxBytes uint64) error {
	current := make([]*imageparserv1.ImageSampleResult, 0, len(ordered))
	send := func(samples []*imageparserv1.ImageSampleResult) error {
		response := &imageparserv1.StreamImagesResponse{Payload: &imageparserv1.StreamImagesResponse_SampleBatch{
			SampleBatch: &imageparserv1.ImageSampleBatchResponse{
				ContextId: contextID, Samples: samples, AckSequence: samples[len(samples)-1].Sequence,
			},
		}}
		if uint64(proto.Size(response)) > maxBytes {
			return status.Errorf(codes.ResourceExhausted, "image sample sequence %d exceeds maximum response bytes %d", samples[0].Sequence, maxBytes)
		}
		return stream.Send(response)
	}
	for _, sample := range ordered {
		candidate := append(current, sample)
		response := &imageparserv1.StreamImagesResponse{Payload: &imageparserv1.StreamImagesResponse_SampleBatch{
			SampleBatch: &imageparserv1.ImageSampleBatchResponse{ContextId: contextID, Samples: candidate, AckSequence: sample.Sequence},
		}}
		if len(current) > 0 && uint64(proto.Size(response)) > maxBytes {
			if err := send(current); err != nil {
				return err
			}
			current = []*imageparserv1.ImageSampleResult{sample}
			continue
		}
		current = candidate
	}
	if len(current) > 0 {
		return send(current)
	}
	return nil
}

func (s *ScImageService) openImageContext(stream imageBidiStream, useCase imagestream.UseCase, limits imagestream.Limits, contexts map[string]*activeImageContext, request *imageparserv1.OpenImageContext) error {
	if request == nil || strings.TrimSpace(request.ContextId) == "" || strings.TrimSpace(request.InspectionTime) == "" || request.WaferKey <= 0 || len(request.Roles) == 0 {
		return status.Error(codes.InvalidArgument, "open_context context_id, inspection_time, wafer_key, and roles are required")
	}
	if _, exists := contexts[request.ContextId]; exists {
		return status.Errorf(codes.AlreadyExists, "image context %q is already open", request.ContextId)
	}
	if len(contexts) >= int(limits.MaxActiveContexts) {
		return status.Errorf(codes.ResourceExhausted, "maximum active image contexts is %d", limits.MaxActiveContexts)
	}
	roles := make([]string, len(request.Roles))
	seen := make(map[string]struct{}, len(request.Roles))
	for index, raw := range request.Roles {
		role := strings.TrimSpace(raw)
		if role == "" {
			return status.Error(codes.InvalidArgument, "image context roles cannot contain an empty role")
		}
		if _, exists := seen[role]; exists {
			return status.Errorf(codes.InvalidArgument, "duplicate image context role %q", role)
		}
		seen[role] = struct{}{}
		roles[index] = role
	}
	opened, err := s.streams.Open(stream.Context(), useCase, imagestream.OpenRequest{
		ContextID: request.ContextId, InspectionTime: request.InspectionTime, WaferKey: request.WaferKey, Roles: roles,
	})
	if err != nil {
		return sendContextError(stream, request.ContextId, imagestream.ErrorCode(err), err.Error())
	}
	contexts[request.ContextId] = &activeImageContext{Context: opened, lastUsed: s.now()}
	return stream.Send(&imageparserv1.StreamImagesResponse{Payload: &imageparserv1.StreamImagesResponse_ContextOpened{
		ContextOpened: &imageparserv1.ImageContextOpened{
			ContextId: request.ContextId,
			EqpId:     opened.EquipmentID(),
			Limits: &imageparserv1.ImageStreamLimits{
				MaxBatchItems: limits.MaxBatchItems, MaxResponseBytes: limits.MaxResponseBytes, MaxActiveContexts: limits.MaxActiveContexts,
			},
		},
	}})
}

func sendContextError(stream imageBidiStream, contextID, code, message string) error {
	return stream.Send(&imageparserv1.StreamImagesResponse{Payload: &imageparserv1.StreamImagesResponse_ContextError{
		ContextError: &imageparserv1.ImageContextError{ContextId: contextID, Code: code, Error: message},
	}})
}

func orderSampleResults(requests []imagestream.SampleRequest, resolved []imagestream.SampleResult) ([]*imageparserv1.ImageSampleResult, error) {
	bySequence := make(map[uint64]imagestream.SampleResult, len(resolved))
	for _, item := range resolved {
		if _, exists := bySequence[item.Sequence]; exists {
			return nil, fmt.Errorf("image resolver returned duplicate sequence %d", item.Sequence)
		}
		bySequence[item.Sequence] = item
	}
	ordered := make([]*imageparserv1.ImageSampleResult, len(requests))
	for index, request := range requests {
		item, exists := bySequence[request.Sequence]
		if !exists {
			return nil, fmt.Errorf("image resolver omitted sequence %d", request.Sequence)
		}
		images := make([]*imageparserv1.ImageRoleResult, len(item.Images))
		for imageIndex, image := range item.Images {
			images[imageIndex] = &imageparserv1.ImageRoleResult{Role: image.Role, ImageData: image.Data, ContentType: image.ContentType}
			if image.Err != nil {
				images[imageIndex].Error = image.Err.Error()
			}
		}
		ordered[index] = &imageparserv1.ImageSampleResult{Sequence: item.Sequence, SampleId: item.SampleID, DefectId: item.DefectID, Images: images}
		if item.Err != nil {
			ordered[index].Error = item.Err.Error()
		}
	}
	if len(bySequence) != len(requests) {
		return nil, fmt.Errorf("image resolver returned unexpected sequences")
	}
	return ordered, nil
}

func (s *ScImageService) Health(ctx context.Context, req *imageparserv1.HealthRequest) (*imageparserv1.HealthResponse, error) {
	return &imageparserv1.HealthResponse{Status: "ok"}, nil
}
