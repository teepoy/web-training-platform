/**
 * Seed client factory — patches Node fetch for absolute URLs and configures
 * the shared transport with an auth token.
 *
 * Call `getSeedClient(token?)` once before using any seed helpers.
 * The returned client is thin — the real work happens via module-level
 * state in `client.ts` and the patched `globalThis.fetch`.
 */
import { configureTransport } from "../../src/shared/api/client";

const API_BASE = process.env["API_URL"] ?? "http://localhost:8000";

let _fetchPatched = false;

function ensureFetchPatched(): void {
  if (_fetchPatched) return;
  const _nativeFetch = globalThis.fetch.bind(globalThis);
  globalThis.fetch = ((input: string | URL | Request, init?: RequestInit) => {
    if (typeof input === "string" && input.startsWith("/")) {
      return _nativeFetch(`${API_BASE}${input}`, init);
    }
    return _nativeFetch(input, init);
  }) as typeof globalThis.fetch;
  _fetchPatched = true;
}

export interface SeedClient {
  /** The JWT token currently configured, if any. */
  token: string | undefined;
}

/**
 * Create a typed seed client for live-mode tests.
 *
 * - Patches `globalThis.fetch` so orval's relative URLs (`/api/v1/...`)
 *   resolve against {@link API_BASE}.
 * - Configures the shared transport with the given token.
 *
 * Call this BEFORE importing or using any other seed module.
 */
export function getSeedClient(token?: string): SeedClient {
  ensureFetchPatched();
  configureTransport({ getToken: () => token ?? null });
  return { token };
}
