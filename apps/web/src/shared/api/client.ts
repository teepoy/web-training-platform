let _getToken: (() => string | null) | null = null;
let _getOrgId: (() => string | null) | null = null;
let _onAuthError: (() => void) | null = null;
let _apiBase: string = "/api/v1";
let _authEnabled: (() => boolean) | null = null;

export function configureTransport(config: {
  getToken?: () => string | null;
  getOrgId?: () => string | null;
  onAuthError?: () => void;
  apiBase?: string;
  authEnabled?: () => boolean;
}) {
  if (config.getToken !== undefined) _getToken = config.getToken;
  if (config.getOrgId !== undefined) _getOrgId = config.getOrgId;
  if (config.onAuthError !== undefined) _onAuthError = config.onAuthError;
  if (config.apiBase !== undefined) _apiBase = config.apiBase;
  if (config.authEnabled !== undefined) _authEnabled = config.authEnabled;
}

export class ApiError extends Error {
  detail: string;
  status: number;

  constructor(detail: string, status: number) {
    super(`API ${status}: ${detail}`);
    this.detail = detail;
    this.status = status;
  }
}

export const API_BASE = "/api/v1";

function resolveApiBase(): string {
  return _apiBase;
}

export async function req<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = 30_000,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const authHeader: Record<string, string> = {};
  let hasAuthToken = false;

  try {
    const token = _getToken?.() ?? null;
    if (token) {
      authHeader["Authorization"] = `Bearer ${token}`;
      hasAuthToken = true;
    }
  } catch {}

  try {
    const orgId = _getOrgId?.() ?? null;
    if (orgId) {
      authHeader["X-Organization-ID"] = orgId;
    }
  } catch {}

  try {
    const { headers: initHeaders, ...restInit } = init ?? {};
    const r = await fetch(`${resolveApiBase()}${path}`, {
      ...restInit,
      headers: {
        "Content-Type": "application/json",
        ...authHeader,
        ...((initHeaders as Record<string, string>) ?? {}),
      },
      signal: controller.signal,
    });

    if (!r.ok) {
      if (r.status === 401 && hasAuthToken && (_authEnabled?.() ?? true)) {
        try {
          _onAuthError?.();
        } catch {}
      }
      let detail = `request failed: ${r.status}`;
      try {
        const body = await r.json();
        detail =
          typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
      } catch {}
      throw new ApiError(detail, r.status);
    }

    if (r.status === 204 || r.status === 205) {
      return undefined as T;
    }
    const acceptHeader = (initHeaders as Record<string, string> | undefined)?.Accept;
    if (
      acceptHeader?.includes("application/x-protobuf") ||
      acceptHeader?.includes("application/octet-stream")
    ) {
      return r as T;
    }
    return (await r.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

export function getApiBase(): string {
  return resolveApiBase();
}

export function getAuthToken(): string | null {
  try {
    const token = _getToken?.() ?? null;
    if (token) return token;
  } catch {}

  try {
    return localStorage.getItem("auth_token");
  } catch {
    return null;
  }
}

export function getOrgId(): string | null {
  try {
    return _getOrgId?.() ?? null;
  } catch {
    return null;
  }
}

export function withAuthQueryParams(url: string): string {
  const params = new URLSearchParams();
  const token = getAuthToken();
  const orgId = getOrgId();
  if (token) params.set("token", token);
  if (orgId) params.set("org_id", orgId);
  const query = params.toString();
  if (!query) return url;

  const hashIndex = url.indexOf("#");
  const base = hashIndex >= 0 ? url.slice(0, hashIndex) : url;
  const hash = hashIndex >= 0 ? url.slice(hashIndex) : "";
  const separator = base.includes("?") ? "&" : "?";
  return `${base}${separator}${query}${hash}`;
}

export async function uploadFile<T>(path: string, form: FormData): Promise<T> {
  const headers: Record<string, string> = {};
  try {
    const token = _getToken?.() ?? null;
    if (token) headers["Authorization"] = `Bearer ${token}`;
  } catch {}
  try {
    const orgId = _getOrgId?.() ?? null;
    if (orgId) headers["X-Organization-ID"] = orgId;
  } catch {}

  const r = await fetch(`${resolveApiBase()}${path}`, {
    method: "POST",
    headers,
    body: form,
  });
  if (!r.ok) {
    let detail = `upload failed: ${r.status}`;
    try {
      const body = await r.json();
      detail =
        typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
    } catch {}
    throw new ApiError(detail, r.status);
  }
  return r.json() as Promise<T>;
}
