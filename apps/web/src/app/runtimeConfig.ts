export interface PlatformRuntimeConfig {
  operatorPrefectUiUrl?: string;
  operatorMinioConsoleUrl?: string;
}

declare global {
  interface Window {
    __PLATFORM_RUNTIME_CONFIG__?: PlatformRuntimeConfig;
  }
}

export interface OperatorConsoleConfiguration {
  configuredValue: string | null;
  url: string | null;
  status: "available" | "not-configured" | "invalid";
}

function readProtectedUrl(value: unknown): OperatorConsoleConfiguration {
  if (typeof value !== "string" || value.trim() === "") {
    return { configuredValue: null, url: null, status: "not-configured" };
  }

  const configuredValue = value.trim();
  try {
    const url = new URL(configuredValue);
    if (url.protocol !== "https:" || url.username !== "" || url.password !== "") {
      return { configuredValue, url: null, status: "invalid" };
    }
    return { configuredValue, url: url.toString(), status: "available" };
  } catch {
    return { configuredValue, url: null, status: "invalid" };
  }
}

export function getOperatorConsoleConfiguration(): {
  prefect: OperatorConsoleConfiguration;
  minio: OperatorConsoleConfiguration;
} {
  const config = window.__PLATFORM_RUNTIME_CONFIG__;
  return {
    prefect: readProtectedUrl(config?.operatorPrefectUiUrl),
    minio: readProtectedUrl(config?.operatorMinioConsoleUrl),
  };
}
