export const DEFAULT_ROUGH_BIN_CODE_NAMES: Record<string, string> = Object.fromEntries(
  Array.from({ length: 61 }, (_, code) => [
    String(code),
    code === 0 ? "Unclassified" : `Rough Bin ${code}`,
  ]),
);
