let _getToken: (() => string | null) | null = null;
let _getOrgId: (() => string | null) | null = null;
let _onAuthError: (() => void) | null = null;
let _apiBase: string = "/api/v1";
let _authEnabled: (() => boolean) | null = null;

export type ApiErrorKind = "http" | "network" | "timeout";

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

export class ApiError<ErrorBody = unknown> extends Error {
  readonly cause: unknown;
  readonly kind: ApiErrorKind;
  readonly detail: string;
  readonly status: number | null;
  readonly body: ErrorBody | null;
  readonly requestId: string | null;

  constructor(options: {
    kind: ApiErrorKind;
    detail: string;
    status?: number | null;
    body?: ErrorBody | null;
    requestId?: string | null;
    cause?: unknown;
  }) {
    super(options.detail);
    this.name = "ApiError";
    this.kind = options.kind;
    this.detail = options.detail;
    this.status = options.status ?? null;
    this.body = options.body ?? null;
    this.requestId = options.requestId ?? null;
    this.cause = options.cause;
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

export function toUserMessage(error: unknown, fallback: string): string {
  if (isApiError(error)) {
    if (error.kind === "timeout") return "The request timed out. Please try again.";
    if (error.kind === "network") return "The server could not be reached. Please try again.";
    if (error.status === 401) return "Your session has expired. Please sign in again.";
    if (error.status === 403) return "You do not have permission to perform this action.";
    if (error.status === 404) return "The requested item could not be found.";
    if (error.status === 409) return "The request conflicts with the current state.";
    if (error.status === 422) return "Some request values are invalid.";
    return fallback;
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return "The request was cancelled.";
  }
  return fallback;
}

function safeGetToken(): string | null {
  try {
    return _getToken?.() ?? null;
  } catch {
    return null;
  }
}

function safeGetOrgId(): string | null {
  try {
    return _getOrgId?.() ?? null;
  } catch {
    return null;
  }
}

function buildHeaders(init: RequestInit): Headers {
  const headers = new Headers(init.headers);
  const isFormData = init.body instanceof FormData;
  if (init.body !== undefined && !isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = safeGetToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const orgId = safeGetOrgId();
  if (orgId) headers.set("X-Organization-ID", orgId);
  return headers;
}

function combineSignals(
  callerSignal: AbortSignal | null | undefined,
  timeoutSignal: AbortSignal,
): AbortSignal {
  if (!callerSignal) return timeoutSignal;
  if (typeof AbortSignal.any === "function") {
    return AbortSignal.any([callerSignal, timeoutSignal]);
  }
  const controller = new AbortController();
  const abort = (signal: AbortSignal) => {
    if (!controller.signal.aborted) controller.abort(signal.reason);
  };
  if (callerSignal.aborted) abort(callerSignal);
  else callerSignal.addEventListener("abort", () => abort(callerSignal), { once: true });
  if (timeoutSignal.aborted) abort(timeoutSignal);
  else timeoutSignal.addEventListener("abort", () => abort(timeoutSignal), { once: true });
  return controller.signal;
}

async function parseResponseBody(response: Response): Promise<unknown> {
  if (response.status === 204 || response.status === 205) return undefined;
  const contentType = response.headers.get("Content-Type") ?? "";
  if (contentType.includes("application/json")) {
    const text = await response.text();
    return text ? (JSON.parse(text) as unknown) : undefined;
  }
  if (contentType.startsWith("text/")) return response.text();
  return response.blob();
}

function errorDetail(body: unknown, status: number): string {
  if (
    typeof body === "object" &&
    body !== null &&
    "detail" in body &&
    typeof body.detail === "string"
  ) {
    return body.detail;
  }
  if (typeof body === "string" && body.trim()) return body;
  return `Request failed with status ${status}`;
}

export async function requestData<T>(
  url: string,
  init: RequestInit = {},
  timeoutMs = 30_000,
): Promise<T> {
  const response = await requestRaw(url, init, timeoutMs);
  return (await parseResponseBody(response)) as T;
}

export async function requestRaw(
  url: string,
  init: RequestInit = {},
  timeoutMs: number | null = 30_000,
): Promise<Response> {
  const timeoutSignal = timeoutMs === null ? null : AbortSignal.timeout(timeoutMs);
  const signal = timeoutSignal ? combineSignals(init.signal, timeoutSignal) : init.signal;
  const token = safeGetToken();

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: buildHeaders(init),
      signal,
    });
  } catch (error) {
    if (init.signal?.aborted) throw error;
    if (timeoutSignal?.aborted) {
      throw new ApiError({
        kind: "timeout",
        detail: "Request timed out",
        cause: error,
      });
    }
    throw new ApiError({
      kind: "network",
      detail: "Network request failed",
      cause: error,
    });
  }

  if (!response.ok) {
    const body = await parseResponseBody(response);
    if (response.status === 401 && token && (_authEnabled?.() ?? true)) {
      try {
        _onAuthError?.();
      } catch {
        // Auth cleanup must not replace the request error.
      }
    }
    throw new ApiError({
      kind: "http",
      detail: errorDetail(body, response.status),
      status: response.status,
      body,
      requestId: response.headers.get("x-request-id") ?? response.headers.get("x-correlation-id"),
    });
  }

  return response;
}

export const API_BASE = "/api/v1";

function resolveApiBase(): string {
  return _apiBase;
}

export function getApiBase(): string {
  return resolveApiBase();
}

export function getAuthToken(): string | null {
  const token = safeGetToken();
  if (token) return token;

  try {
    return localStorage.getItem("auth_token");
  } catch {
    return null;
  }
}

export function getOrgId(): string | null {
  return safeGetOrgId();
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
  return requestData<T>(`${resolveApiBase()}${path}`, {
    method: "POST",
    body: form,
  });
}
