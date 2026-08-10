import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent } from "vue";

import { mountWithProviders } from "@/testing";
import { configureTransport } from "@/shared/api/client";
import type { TrainingEvent } from "@/shared/types/components";

import { useJobEvents, type JobEventsReturn } from "./useJobEvents";

class FakeEventSource {
  static instance: FakeEventSource | null = null;

  readonly url: string;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  closed = false;
  private readonly listeners = new Map<string, Array<(event: Event) => void>>();

  constructor(url: string | URL) {
    this.url = String(url);
    FakeEventSource.instance = this;
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    const callback =
      typeof listener === "function" ? listener : (event: Event) => listener.handleEvent(event);
    const listeners = this.listeners.get(type) ?? [];
    listeners.push(callback);
    this.listeners.set(type, listeners);
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, event: TrainingEvent): void {
    const message = new MessageEvent(type, { data: JSON.stringify(event) });
    for (const listener of this.listeners.get(type) ?? []) {
      listener(message);
    }
  }
}

describe("useJobEvents", () => {
  beforeEach(() => {
    localStorage.setItem("auth_token", "test-token");
    localStorage.setItem("current_org_id", "org-1");
    configureTransport({ getOrgId: () => "org-1" });
    vi.stubGlobal("EventSource", FakeEventSource);
  });

  afterEach(() => {
    localStorage.clear();
    configureTransport({ getOrgId: () => null });
    FakeEventSource.instance = null;
    vi.unstubAllGlobals();
  });

  it("receives named epoch events and closes on a terminal status", async () => {
    let state: JobEventsReturn | undefined;
    const Host = defineComponent({
      setup() {
        state = useJobEvents("job-1");
        return () => null;
      },
    });

    const { wrapper } = await mountWithProviders(Host);
    await flushPromises();
    const source = FakeEventSource.instance;
    expect(source?.url).toContain("/training-jobs/job-1/events?token=test-token&org_id=org-1");

    source?.emit("epoch", {
      job_id: "job-1",
      ts: "2026-08-10T10:00:00Z",
      level: "epoch",
      message: "epoch 1/50 completed",
      payload: { epoch: 1, total_epochs: 50, loss: 0.5 },
    });
    expect(state?.events.value).toHaveLength(1);

    source?.emit("status", {
      job_id: "job-1",
      ts: "2026-08-10T10:01:00Z",
      level: "info",
      message: "training completed",
      payload: { status: "completed" },
    });
    expect(state?.events.value).toHaveLength(2);
    expect(source?.closed).toBe(true);
    expect(state?.status.value).toBe("closed");

    wrapper.unmount();
  });
});
