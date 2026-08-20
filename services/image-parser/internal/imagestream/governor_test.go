package imagestream

import (
	"context"
	"testing"
	"time"
)

func TestFairLimiterEnforcesGlobalAndLaneCapacity(t *testing.T) {
	limiter, err := NewFairLimiter(GovernorConfig{
		GlobalConcurrency: 2,
		PerUseCase: map[UseCase]int{
			UseCaseDisplay: 1, UseCasePrediction: 1, UseCaseTraining: 1, UseCaseExport: 1,
		},
		Weights: map[UseCase]int{
			UseCaseDisplay: 1, UseCasePrediction: 4, UseCaseTraining: 1, UseCaseExport: 1,
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	releasePrediction, err := limiter.Acquire(context.Background(), UseCasePrediction)
	if err != nil {
		t.Fatal(err)
	}
	releaseTraining, err := limiter.Acquire(context.Background(), UseCaseTraining)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer cancel()
	if _, err := limiter.Acquire(ctx, UseCaseExport); err == nil {
		t.Fatal("third global permit unexpectedly acquired")
	}
	releasePrediction()
	releaseTraining()
}

func TestFairLimiterDoesNotLetOneLaneExceedItsLimit(t *testing.T) {
	limiter, err := NewFairLimiter(GovernorConfig{
		GlobalConcurrency: 2,
		PerUseCase: map[UseCase]int{
			UseCaseDisplay: 1, UseCasePrediction: 1, UseCaseTraining: 1, UseCaseExport: 1,
		},
		Weights: map[UseCase]int{
			UseCaseDisplay: 1, UseCasePrediction: 4, UseCaseTraining: 1, UseCaseExport: 1,
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	release, err := limiter.Acquire(context.Background(), UseCasePrediction)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer cancel()
	if _, err := limiter.Acquire(ctx, UseCasePrediction); err == nil {
		t.Fatal("second prediction permit unexpectedly acquired")
	}
	release()
}
