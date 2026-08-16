package client

import "testing"

func TestUpstreamGRPCAddressUsesHostOverride(t *testing.T) {
	t.Setenv("SC_UPSTREAM_ADDR", "127.0.0.1:19091")
	if got := upstreamGRPCAddress(); got != "127.0.0.1:19091" {
		t.Fatalf("upstreamGRPCAddress() = %q", got)
	}
}
