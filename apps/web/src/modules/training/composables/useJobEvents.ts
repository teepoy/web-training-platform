import { ref, computed, onUnmounted, onMounted, isRef, watch, type Ref, type ComputedRef } from "vue";
import { useAuthStore } from "@/modules/auth/stores/auth";
import type { TrainingEvent } from "../types";

const API_BASE = import.meta.env.VITE_API_BASE || "/api/v1";

const AUTH_RETRY_MS = 500;
const AUTH_MAX_RETRIES = 20;

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

const BACKOFF_INITIAL_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;

export type ConnectionStatus = "connecting" | "open" | "closed" | "error";

export interface JobEventsReturn {
  events: Ref<TrainingEvent[]>;
  status: Ref<ConnectionStatus>;
  latestMetrics: ComputedRef<{ epoch: number; loss: number }[]>;
  isTerminal: ComputedRef<boolean>;
  close: () => void;
}

export function useJobEvents(jobId: Ref<string> | string): JobEventsReturn {
  const events = ref<TrainingEvent[]>([]);
  const status = ref<ConnectionStatus>("connecting");

  let es: EventSource | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let authRetryTimer: ReturnType<typeof setTimeout> | null = null;
  let backoffMs = BACKOFF_INITIAL_MS;
  let authRetries = 0;
  let closed = false;
  let mounted = false;

  const latestMetrics = computed<{ epoch: number; loss: number }[]>(() =>
    events.value
      .filter((e) => e.payload.epoch !== undefined && e.payload.loss !== undefined)
      .map((e) => ({
        epoch: e.payload.epoch as number,
        loss: e.payload.loss as number,
      })),
  );

  const isTerminal = computed<boolean>(() => {
    if (events.value.length === 0) return false;
    const last = events.value[events.value.length - 1];
    const s = last.payload.status;
    return typeof s === "string" && TERMINAL_STATUSES.has(s);
  });

  function resolveJobId(): string {
    return isRef(jobId) ? jobId.value : jobId;
  }

  function clearReconnectTimer() {
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  }

  function clearAuthRetryTimer() {
    if (authRetryTimer !== null) {
      clearTimeout(authRetryTimer);
      authRetryTimer = null;
    }
  }

  function closeEs() {
    if (es !== null) {
      es.close();
      es = null;
    }
    clearReconnectTimer();
    clearAuthRetryTimer();
  }

  function close() {
    closed = true;
    closeEs();
    status.value = "closed";
  }

  function connect() {
    if (closed) return;

    const id = resolveJobId();
    if (!id) return;

    closeEs();
    status.value = "connecting";

    let token: string | null = null;
    try {
      const authStore = useAuthStore();
      token = authStore.token;
    } catch {
      /* pinia not ready */
    }

    if (!token) {
      try {
        token = localStorage.getItem("auth_token");
      } catch {
        /* localStorage not available */
      }
    }

    if (!token && authRetries < AUTH_MAX_RETRIES) {
      authRetries++;
      authRetryTimer = setTimeout(() => {
        authRetryTimer = null;
        if (!closed) {
          connect();
        }
      }, AUTH_RETRY_MS);
      return;
    }

    authRetries = 0;

    let url = `${API_BASE}/training-jobs/${encodeURIComponent(id)}/events`;
    if (token) {
      url += `?token=${encodeURIComponent(token)}`;
    }
    es = new EventSource(url);

    es.onopen = () => {
      if (closed) {
        closeEs();
        return;
      }
      status.value = "open";
      backoffMs = BACKOFF_INITIAL_MS;
    };

    es.onmessage = (evt: MessageEvent) => {
      if (closed) return;

      let parsed: TrainingEvent;
      try {
        parsed = JSON.parse(evt.data) as TrainingEvent;
      } catch {
        console.warn("[useJobEvents] malformed JSON event, skipping:", evt.data);
        return;
      }

      if (parsed.ts && events.value.some((e) => e.ts === parsed.ts)) {
        return;
      }

      events.value.push(parsed);

      if (isTerminal.value) {
        close();
      }
    };

    es.onerror = () => {
      if (closed) return;

      status.value = "error";
      closeEs();

      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        if (!closed) {
          backoffMs = Math.min(backoffMs * 2, BACKOFF_MAX_MS);
          connect();
        }
      }, backoffMs);
    };
  }

  if (isRef(jobId)) {
    watch(jobId, (newId, oldId) => {
      if (newId !== oldId && newId) {
        closed = false;
        events.value = [];
        backoffMs = BACKOFF_INITIAL_MS;
        authRetries = 0;
        if (mounted) {
          connect();
        }
      }
    });
  }

  onMounted(() => {
    mounted = true;
    connect();
  });

  onUnmounted(() => {
    close();
  });

  return { events, status, latestMetrics, isTerminal, close };
}
