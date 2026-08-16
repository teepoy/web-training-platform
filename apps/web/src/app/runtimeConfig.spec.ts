import { afterEach, describe, expect, it } from "vitest";
import { getOperatorConsoleConfiguration } from "./runtimeConfig";

afterEach(() => {
  delete window.__PLATFORM_RUNTIME_CONFIG__;
});

describe("operator console runtime configuration", () => {
  it("accepts credential-free HTTPS console URLs", () => {
    window.__PLATFORM_RUNTIME_CONFIG__ = {
      operatorPrefectUiUrl: "https://prefect-admin.example.com",
      operatorMinioConsoleUrl: "https://minio-admin.example.com/console",
    };

    const configuration = getOperatorConsoleConfiguration();

    expect(configuration.prefect).toEqual({
      configuredValue: "https://prefect-admin.example.com",
      url: "https://prefect-admin.example.com/",
      status: "available",
    });
    expect(configuration.minio.status).toBe("available");
  });

  it("does not expose missing, insecure, or credential-bearing URLs", () => {
    window.__PLATFORM_RUNTIME_CONFIG__ = {
      operatorPrefectUiUrl: "http://prefect.example.com",
      operatorMinioConsoleUrl: "https://operator:secret@minio.example.com",
    };

    const configuration = getOperatorConsoleConfiguration();

    expect(configuration.prefect).toMatchObject({ url: null, status: "invalid" });
    expect(configuration.minio).toMatchObject({ url: null, status: "invalid" });
  });

  it("reports omitted URLs as not configured", () => {
    expect(getOperatorConsoleConfiguration()).toEqual({
      prefect: { configuredValue: null, url: null, status: "not-configured" },
      minio: { configuredValue: null, url: null, status: "not-configured" },
    });
  });
});
