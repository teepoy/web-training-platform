import { ref, onUnmounted, type Ref } from "vue";
import type { BlinkPhase } from "../types/blink-table";

export interface UseBlinkControllerOptions {
  intervalMs?: number;
  initialEnabled?: boolean;
}

export interface UseBlinkControllerReturn {
  enabled: Ref<boolean>;
  phase: Ref<BlinkPhase>;
  toggle: () => void;
  intervalMs: Ref<number>;
}

export function useBlinkController(
  options?: UseBlinkControllerOptions,
): UseBlinkControllerReturn {
  const enabled = ref(options?.initialEnabled ?? true);
  const phase = ref<BlinkPhase>("A");
  const intervalMs = ref(options?.intervalMs ?? 1000);

  let timer: ReturnType<typeof setInterval> | null = null;

  function startTimer(): void {
    if (timer !== null) return;
    timer = setInterval(() => {
      phase.value = phase.value === "A" ? "B" : "A";
    }, intervalMs.value);
  }

  function stopTimer(): void {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  }

  function toggle(): void {
    enabled.value = !enabled.value;
    if (enabled.value) {
      startTimer();
    } else {
      stopTimer();
    }
  }

  if (enabled.value) {
    startTimer();
  }

  onUnmounted(() => {
    stopTimer();
  });

  return { enabled, phase, toggle, intervalMs };
}
