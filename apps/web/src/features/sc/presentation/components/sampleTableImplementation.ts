export type ScSampleTableImplementation = "vxe" | "tanstack";

export const SC_SAMPLE_TABLE_IMPLEMENTATION_QUERY = "sc-table";

export function resolveScSampleTableImplementation(
  search: string,
  allowComparison: boolean,
): ScSampleTableImplementation {
  if (!allowComparison) return "vxe";
  const requested = new URLSearchParams(search).get(SC_SAMPLE_TABLE_IMPLEMENTATION_QUERY);
  if (requested === null || requested === "vxe") return "vxe";
  if (requested === "tanstack") return "tanstack";
  throw new Error(
    `Unsupported ${SC_SAMPLE_TABLE_IMPLEMENTATION_QUERY} value: ${requested}. Expected vxe or tanstack.`,
  );
}
