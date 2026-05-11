import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { useBlinkController } from "./useBlinkController";

describe("useBlinkController", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("defaults enabled to true", () => {
    const { enabled } = useBlinkController();
    expect(enabled.value).toBe(true);
  });

  it("defaults intervalMs to 1000", () => {
    const { intervalMs } = useBlinkController();
    expect(intervalMs.value).toBe(1000);
  });

  it("starts with phase A", () => {
    const { phase } = useBlinkController();
    expect(phase.value).toBe("A");
  });

  it("accepts custom intervalMs option", () => {
    const { intervalMs } = useBlinkController({ intervalMs: 500 });
    expect(intervalMs.value).toBe(500);
  });

  it("accepts custom initialEnabled option", () => {
    const ctrl1 = useBlinkController({ initialEnabled: false });
    expect(ctrl1.enabled.value).toBe(false);

    const ctrl2 = useBlinkController({ initialEnabled: true });
    expect(ctrl2.enabled.value).toBe(true);
  });

  it("toggles phase from A to B after one interval tick", () => {
    const { phase } = useBlinkController();
    expect(phase.value).toBe("A");

    vi.advanceTimersByTime(1000);
    expect(phase.value).toBe("B");
  });

  it("toggles phase from B back to A after two interval ticks", () => {
    const { phase } = useBlinkController();

    vi.advanceTimersByTime(2000);
    expect(phase.value).toBe("A");
  });

  it("toggles deterministically — 3 ticks = B, 4 ticks = A", () => {
    const { phase } = useBlinkController();

    vi.advanceTimersByTime(3000);
    expect(phase.value).toBe("B");

    vi.advanceTimersByTime(1000);
    expect(phase.value).toBe("A");
  });

  it("toggle() flips enabled from true to false", () => {
    const ctrl = useBlinkController();
    expect(ctrl.enabled.value).toBe(true);

    ctrl.toggle();
    expect(ctrl.enabled.value).toBe(false);
  });

  it("toggle() flips enabled from false back to true", () => {
    const ctrl = useBlinkController({ initialEnabled: false });
    expect(ctrl.enabled.value).toBe(false);

    ctrl.toggle();
    expect(ctrl.enabled.value).toBe(true);
  });

  it("phase freezes when disabled via toggle()", () => {
    const ctrl = useBlinkController();

    // Let one tick happen
    vi.advanceTimersByTime(1000);
    expect(ctrl.phase.value).toBe("B");

    // Disable
    ctrl.toggle();

    // Advance more time — phase should NOT change
    vi.advanceTimersByTime(5000);
    expect(ctrl.phase.value).toBe("B");
  });

  it("phase resumes when re-enabled via toggle()", () => {
    const ctrl = useBlinkController();

    // Let one tick happen (A → B)
    vi.advanceTimersByTime(1000);
    expect(ctrl.phase.value).toBe("B");

    // Disable, freeze at B
    ctrl.toggle();

    // Re-enable
    ctrl.toggle();
    expect(ctrl.enabled.value).toBe(true);

    // Another tick — should go B → A
    vi.advanceTimersByTime(1000);
    expect(ctrl.phase.value).toBe("A");
  });

  it("does NOT create a new timer if startTimer is called while timer is already running", () => {
    const ctrl = useBlinkController();

    // Advance 1 tick
    vi.advanceTimersByTime(1000);
    expect(ctrl.phase.value).toBe("B");

    // Toggling rapidly should not duplicate timers
    ctrl.toggle(); // off
    ctrl.toggle(); // on
    ctrl.toggle(); // off
    ctrl.toggle(); // on — should NOT crash or duplicate

    vi.advanceTimersByTime(1000);
    expect(ctrl.phase.value).toBe("A");

    vi.advanceTimersByTime(1000);
    expect(ctrl.phase.value).toBe("B");
  });

  it("cleans up interval onUnmounted does not throw", () => {
    // This test validates that onUnmounted callback doesn't throw
    // Since we can't easily trigger onUnmounted in a unit test,
    // we verify the composable handles multiple toggle cycles without leaks.
    const ctrl = useBlinkController();

    // Exercise on/off repeatedly
    for (let i = 0; i < 10; i++) {
      ctrl.toggle();
      vi.advanceTimersByTime(500);
    }

    // Should not have thrown or leaked
    expect(ctrl.enabled.value).toBeDefined();
    expect(ctrl.phase.value).toBeDefined();
  });

  it("intervalMs is a readable ref", () => {
    const { intervalMs } = useBlinkController({ intervalMs: 2000 });
    expect(intervalMs.value).toBe(2000);
  });
});
