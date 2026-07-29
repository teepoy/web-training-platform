import { defineComponent, h, nextTick, ref, type Ref } from "vue";
import { mount, type VueWrapper } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import type { Table, View, ViewConfigUpdate } from "@perspective-dev/client";

import { useManagedPerspectiveView } from "../useManagedPerspectiveView";

class MockView {
  readonly callbacks: Array<(evt: unknown) => void> = [];
  readonly delete = vi.fn();

  constructor(
    private readonly rows: number,
    private readonly emitOnSubscribe = false,
  ) {}

  on_update(cb: (evt: unknown) => void): void {
    this.callbacks.push(cb);
    if (this.emitOnSubscribe) cb({});
  }

  async num_rows(): Promise<number> {
    return this.rows;
  }

  emitUpdate(): void {
    for (const cb of this.callbacks) cb({});
  }
}

class Deferred<T> {
  readonly promise: Promise<T>;
  private resolveValue?: (value: T) => void;

  constructor() {
    this.promise = new Promise<T>((resolve) => {
      this.resolveValue = resolve;
    });
  }

  resolve(value: T): void {
    this.resolveValue?.(value);
  }
}

function mountManagedView(
  table: Ref<Table | null>,
  config: Ref<ViewConfigUpdate>,
): {
  state: ReturnType<typeof useManagedPerspectiveView>;
  wrapper: VueWrapper;
} {
  let state: ReturnType<typeof useManagedPerspectiveView> | undefined;
  const wrapper = mount(
    defineComponent({
      setup() {
        state = useManagedPerspectiveView(table, config);
        return () => h("div");
      },
    }),
  );
  if (!state) throw new Error("composable did not mount");
  return { state, wrapper };
}

async function flushMicrotasks(): Promise<void> {
  await Promise.resolve();
  await nextTick();
}

describe("useManagedPerspectiveView", () => {
  it("publishes one immutable snapshot for a new View and its immediate update", async () => {
    const view = new MockView(12, true);
    const table = ref({
      view: vi.fn(async () => view as unknown as View),
    } as unknown as Table);
    const config = ref<ViewConfigUpdate>({ columns: ["defect_id"] });
    const { state } = mountManagedView(table, config);

    await vi.waitFor(() => {
      expect(state.snapshot.value?.view.rawView).toBe(view);
    });

    const initialSnapshot = state.snapshot.value;
    view.emitUpdate();
    await vi.waitFor(() => {
      expect(state.snapshot.value).not.toBe(initialSnapshot);
      expect(state.snapshot.value?.view.rawView).toBe(view);
    });
  });

  it("does not let an older async rebuild replace the latest view", async () => {
    const first = new Deferred<View>();
    const second = new Deferred<View>();
    const oldView = new MockView(1);
    const newView = new MockView(2);
    const table = ref({
      view: vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise),
    } as unknown as Table);
    const config = ref<ViewConfigUpdate>({ columns: ["defect_id"] });
    const { state } = mountManagedView(table, config);

    config.value = { columns: ["defect_id", "class_number"] };
    await nextTick();

    second.resolve(newView as unknown as View);
    await vi.waitFor(() => {
      expect(state.snapshot.value?.view.rawView).toBe(newView);
      expect(state.latestBuildTiming.value?.rows).toBe(2);
    });

    first.resolve(oldView as unknown as View);
    await vi.waitFor(() => {
      expect(state.snapshot.value?.view.rawView).toBe(newView);
      expect(oldView.delete).toHaveBeenCalledTimes(1);
    });
  });
});
