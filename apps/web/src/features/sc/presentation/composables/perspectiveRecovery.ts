export interface BrowserHeapSnapshot {
  usedJsHeapMb: number;
  totalJsHeapMb: number;
  jsHeapLimitMb: number;
}

export interface PerspectiveHeapLogPayload {
  scope: string;
  rows?: number | null;
  columns?: number | null;
  heap: BrowserHeapSnapshot | null;
}

interface PerformanceWithMemory extends Performance {
  memory?: {
    usedJSHeapSize: number;
    totalJSHeapSize: number;
    jsHeapSizeLimit: number;
  };
}

const RECOVERABLE_ERROR_PATTERNS = [
  /memory access out of bounds/i,
  /out of bounds memory access/i,
  /wasm.*out of bounds/i,
  /webassembly.*out of bounds/i,
  /runtimeerror/i,
  /connection.*closed/i,
  /websocket.*closed/i,
  /failed to fetch/i,
];

function bytesToMb(value: number): number {
  return Number((value / 1024 / 1024).toFixed(2));
}

export function readBrowserHeapSnapshot(): BrowserHeapSnapshot | null {
  const memory = (performance as PerformanceWithMemory).memory;
  if (!memory) return null;
  return {
    usedJsHeapMb: bytesToMb(memory.usedJSHeapSize),
    totalJsHeapMb: bytesToMb(memory.totalJSHeapSize),
    jsHeapLimitMb: bytesToMb(memory.jsHeapSizeLimit),
  };
}

export function isRecoverablePerspectiveError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return RECOVERABLE_ERROR_PATTERNS.some((pattern) => pattern.test(message));
}

export function perspectiveErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function logPerspectiveHeap(payload: PerspectiveHeapLogPayload): void {
  console.info("[sc-perspective] final client heap", payload);
}
