export interface ParsedDefectIds {
  values: number[];
  invalidCount: number;
}

function csvFields(line: string): string[] {
  const fields: string[] = [];
  let field = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const character = line[index];
    if (character === '"') {
      if (quoted && line[index + 1] === '"') {
        field += '"';
        index += 1;
      } else quoted = !quoted;
    } else if (character === "," && !quoted) {
      fields.push(field.trim());
      field = "";
    } else field += character;
  }
  fields.push(field.trim());
  return fields;
}

function normalizedHeader(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
}

function numericTokens(content: string): string[] {
  const lines = content
    .replace(/^\uFEFF/, "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) return [];

  const firstFields = csvFields(lines[0] ?? "");
  const defectIdColumn = firstFields.findIndex((field) => {
    const header = normalizedHeader(field);
    return header === "defect_id" || header === "defectid";
  });
  if (defectIdColumn >= 0) {
    return lines.slice(1).map((line) => csvFields(line)[defectIdColumn] ?? "");
  }
  return lines.flatMap((line) => line.split(/[\s,;\t]+/));
}

export function parseDefectIds(content: string): ParsedDefectIds {
  const values: number[] = [];
  const seen = new Set<number>();
  let invalidCount = 0;
  for (const token of numericTokens(content)) {
    const trimmed = token.trim();
    if (!trimmed) continue;
    const value = Number(trimmed);
    if (!Number.isSafeInteger(value)) {
      invalidCount += 1;
      continue;
    }
    if (!seen.has(value)) {
      seen.add(value);
      values.push(value);
    }
  }
  return { values, invalidCount };
}
