export type PipelineLibraryState = {
  activeIds: string[];
  titles: Record<string, string>;
};

const STORAGE_KEY = "traderbot.lab.pipelines";

export const DEFAULT_ACTIVE_PIPELINE_IDS = ["full-research-strategies"];

export function loadPipelineLibrary(): PipelineLibraryState {
  if (typeof window === "undefined") {
    return { activeIds: [...DEFAULT_ACTIVE_PIPELINE_IDS], titles: {} };
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { activeIds: [...DEFAULT_ACTIVE_PIPELINE_IDS], titles: {} };
    const parsed = JSON.parse(raw) as Partial<PipelineLibraryState>;
    const activeIds = Array.isArray(parsed.activeIds)
      ? parsed.activeIds.filter((id): id is string => typeof id === "string")
      : [...DEFAULT_ACTIVE_PIPELINE_IDS];
    const titles =
      parsed.titles && typeof parsed.titles === "object"
        ? Object.fromEntries(
            Object.entries(parsed.titles).filter(
              (entry): entry is [string, string] => typeof entry[1] === "string" && entry[1].trim().length > 0,
            ),
          )
        : {};
    return { activeIds, titles };
  } catch {
    return { activeIds: [...DEFAULT_ACTIVE_PIPELINE_IDS], titles: {} };
  }
}

export function savePipelineLibrary(state: PipelineLibraryState): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}
