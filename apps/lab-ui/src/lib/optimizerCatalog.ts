import type { DatasetRow } from "@/lib/api";
import { datasetMatchesFilters } from "@/lib/dataFilters";

export function filterOptimizerDatasets(
  datasets: DatasetRow[],
  options: { search: string; symbol: string | null; resolution: string },
): DatasetRow[] {
  return datasets.filter((dataset) =>
    datasetMatchesFilters(dataset, {
      search: options.search,
      symbol: options.symbol ?? "",
      resolution: options.resolution,
    }),
  );
}

/** Keep current selection when still visible; otherwise pick the first filtered row. */
export function resolveSingleDatasetId(filtered: DatasetRow[], currentId: string): string {
  if (filtered.length === 0) {
    return "";
  }
  if (currentId && filtered.some((row) => row.id === currentId)) {
    return currentId;
  }
  return filtered[0].id;
}

export function datasetIdsForSymbols(datasets: DatasetRow[], symbols: string[]): string[] {
  if (symbols.length === 0) {
    return [];
  }
  const set = new Set(symbols);
  return datasets.filter((row) => row.symbol && set.has(row.symbol)).map((row) => row.id);
}
