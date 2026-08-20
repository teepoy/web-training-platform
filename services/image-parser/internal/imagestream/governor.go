package imagestream

import (
	"context"
	"fmt"
	"sync"
)

type GovernorConfig struct {
	GlobalConcurrency int
	PerUseCase        map[UseCase]int
	Weights           map[UseCase]int
}

type permitRequest struct {
	useCase  UseCase
	granted  bool
	canceled bool
	ready    chan struct{}
}

// FairLimiter is a bounded weighted round-robin admission queue. Work in each
// semantic lane is FIFO; an idle lane never withholds global capacity.
type FairLimiter struct {
	mu        sync.Mutex
	available int
	capacity  int
	limits    map[UseCase]int
	inFlight  map[UseCase]int
	queues    map[UseCase][]*permitRequest
	schedule  []UseCase
	cursor    int
}

func NewFairLimiter(config GovernorConfig) (*FairLimiter, error) {
	if config.GlobalConcurrency <= 0 {
		return nil, fmt.Errorf("global image resolve concurrency must be positive")
	}
	order := []UseCase{UseCaseDisplay, UseCasePrediction, UseCaseTraining, UseCaseExport}
	limits := make(map[UseCase]int, len(order))
	schedule := make([]UseCase, 0)
	for _, useCase := range order {
		limit := config.PerUseCase[useCase]
		weight := config.Weights[useCase]
		if limit <= 0 || weight <= 0 {
			return nil, fmt.Errorf("%s image lane requires positive concurrency and weight", useCase)
		}
		limits[useCase] = limit
		for range weight {
			schedule = append(schedule, useCase)
		}
	}
	return &FairLimiter{
		available: config.GlobalConcurrency,
		capacity:  config.GlobalConcurrency,
		limits:    limits,
		inFlight:  make(map[UseCase]int, len(order)),
		queues:    make(map[UseCase][]*permitRequest, len(order)),
		schedule:  schedule,
	}, nil
}

func (l *FairLimiter) Acquire(ctx context.Context, useCase UseCase) (func(), error) {
	request := &permitRequest{useCase: useCase, ready: make(chan struct{}, 1)}
	l.mu.Lock()
	if _, ok := l.limits[useCase]; !ok {
		l.mu.Unlock()
		return nil, fmt.Errorf("unknown image resolve lane %q", useCase)
	}
	l.queues[useCase] = append(l.queues[useCase], request)
	l.dispatchLocked()
	l.mu.Unlock()

	select {
	case <-request.ready:
		return l.releaseFunc(useCase), nil
	case <-ctx.Done():
		l.mu.Lock()
		request.canceled = true
		if request.granted {
			request.granted = false
			l.available++
			l.inFlight[useCase]--
		}
		l.dispatchLocked()
		l.mu.Unlock()
		return nil, ctx.Err()
	}
}

func (l *FairLimiter) releaseFunc(useCase UseCase) func() {
	var once sync.Once
	return func() {
		once.Do(func() {
			l.mu.Lock()
			l.available++
			l.inFlight[useCase]--
			l.dispatchLocked()
			l.mu.Unlock()
		})
	}
}

func (l *FairLimiter) dispatchLocked() {
	for l.available > 0 {
		selected := UseCase("")
		for range len(l.schedule) {
			useCase := l.schedule[l.cursor]
			l.cursor = (l.cursor + 1) % len(l.schedule)
			l.discardCanceledLocked(useCase)
			if len(l.queues[useCase]) > 0 && l.inFlight[useCase] < l.limits[useCase] {
				selected = useCase
				break
			}
		}
		if selected == "" {
			return
		}
		request := l.queues[selected][0]
		l.queues[selected] = l.queues[selected][1:]
		request.granted = true
		l.available--
		l.inFlight[selected]++
		request.ready <- struct{}{}
	}
}

func (l *FairLimiter) discardCanceledLocked(useCase UseCase) {
	queue := l.queues[useCase]
	for len(queue) > 0 && queue[0].canceled {
		queue = queue[1:]
	}
	l.queues[useCase] = queue
}

type GovernedEngine struct {
	delegate Engine
	limiter  *FairLimiter
}

func NewGovernedEngine(delegate Engine, limiter *FairLimiter) (*GovernedEngine, error) {
	if delegate == nil || limiter == nil {
		return nil, fmt.Errorf("image stream engine and fair limiter are required")
	}
	return &GovernedEngine{delegate: delegate, limiter: limiter}, nil
}

func (e *GovernedEngine) Limits(useCase UseCase) Limits {
	return e.delegate.Limits(useCase)
}

func (e *GovernedEngine) Open(ctx context.Context, useCase UseCase, request OpenRequest) (Context, error) {
	opened, err := e.delegate.Open(ctx, useCase, request)
	if err != nil {
		return nil, err
	}
	return &governedContext{Context: opened, useCase: useCase, limiter: e.limiter}, nil
}

type governedContext struct {
	Context
	useCase UseCase
	limiter *FairLimiter
}

func (c *governedContext) Resolve(ctx context.Context, samples []SampleRequest) ([]SampleResult, error) {
	release, err := c.limiter.Acquire(ctx, c.useCase)
	if err != nil {
		return nil, err
	}
	defer release()
	return c.Context.Resolve(ctx, samples)
}

var _ Engine = (*GovernedEngine)(nil)
