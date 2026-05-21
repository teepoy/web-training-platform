export type ImageAdapter = (uri: string) => string | null;

interface AdapterEntry {
  name: string;
  adapter: ImageAdapter;
}

const adapters: AdapterEntry[] = [];

export const FALLBACK_PLACEHOLDER =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='64' height='64'%3E%3Crect width='64' height='64' fill='%23e0e0e0'/%3E%3Ctext x='50%25' y='54%25' dominant-baseline='middle' text-anchor='middle' fill='%23999' font-size='10'%3ENo img%3C/text%3E%3C/svg%3E";

export function registerImageAdapter(name: string, adapter: ImageAdapter): void {
  const idx = adapters.findIndex((e) => e.name === name);
  if (idx !== -1) {
    adapters[idx] = { name, adapter };
  } else {
    adapters.push({ name, adapter });
  }
}

export function unregisterImageAdapter(name: string): boolean {
  const idx = adapters.findIndex((e) => e.name === name);
  if (idx === -1) return false;
  adapters.splice(idx, 1);
  return true;
}

export function listImageAdapters(): string[] {
  return adapters.map((e) => e.name);
}

export function resolveImageUri(uri: string | null | undefined): string {
  if (!uri) return FALLBACK_PLACEHOLDER;

  for (const { adapter } of adapters) {
    const result = adapter(uri);
    if (result !== null) return result;
  }

  return FALLBACK_PLACEHOLDER;
}

export function resolveImageUris(uris: string[] | null | undefined): string[] {
  if (!uris || uris.length === 0) return [FALLBACK_PLACEHOLDER];
  return uris.map((u) => resolveImageUri(u));
}

registerImageAdapter("data-uri", (uri) => (uri.startsWith("data:") ? uri : null));
registerImageAdapter("http", (uri) =>
  uri.startsWith("http://") || uri.startsWith("https://") ? uri : null,
);
registerImageAdapter("proxy", (uri) =>
  uri.startsWith("s3://") || uri.startsWith("memory://")
    ? `/api/v1/images/resolve?uri=${encodeURIComponent(uri)}`
    : null,
);
