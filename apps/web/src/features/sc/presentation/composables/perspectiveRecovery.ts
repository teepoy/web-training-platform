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

export function isRecoverablePerspectiveError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return RECOVERABLE_ERROR_PATTERNS.some((pattern) => pattern.test(message));
}

export function perspectiveErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
