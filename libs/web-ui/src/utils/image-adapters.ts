const FALLBACK_PLACEHOLDER =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='64' height='64'%3E%3Crect width='64' height='64' fill='%23e0e0e0'/%3E%3Ctext x='50%25' y='54%25' dominant-baseline='middle' text-anchor='middle' fill='%23999' font-size='10'%3ENo img%3C/text%3E%3C/svg%3E";

function resolveImageUri(uri: string | null | undefined): string {
  if (!uri) {
    return FALLBACK_PLACEHOLDER;
  }

  if (uri.startsWith("data:") || uri.startsWith("http://") || uri.startsWith("https://")) {
    return uri;
  }

  if (uri.startsWith("s3://") || uri.startsWith("memory://")) {
    return `/api/v1/images/resolve?uri=${encodeURIComponent(uri)}`;
  }

  return FALLBACK_PLACEHOLDER;
}

export function resolveImageUris(uris: string[] | null | undefined): string[] {
  if (!uris || uris.length === 0) {
    return [FALLBACK_PLACEHOLDER];
  }

  return uris.map((uri) => resolveImageUri(uri));
}
