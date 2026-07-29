import { defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";
import type { Client, Table } from "@perspective-dev/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  useScPerspectiveWorkbench,
  type ScPerspectiveWorkbenchState,
} from "../useScPerspectiveWorkbench";

vi.mock("@perspective-dev/client", () => ({
  default: { init_client: vi.fn(), websocket: vi.fn() },
}));

function mountWorkbench(createWorkbench: () => ScPerspectiveWorkbenchState): {
  state: ScPerspectiveWorkbenchState;
  unmount: () => void;
} {
  let state: ScPerspectiveWorkbenchState | undefined;
  const wrapper = mount(
    defineComponent({
      setup() {
        state = createWorkbench();
        return () => h("div");
      },
    }),
  );
  if (!state) throw new Error("Perspective workbench test harness did not initialize");
  return { state, unmount: () => wrapper.unmount() };
}

describe("useScPerspectiveWorkbench timeouts", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("fails a websocket handshake early after the configured reconnect attempts", async () => {
    const websocket = vi.fn(() => new Promise<Client>(() => undefined));
    const harness = mountWorkbench(() =>
      useScPerspectiveWorkbench({
        websocket,
        connectionTimeoutMs: 10,
        reconnectInitialDelayMs: 1,
        reconnectMaxDelayMs: 1,
        reconnectMaxAttempts: 1,
      }),
    );

    const connectPromise = harness.state.connect({
      kind: "preview",
      inspectionTime: "2026-07-26T04:00:00+08:00",
      waferKey: 1,
    });
    await vi.advanceTimersByTimeAsync(10);
    await connectPromise;

    expect(harness.state.reconnecting.value).toBe(true);
    expect(harness.state.error.value).toContain(
      "Perspective websocket connection timed out after 10ms",
    );

    await vi.advanceTimersByTimeAsync(11);

    expect(websocket).toHaveBeenCalledTimes(2);
    expect(harness.state.reconnectFailed.value).toBe(true);
    expect(harness.state.error.value).toContain("reconnect failed after 1 attempts");
    harness.unmount();
  });

  it("terminates a websocket client that resolves after its handshake timed out", async () => {
    let resolveClient: ((client: Client) => void) | undefined;
    const terminate = vi.fn();
    const websocket = vi.fn(
      () =>
        new Promise<Client>((resolve) => {
          resolveClient = resolve;
        }),
    );
    const harness = mountWorkbench(() =>
      useScPerspectiveWorkbench({
        websocket,
        connectionTimeoutMs: 10,
        reconnectMaxAttempts: 0,
      }),
    );

    const connectPromise = harness.state.connect({
      kind: "preview",
      inspectionTime: "2026-07-26T04:00:00+08:00",
      waferKey: 1,
    });
    await vi.advanceTimersByTimeAsync(10);
    await connectPromise;

    resolveClient?.({ terminate } as unknown as Client);
    await Promise.resolve();

    expect(terminate).toHaveBeenCalledTimes(1);
    harness.unmount();
  });

  it("does not mark an empty table ready when the data deadline expires", async () => {
    const table = {
      delete: vi.fn(async () => undefined),
      size: vi.fn(async () => 0),
    } as unknown as Table;
    const client = {
      open_table: vi.fn(async () => table),
      terminate: vi.fn(),
    } as unknown as Client;
    const websocket = vi.fn(async () => client);
    const harness = mountWorkbench(() =>
      useScPerspectiveWorkbench({
        websocket,
        tableNameFactory: () => "b2ad41da-af90-4791-a453-83a77fa5e982",
        connectionTimeoutMs: 10,
        tableReadyTimeoutMs: 10,
        dataReadyTimeoutMs: 10,
        reconnectMaxAttempts: 0,
      }),
    );

    await harness.state.connect({
      kind: "preview",
      inspectionTime: "2026-07-26T04:00:00+08:00",
      waferKey: 1,
    });
    await vi.advanceTimersByTimeAsync(10);

    expect(harness.state.dataReady.value).toBe(false);
    expect(harness.state.reconnectFailed.value).toBe(true);
    expect(harness.state.error.value).toContain(
      "Perspective data did not become ready within 10ms",
    );
    expect(client.open_table).toHaveBeenCalledWith("b2ad41da-af90-4791-a453-83a77fa5e982");
    expect(websocket).toHaveBeenCalledWith(
      expect.stringContaining("table_name=b2ad41da-af90-4791-a453-83a77fa5e982"),
    );
    harness.unmount();
  });

  it("starts client probes after data becomes ready and fails a stalled connection", async () => {
    const size = vi
      .fn<() => Promise<number>>()
      .mockResolvedValueOnce(1)
      .mockImplementation(() => new Promise<number>(() => undefined));
    const table = {
      delete: vi.fn(async () => undefined),
      size,
    } as unknown as Table;
    const client = {
      open_table: vi.fn(async () => table),
      terminate: vi.fn(),
    } as unknown as Client;
    const harness = mountWorkbench(() =>
      useScPerspectiveWorkbench({
        websocket: vi.fn(async () => client),
        connectionTimeoutMs: 10,
        tableReadyTimeoutMs: 10,
        dataReadyTimeoutMs: 20,
        clientProbeIntervalMs: 5,
        clientProbeTimeoutMs: 5,
        clientProbeFailureThreshold: 1,
        reconnectMaxAttempts: 0,
        unexpectedTimeoutMs: 100,
      }),
    );

    await harness.state.connect({
      kind: "preview",
      inspectionTime: "2026-07-26T04:00:00+08:00",
      waferKey: 1,
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(harness.state.dataReady.value).toBe(true);

    await vi.advanceTimersByTimeAsync(10);

    expect(size).toHaveBeenCalledTimes(2);
    expect(harness.state.reconnectFailed.value).toBe(true);
    expect(harness.state.error.value).toContain(
      "websocket client probe timed out 1 consecutive times",
    );
    harness.unmount();
  });
});
