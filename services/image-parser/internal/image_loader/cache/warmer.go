package cache

import (
	"sync"
)

type Warmer struct {
	zip     *ZipCache
	load    func(bucket, key string) ([]byte, error)
	warming sync.Map
}

func NewWarmer(z *ZipCache, load func(bucket, key string) ([]byte, error)) *Warmer {
	return &Warmer{zip: z, load: load}
}

func (w *Warmer) Warm(bucket string, keys []string) {
	sem := make(chan struct{}, 50)
	var wg sync.WaitGroup

	for _, k := range keys {
		wg.Add(1)
		go func(key string) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			ck := CacheKey(bucket, key)
			w.zip.GetOrLoad(ck, func() ([]byte, error) {
				return w.load(bucket, key)
			})
		}(k)
	}
	wg.Wait()
}

func (w *Warmer) WarmAsync(record, bucket string, keys []string) {
	if _, loaded := w.warming.LoadOrStore(record, struct{}{}); loaded {
		return
	}
	go func() {
		defer w.warming.Delete(record)
		w.Warm(bucket, keys)
	}()
}
