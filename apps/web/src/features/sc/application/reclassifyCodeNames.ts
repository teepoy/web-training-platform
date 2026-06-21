export const DEFAULT_RECLASSIFY_CODE_NAMES: Record<string, string> =
  Object.fromEntries(
    Array.from({ length: 61 }, (_, code) => [
      String(code),
      code === 0 ? "Unclassified" : `Code ${code}`,
    ]),
  );
