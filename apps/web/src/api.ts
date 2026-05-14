import type { ApiError as ApiErrorType } from "./types";
import { getStoredToken, useAuthStore } from "./stores/auth";

export const API_BASE = import.meta.env.VITE_API_BASE || "/api/v1";
export const HEALTH_URL = import.meta.env.VITE_HEALTH_URL || "/api/v1/health";

// ---------------------------------------------------------------------------
// Typed error class
// ---------------------------------------------------------------------------

export class ApiError extends Error implements ApiErrorType {
  detail: string;
  status: number;

  constructor(detail: string, status: number) {
    super(`API ${status}: ${detail}`);
    this.detail = detail;
    this.status = status;
  }
}

function getAuthContext(): { token: string | null; authEnabled: boolean } {
  try {
    const authStore = useAuthStore();
    const authEnabled = authStore.authEnabled;
    return {
      token: authEnabled ? (authStore.token ?? getStoredToken()) : null,
      authEnabled,
    };
  } catch {
    return {
      token: getStoredToken(),
      authEnabled: true,
    };
  }
}

// ---------------------------------------------------------------------------
// SSE helpers
// ---------------------------------------------------------------------------

export function buildJobEventSource(jobId: string): EventSource {
  let tokenParam = "";
  try {
    const { token } = getAuthContext();
    if (token) {
      tokenParam = `?token=${encodeURIComponent(token)}`;
    }
  } catch {
    /* ignore */
  }
  return new EventSource(
    `${API_BASE}/training-jobs/${jobId}/events${tokenParam}`,
  );
}

export function buildTrackedTaskEventSource(taskId: string): EventSource {
  let tokenParam = "";
  try {
    const { token } = getAuthContext();
    if (token) {
      tokenParam = `?token=${encodeURIComponent(token)}`;
    }
  } catch {
    /* ignore */
  }
  return new EventSource(
    `${API_BASE}/task-tracker/tasks/${taskId}/stream${tokenParam}`,
  );
}
