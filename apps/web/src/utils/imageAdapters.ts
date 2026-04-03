/**
 * Image URI adapter registry.
 *
 * Built-in adapters handle `data:` URIs (HuggingFace datasets base64 format)
 * and `http(s)://` URLs. Users can register custom adapters for other URI
 * schemes (e.g. `s3://`, `gs://`, custom CDN patterns).
 *
 * Usage:
 *   import { resolveImageUri, registerImageAdapter } from '@/utils/imageAdapters'
 *
 *   // Use built-in adapters
 *   const src = resolveImageUri(sample.image_uri)
 *
 *   // Register a custom adapter
 *   registerImageAdapter('s3', (uri) => {
 *     if (!uri.startsWith('s3://')) return null
 *     return `https://my-cdn.example.com/${uri.slice(5)}`
 *   })
 */

/** An adapter receives a raw URI string and returns a renderable `src` or `null` to skip. */
export type ImageAdapter = (uri: string) => string | null;

interface AdapterEntry {
  name: string;
  adapter: ImageAdapter;
}

// ---------------------------------------------------------------------------
// Registry (ordered — first non-null wins)
// ---------------------------------------------------------------------------
const adapters: AdapterEntry[] = [];

/**
 * Register a custom image adapter.
 *
 * @param name   Unique name for the adapter (replaces if already registered).
 * @param adapter  Function that returns a renderable `src` string, or `null` to pass.
 */
export function registerImageAdapter(name: string, adapter: ImageAdapter): void {
  const idx = adapters.findIndex((e) => e.name === name);
  if (idx !== -1) {
    adapters[idx] = { name, adapter };
  } else {
    adapters.push({ name, adapter });
  }
}

/**
 * Remove a previously registered adapter by name.
 */
export function unregisterImageAdapter(name: string): boolean {
  const idx = adapters.findIndex((e) => e.name === name);
  if (idx === -1) return false;
  adapters.splice(idx, 1);
  return true;
}

/**
 * Return the list of registered adapter names (in evaluation order).
 */
export function listImageAdapters(): string[] {
  return adapters.map((e) => e.name);
}

// ---------------------------------------------------------------------------
// Resolver
// ---------------------------------------------------------------------------

/** Placeholder returned when no adapter matches. */
const FALLBACK_PLACEHOLDER =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='64' height='64'%3E%3Crect width='64' height='64' fill='%23e0e0e0'/%3E%3Ctext x='50%25' y='54%25' dominant-baseline='middle' text-anchor='middle' fill='%23999' font-size='10'%3ENo img%3C/text%3E%3C/svg%3E";

/**
 * Resolve a raw image URI to a renderable `src` string.
 *
 * Iterates through registered adapters in order. The first adapter that
 * returns a non-null value wins. If no adapter matches, returns a grey
 * placeholder SVG.
 */
export function resolveImageUri(uri: string | null | undefined): string {
  if (!uri) return FALLBACK_PLACEHOLDER;

  for (const { adapter } of adapters) {
    const result = adapter(uri);
    if (result !== null) return result;
  }

  return FALLBACK_PLACEHOLDER;
}

// ---------------------------------------------------------------------------
// Built-in adapters
// ---------------------------------------------------------------------------

/** Pass through `data:` URIs (base64 images from HuggingFace datasets, etc.). */
const dataUriAdapter: ImageAdapter = (uri) => {
  if (uri.startsWith("data:")) return uri;
  return null;
};

/** Pass through `http://` and `https://` URLs. */
const httpAdapter: ImageAdapter = (uri) => {
  if (uri.startsWith("http://") || uri.startsWith("https://")) return uri;
  return null;
};

// Register built-ins on module load
registerImageAdapter("data-uri", dataUriAdapter);
registerImageAdapter("http", httpAdapter);

// ---------------------------------------------------------------------------
// Proxy adapter — routes storage URIs through the backend resolver
// ---------------------------------------------------------------------------

/** Proxy `s3://` and `memory://` URIs through the backend image resolver. */
const proxyAdapter: ImageAdapter = (uri) => {
  if (uri.startsWith("s3://") || uri.startsWith("memory://")) {
    return `/api/v1/images/resolve?uri=${encodeURIComponent(uri)}`;
  }
  return null;
};
registerImageAdapter("proxy", proxyAdapter);

// ---------------------------------------------------------------------------
// Multi-URI helper
// ---------------------------------------------------------------------------

/**
 * Resolve an array of image URIs. Returns resolved `src` strings.
 * Empty/null input returns an array with just the fallback placeholder.
 */
export function resolveImageUris(uris: string[] | null | undefined): string[] {
  if (!uris || uris.length === 0) return [FALLBACK_PLACEHOLDER];
  return uris.map((u) => resolveImageUri(u));
}
