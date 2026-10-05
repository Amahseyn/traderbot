/** Drop uvicorn / Lab API poll noise from job log panels. */
const NOISE_LINE =
  /^\s*INFO:\s+\d{1,3}(?:\.\d{1,3}){3}:\d+\s+-\s+"(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+\//;

export function filterJobLogText(text: string): string {
  if (!text.trim()) {
    return text;
  }
  const lines = text.split("\n").filter((line) => !NOISE_LINE.test(line));
  return lines.join("\n");
}
