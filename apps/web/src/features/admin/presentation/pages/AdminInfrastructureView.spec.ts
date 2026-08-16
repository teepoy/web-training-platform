import { afterEach, describe, expect, it } from "vitest";
import { mountWithProviders } from "@/testing";
import AdminInfrastructureView from "./AdminInfrastructureView.vue";

afterEach(() => {
  delete window.__PLATFORM_RUNTIME_CONFIG__;
});

describe("AdminInfrastructureView", () => {
  it("shows only explicitly configured protected launch actions", async () => {
    window.__PLATFORM_RUNTIME_CONFIG__ = {
      operatorPrefectUiUrl: "https://prefect-admin.example.com",
    };

    const { wrapper } = await mountWithProviders(AdminInfrastructureView);

    const prefectLink = wrapper.get('[data-testid="prefect-launch"]');
    expect(prefectLink.attributes("href")).toBe("https://prefect-admin.example.com/");
    expect(wrapper.find('[data-testid="minio-launch"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="minio-card"]').text()).toContain("Not configured");
    expect(wrapper.text()).toContain("TLS");
    expect(wrapper.text()).toContain("authenticated reverse proxy or private VPN");
  });

  it("blocks an invalid configured URL", async () => {
    window.__PLATFORM_RUNTIME_CONFIG__ = {
      operatorMinioConsoleUrl: "javascript:alert(1)",
    };

    const { wrapper } = await mountWithProviders(AdminInfrastructureView);

    expect(wrapper.find('[data-testid="minio-launch"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="minio-card"]').text()).toContain(
      "Invalid deployment configuration",
    );
  });
});
