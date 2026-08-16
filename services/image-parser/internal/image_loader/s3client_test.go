package image_loader

import "testing"

func TestObjectStoreConfigUsesSourceThenMinioEnvironment(t *testing.T) {
	t.Setenv("MINIO_ENDPOINT", "fallback:9000")
	t.Setenv("MINIO_ACCESS_KEY", "fallback-access")
	t.Setenv("MINIO_SECRET_KEY", "fallback-secret")
	t.Setenv("SC_PATCH_S3_ENDPOINT", "127.0.0.1:19000")
	t.Setenv("SC_PATCH_S3_ACCESS_KEY", "patch-access")
	t.Setenv("SC_PATCH_S3_SECRET_KEY", "patch-secret")

	config := objectStoreConfigFromEnvironment("SC_PATCH_S3")
	if config.endpoint != "http://127.0.0.1:19000" {
		t.Fatalf("endpoint = %q", config.endpoint)
	}
	if config.accessKey != "patch-access" || config.secretKey != "patch-secret" {
		t.Fatalf("credentials = %q/%q", config.accessKey, config.secretKey)
	}

	t.Setenv("SC_PATCH_S3_ENDPOINT", "")
	t.Setenv("SC_PATCH_S3_ACCESS_KEY", "")
	t.Setenv("SC_PATCH_S3_SECRET_KEY", "")
	config = objectStoreConfigFromEnvironment("SC_PATCH_S3")
	if config.endpoint != "http://fallback:9000" {
		t.Fatalf("fallback endpoint = %q", config.endpoint)
	}
	if config.accessKey != "fallback-access" || config.secretKey != "fallback-secret" {
		t.Fatalf("fallback credentials = %q/%q", config.accessKey, config.secretKey)
	}
}
