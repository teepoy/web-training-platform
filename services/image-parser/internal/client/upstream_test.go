package client

import "testing"

func TestUpstreamGRPCAddressUsesHostOverride(t *testing.T) {
	t.Setenv("SC_UPSTREAM_ADDR", "127.0.0.1:19091")
	got, err := upstreamGRPCAddress()
	if err != nil {
		t.Fatal(err)
	}
	if got != "127.0.0.1:19091" {
		t.Fatalf("upstreamGRPCAddress() = %q", got)
	}
}

func TestUpstreamGRPCAddressIsRequired(t *testing.T) {
	t.Setenv("SC_UPSTREAM_ADDR", "")
	if _, err := upstreamGRPCAddress(); err == nil {
		t.Fatal("missing SC_UPSTREAM_ADDR was accepted")
	}
}
