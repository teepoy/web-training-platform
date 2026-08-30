const CLASS_NUMBER_MIN = 0;
const CLASS_NUMBER_MAX = 60;

export const SC_CLASS_NUMBER_DISPLAY_NAMES: Readonly<Record<string, string>> = Object.freeze(
  Object.fromEntries(
    Array.from({ length: CLASS_NUMBER_MAX - CLASS_NUMBER_MIN + 1 }, (_, offset) => {
      const classNumber = CLASS_NUMBER_MIN + offset;
      return [String(classNumber), classNumber === 0 ? "Unclassified" : `Code ${classNumber}`];
    }),
  ),
);

export function normalizeScClassNumber(value: unknown): number | null {
  const classNumber = typeof value === "number" ? value : Number(value);
  return Number.isInteger(classNumber) ? classNumber : null;
}

export function resolveScClassNumberDisplayName(value: unknown): string {
  const classNumber = normalizeScClassNumber(value);
  if (classNumber === null) return String(value);
  return SC_CLASS_NUMBER_DISPLAY_NAMES[String(classNumber)] ?? String(classNumber);
}

export function formatScClassNumber(value: unknown): string {
  const classNumber = normalizeScClassNumber(value);
  if (classNumber === null) return String(value);
  const name = SC_CLASS_NUMBER_DISPLAY_NAMES[String(classNumber)];
  return name ? `${classNumber} · ${name}` : String(classNumber);
}
