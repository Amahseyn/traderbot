/** Matches `traderbot.discovery.run.DEFAULT_RESOLUTIONS`. */
export const HYPERLIQUID_DISCOVERY_RESOLUTIONS = ["5", "15", "60", "240", "D"] as const;

export type DiscoveryDataSource = "coinbeacon" | "hyperliquid";

export function parseSymbolList(raw: string): string[] {
  return raw
    .split(/[\s,]+/)
    .map((part) => part.trim().toLowerCase())
    .filter((part) => part.length > 0);
}
