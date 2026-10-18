export function parseSweepValues(text: string): unknown[] {
  const values: unknown[] = [];
  for (const token of text.split(",")) {
    const cleaned = token.trim();
    if (!cleaned) continue;
    const lowered = cleaned.toLowerCase();
    if (lowered === "true" || lowered === "false") {
      values.push(lowered === "true");
      continue;
    }
    const numeric = Number(cleaned);
    values.push(Number.isNaN(numeric) ? cleaned : numeric);
  }
  return values;
}

export function prettyParamLabel(name: string): string {
  return name.replaceAll("_", " ");
}
