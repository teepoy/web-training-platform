import { defineComponent, h, nextTick, ref, type Ref } from "vue";
import { mount, type VueWrapper } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import type { Table, View, ViewConfigUpdate } from "@perspective-dev/client";

import { usePerspectiveViewRef } from "../usePerspectiveViewRef";

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

function mountViewRef(
  table: Ref<Table | null>,
  config: Ref<ViewConfigUpdate>,
  onChange = vi.fn(),
): {
  state: ReturnType<typeof usePerspectiveViewRef>;
  wrapper: VueWrapper;
  onChange: ReturnType<typeof vi.fn>;
} {
  let state: ReturnType<typeof usePerspectiveViewRef> | undefined;
  const wrapper = mount(
    defineComponent({
      setup() {
        state = usePerspectiveViewRef(table, config, { onChange });
        return () => h("div");
      },
    }),
  );
  if (!state) throw new Error("composable did not mount");
  return { state, wrapper, onChange };
}

async function flushMicrotasks(): Promise<void> {
  await Promise.resolve();
  await nextTick();
}

describe("usePerspectiveViewRef", () => {
  it("publishes the new view before accepting Perspective update callbacks", async () => {
    const view = new MockView(12, true);
    const table = ref({
      view: vi.fn(async () => view as unknown as View),
    } as unknown as Table);
    const config = ref<ViewConfigUpdate>({ columns: ["defect_id"] });
    const { state, onChange } = mountViewRef(table, config);

    await flushMicrotasks();

    expect(state.view.value).toBe(view);
    expect(state.version.value).toBe(1);
    expect(onChange).toHaveBeenCalledTimes(1);

    view.emitUpdate();
    await flushMicrotasks();

    expect(state.version.value).toBe(2);
    expect(onChange).toHaveBeenCalledTimes(2);
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
    const { state } = mountViewRef(table, config);

    config.value = { columns: ["defect_id", "class_number"] };
    await nextTick();

    second.resolve(newView as unknown as View);
    await flushMicrotasks();

    expect(state.view.value).toBe(newView);
    expect(state.latestTiming.value?.rows).toBe(2);

    first.resolve(oldView as unknown as View);
    await flushMicrotasks();
    await new Promise((resolve) => setTimeout(resolve, 25));

    expect(state.view.value).toBe(newView);
    expect(oldView.delete).toHaveBeenCalledTimes(1);
  });
});
