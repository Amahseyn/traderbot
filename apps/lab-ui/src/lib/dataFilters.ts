import type { DatasetRow } from "@/lib/api";

export type MarketScope = "default_jobs" | "nobitex_all";

export function marketMatchesSearch(
  market: { symbol: string; label: string; src: string; dst: string },
  needle: string,
): boolean {
  if (!needle) {
    return true;
  }
  const lower = needle.toLowerCase();
  return (
    market.symbol.toLowerCase().includes(lower) ||
    market.label.toLowerCase().includes(lower) ||
    market.src.toLowerCase().includes(lower) ||
    market.dst.toLowerCase().includes(lower)
  );
}

export function datasetMatchesFilters(
  dataset: DatasetRow,
  options: { search: string; symbol: string; resolution: string },
): boolean {
  const search = options.search.trim().toLowerCase();
  if (search) {
    const haystack = [
      dataset.id,
      dataset.label,
      dataset.symbol ?? "",
      dataset.resolution ?? "",
      dataset.source,
      dataset.repo_path ?? "",
    ]
      .join(" ")
      .toLowerCase();
    if (!haystack.includes(search)) {
      return false;
    }
  }
  if (options.symbol && (dataset.symbol ?? "") !== options.symbol) {
    return false;
  }
  if (options.resolution && (dataset.resolution ?? "") !== options.resolution) {
    return false;
  }
  return true;
}

export function uniqueDatasetSymbols(datasets: DatasetRow[]): string[] {
  const symbols = new Set<string>();
  for (const dataset of datasets) {
    if (dataset.symbol) {
      symbols.add(dataset.symbol);
    }
  }
  return [...symbols].sort();
}

export function uniqueDatasetResolutions(datasets: DatasetRow[]): string[] {
  const resolutions = new Set<string>();
  for (const dataset of datasets) {
    if (dataset.resolution) {
      resolutions.add(dataset.resolution);
    }
  }
  return [...resolutions].sort();
}
