package mocksource

// The current image-parser data source is a local fixture shared by Compose and
// the smoke Kubernetes manifests. Keep its connection contract internal so a
// future production adapter can define its own environment variable names.
const (
	UpstreamGRPCAddress       = "sc-upstream:9091"
	ObjectStoreEndpoint       = "http://minio:9000"
	ObjectStoreRegion         = "us-east-1"
	ObjectStoreAccessKey      = "minioadmin"
	ObjectStoreSecretKey      = "minioadmin"
	ObjectStoreMaxConnections = 1000
	ObjectStoreUsePathStyle   = true
)
