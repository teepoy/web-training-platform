export class UpstreamMockError extends Error {
  constructor(
    message: string,
    readonly status: 404 | 409 | 503,
  ) {
    super(message);
  }
}

export class UpstreamMockNotFoundError extends UpstreamMockError {
  constructor(message = "inspection does not exist") {
    super(message, 404);
  }
}

export class UpstreamMockConflictError extends UpstreamMockError {
  constructor(message: string) {
    super(message, 409);
  }
}

export class UpstreamMockUnavailableError extends UpstreamMockError {
  constructor(message: string) {
    super(message, 503);
  }
}

export function isUniqueViolation(error: unknown): boolean {
  if (typeof error !== "object" || error === null) return false;
  const candidate = error as { code?: string; cause?: { code?: string } };
  return candidate.code === "23505" || candidate.cause?.code === "23505";
}
