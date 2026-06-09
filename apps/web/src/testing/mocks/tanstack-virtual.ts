import { vi } from "vitest";

// vi.mock calls are hoisted by vitest to execute before any test code.
// Importing this module applies the mock; call mockTanstackVirtual() as an
// explicit opt-in marker at the top of your spec file.
vi.mock("@tanstack/vue-virtual", () => ({
  useVirtualizer: (
    options: {
      count: (() => number) | number;
      estimateSize: (() => number) | number;
    },
  ) => {
    const count =
      typeof options.count === "function"
        ? options.count()
        : options.count;
    const size =
      typeof options.estimateSize === "function"
        ? options.estimateSize()
        : options.estimateSize;

    const inner = {
      getVirtualItems: () =>
        Array.from({ length: count }, (_, i) => ({
          index: i,
          size,
          start: i * size,
        })),
      getTotalSize: () => count * size,
      measure: vi.fn(),
      scrollToIndex: vi.fn(),
    };

    return {
      value: inner,
      getVirtualItems: inner.getVirtualItems,
      getTotalSize: inner.getTotalSize,
      measure: inner.measure,
      scrollToIndex: inner.scrollToIndex,
    };
  },
}));

/** Opt-in marker — call at top of spec to explicitly apply tanstack-virtual mocks. */
export function mockTanstackVirtual(): void {
  // vi.mock call above is hoisted by vitest; this function is a no-op
  // that signals intent to human readers and linters.
}
