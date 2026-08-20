// Package imagestream defines the service-owned image streaming boundary used
// by prediction, training, and image-bearing exports.
package imagestream

import "context"

type UseCase string

const (
	UseCaseDisplay    UseCase = "display"
	UseCasePrediction UseCase = "prediction"
	UseCaseTraining   UseCase = "training"
	UseCaseExport     UseCase = "export"
)

type Limits struct {
	MaxBatchItems     uint32
	MaxResponseBytes  uint64
	MaxActiveContexts uint32
}

type OpenRequest struct {
	ContextID      string
	InspectionTime string
	WaferKey       int32
	Roles          []string
}

type SampleRequest struct {
	Sequence uint64
	SampleID string
	DefectID string
}

type RoleResult struct {
	Role        string
	Data        []byte
	ContentType string
	Err         error
}

type SampleResult struct {
	Sequence uint64
	SampleID string
	DefectID string
	Images   []RoleResult
	Err      error
}

type Context interface {
	EquipmentID() string
	Resolve(ctx context.Context, samples []SampleRequest) ([]SampleResult, error)
	Close() error
}

type Engine interface {
	Limits(useCase UseCase) Limits
	Open(ctx context.Context, useCase UseCase, request OpenRequest) (Context, error)
}

type ContextError struct {
	Code    string
	Message string
}

func (e *ContextError) Error() string { return e.Message }

func ErrorCode(err error) string {
	if typed, ok := err.(*ContextError); ok && typed.Code != "" {
		return typed.Code
	}
	return "context_unavailable"
}
