package main

import (
	"flag"
	"fmt"
	"io"
	"log"
	"math/rand"
	"net/http"
	"os"
	"sort"
	"strconv"
	"sync"
	"sync/atomic"
	"time"
)

const (
	imagesPerZip = 2000
	totalImages  = 1000000
)

type BenchResult struct {
	Name      string
	Latencies []time.Duration
	Errors    int64
	Total     int64
	Elapsed   time.Duration
}

func main() {
	mode := flag.String("mode", "both", "benchmark mode: sequential, random, both")
	useCache := flag.Bool("use-cache", false, "append ?cache=true to requests")
	flag.Parse()

	if v := os.Getenv("BENCH_MODE"); v != "" {
		*mode = v
	}
	if v := os.Getenv("USE_CACHE"); v == "true" {
		*useCache = true
	}

	serverURL := os.Getenv("SERVER_URL")
	if serverURL == "" {
		serverURL = "http://localhost:8080/image"
	}
	bucket := os.Getenv("S3_BUCKET")
	if bucket == "" {
		bucket = "images"
	}

	concurrency := 50
	count := 10000
	warmup := 1000

	if v := os.Getenv("CONCURRENCY"); v != "" {
		concurrency, _ = strconv.Atoi(v)
	}
	if v := os.Getenv("REQUEST_COUNT"); v != "" {
		count, _ = strconv.Atoi(v)
	}
	if v := os.Getenv("WARMUP"); v != "" {
		warmup, _ = strconv.Atoi(v)
	}

	transport := &http.Transport{
		MaxIdleConns:        500,
		MaxIdleConnsPerHost: 500,
		IdleConnTimeout:     90 * time.Second,
	}
	httpClient := &http.Client{
		Transport: transport,
		Timeout:   30 * time.Second,
	}

	log.Printf("waiting for server at %s ...", serverURL)
	waitForServer(httpClient, serverURL, bucket, *useCache)
	log.Println("server ready")

	log.Printf("warming up with %d requests...", warmup)
	runWarmup(httpClient, serverURL, bucket, warmup, *useCache)
	log.Println("warmup done")

	switch *mode {
	case "sequential":
		runSequential(httpClient, serverURL, bucket, count, concurrency, *useCache)
	case "random":
		runRandom(httpClient, serverURL, bucket, count, concurrency, *useCache)
	default:
		runSequential(httpClient, serverURL, bucket, count, concurrency, *useCache)
		time.Sleep(2 * time.Second)
		runRandom(httpClient, serverURL, bucket, count, concurrency, *useCache)
	}
}

func zipKey(idx int) string {
	return fmt.Sprintf("batch_%05d.zip", idx)
}

func imagePrefix(num int) string {
	return fmt.Sprintf("img_%06d", num)
}

func makeRequest(client *http.Client, baseURL, bucket string, imageNum int, useCache bool) (time.Duration, error) {
	zipIdx := imageNum / imagesPerZip
	key := zipKey(zipIdx)
	prefix := imagePrefix(imageNum)
	url := fmt.Sprintf("%s?bucket=%s&key=%s&prefix=%s", baseURL, bucket, key, prefix)
	if useCache {
		url += "&cache=true"
	}

	start := time.Now()
	resp, err := client.Get(url)
	if err != nil {
		return time.Since(start), err
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, resp.Body)

	if resp.StatusCode != http.StatusOK {
		return time.Since(start), fmt.Errorf("status %d", resp.StatusCode)
	}
	return time.Since(start), nil
}

func waitForServer(client *http.Client, baseURL, bucket string, useCache bool) {
	for i := 0; i < 60; i++ {
		_, err := makeRequest(client, baseURL, bucket, 0, useCache)
		if err == nil {
			return
		}
		time.Sleep(2 * time.Second)
	}
	log.Fatal("server not reachable after 2 minutes")
}

func runWarmup(client *http.Client, baseURL, bucket string, count int, useCache bool) {
	var wg sync.WaitGroup
	sem := make(chan struct{}, 50)

	for i := 0; i < count; i++ {
		wg.Add(1)
		sem <- struct{}{}
		go func(n int) {
			defer wg.Done()
			defer func() { <-sem }()
			makeRequest(client, baseURL, bucket, n%totalImages, useCache)
		}(i)
	}
	wg.Wait()
}

func runSequential(client *http.Client, baseURL, bucket string, count, concurrency int, useCache bool) {
	log.Printf("running SEQUENTIAL: %d requests, %d concurrency", count, concurrency)

	var (
		counter   int64
		latencies []time.Duration
		errors    int64
		mu        sync.Mutex
		wg        sync.WaitGroup
	)

	start := time.Now()

	for i := 0; i < concurrency; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for {
				n := int(atomic.AddInt64(&counter, 1) - 1)
				if n >= count {
					return
				}
				lat, err := makeRequest(client, baseURL, bucket, n%totalImages, useCache)
				mu.Lock()
				latencies = append(latencies, lat)
				mu.Unlock()
				if err != nil {
					atomic.AddInt64(&errors, 1)
				}
			}
		}()
	}

	wg.Wait()

	printStats("SEQUENTIAL", BenchResult{
		Name:      "SEQUENTIAL",
		Latencies: latencies,
		Errors:    errors,
		Total:     int64(count),
		Elapsed:   time.Since(start),
	})
}

func runRandom(client *http.Client, baseURL, bucket string, count, concurrency int, useCache bool) {
	log.Printf("running RANDOM: %d requests, %d concurrency", count, concurrency)

	var (
		latencies []time.Duration
		errors    int64
		mu        sync.Mutex
		wg        sync.WaitGroup
	)

	start := time.Now()

	for i := 0; i < concurrency; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			remaining := count / concurrency
			if i < count%concurrency {
				remaining++
			}
			for j := 0; j < remaining; j++ {
				imageNum := rand.Intn(totalImages)
				lat, err := makeRequest(client, baseURL, bucket, imageNum, useCache)
				mu.Lock()
				latencies = append(latencies, lat)
				mu.Unlock()
				if err != nil {
					atomic.AddInt64(&errors, 1)
				}
			}
		}()
	}

	wg.Wait()

	printStats("RANDOM", BenchResult{
		Name:      "RANDOM",
		Latencies: latencies,
		Errors:    errors,
		Total:     int64(count),
		Elapsed:   time.Since(start),
	})
}

func printStats(name string, r BenchResult) {
	if len(r.Latencies) == 0 {
		log.Printf("[%s] no data", name)
		return
	}

	sort.Slice(r.Latencies, func(i, j int) bool {
		return r.Latencies[i] < r.Latencies[j]
	})

	count := len(r.Latencies)
	totalTime := time.Duration(0)
	for _, l := range r.Latencies {
		totalTime += l
	}

	avg := totalTime / time.Duration(count)
	min := r.Latencies[0]
	max := r.Latencies[count-1]
	p50 := percentile(r.Latencies, 0.50)
	p90 := percentile(r.Latencies, 0.90)
	p95 := percentile(r.Latencies, 0.95)
	p99 := percentile(r.Latencies, 0.99)
	qps := float64(count) / r.Elapsed.Seconds()

	fmt.Println()
	fmt.Printf("========== %s ==========\n", name)
	fmt.Printf("  Total Requests : %d\n", r.Total)
	fmt.Printf("  Errors         : %d\n", r.Errors)
	fmt.Printf("  QPS            : %.2f req/s\n", qps)
	fmt.Printf("  Wall Time      : %v\n", r.Elapsed.Round(time.Millisecond))
	fmt.Println("  --- Latency ---")
	fmt.Printf("  Min    : %v\n", min.Round(time.Microsecond))
	fmt.Printf("  Avg    : %v\n", avg.Round(time.Microsecond))
	fmt.Printf("  Max    : %v\n", max.Round(time.Microsecond))
	fmt.Printf("  P50    : %v\n", p50.Round(time.Microsecond))
	fmt.Printf("  P90    : %v\n", p90.Round(time.Microsecond))
	fmt.Printf("  P95    : %v\n", p95.Round(time.Microsecond))
	fmt.Printf("  P99    : %v\n", p99.Round(time.Microsecond))
	fmt.Println("==============================")
}

func percentile(sorted []time.Duration, p float64) time.Duration {
	idx := int(float64(len(sorted)) * p)
	if idx >= len(sorted) {
		idx = len(sorted) - 1
	}
	return sorted[idx]
}
