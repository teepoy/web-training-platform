let _getToken: (() => string | null) | null = null;
let _getOrgId: (() => string | null) | null = null;
let _onAuthError: (() => void) | null = null;

/** Configure the Orval fetcher with auth context. Call once at bootstrap. */
export function configureOrvalFetcher(config: {
  getToken?: () => string | null;
  getOrgId?: () => string | null;
  onAuthError?: () => void;
}) {
  if (config.getToken !== undefined) _getToken = config.getToken;
  if (config.getOrgId !== undefined) _getOrgId = config.getOrgId;
  if (config.onAuthError !== undefined) _onAuthError = config.onAuthError;
}

class ApiError extends Error {
  detail: string;
  status: number;

  constructor(detail: string, status: number) {
    super(`API ${status}: ${detail}`);
    this.detail = detail;
    this.status = status;
  }
}

/**
 * Custom fetch mutator for Orval-generated Vue Query hooks.
 * Injects auth token, org ID, handles errors and 204/205 responses.
 * The `url` parameter already includes the full path from the OpenAPI spec
 * (e.g. `/api/v1/datasets`), so no base prefix is prepended.
 */
export const orvalFetcher = async <T>(
  url: string,
  options: RequestInit,
): Promise<T> => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30_000);

  const isFormData = options.body instanceof FormData;
  const headers: Record<string, string> = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...((options.headers as Record<string, string>) ?? {}),
  };

  try {
    const token = _getToken?.() ?? null;
    if (token) headers["Authorization"] = `Bearer ${token}`;
  } catch {}

  try {
    const orgId = _getOrgId?.() ?? null;
    if (orgId) headers["X-Organization-ID"] = orgId;
  } catch {}

  try {
    const response = await fetch(url, {
      ...options,
      headers,
      signal: controller.signal,
    });

    if (!response.ok) {
      if (response.status === 401) {
        try { _onAuthError?.(); } catch {}
      }
      let detail = `request failed: ${response.status}`;
      try {
        const body = await response.json();
        detail =
          typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
      } catch {}
      throw new ApiError(detail, response.status);
    }

    const status = response.status;
    const responseHeaders = response.headers;

    if (response.status === 204 || response.status === 205) {
      return { data: undefined, status, headers: responseHeaders } as T;
    }

    const contentType = responseHeaders.get("Content-Type") ?? "";
    const isJson = contentType.includes("application/json");
    const data = isJson
      ? ((await response.json()) as unknown)
      : ((await response.blob()) as unknown);
    return { data, status, headers: responseHeaders } as T;
  } finally {
    clearTimeout(timer);
  }
};
