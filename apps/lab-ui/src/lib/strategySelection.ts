/**
 * Pure helpers for the Custom Research strategy multi-selector.
 *
 * Kept free of React/DOM so the filtering/grouping rules are unit-testable and
 * shared between the picker UI and the page (e.g. "select all filtered").
 */

/** Minimal shape accepted by the helpers (structurally matches CatalogStrategy). */
export type StrategyLike = {
  id: string;
  name?: string | null;
  style?: string | null;
  summary?: string | null;
};

/** Human-readable labels for registry strategy styles. */
export const STRATEGY_STYLE_LABELS: Record<string, string> = {
  trend: "Trend",
  mean_reversion: "Mean reversion",
  pattern: "Pattern",
  breakout: "Breakout",
  grid: "Grid",
  pair: "Pairs",
  carry: "Carry",
  market_making: "Market making",
  swing: "Swing",
  scalping: "Scalping",
  accumulation: "Accumulation",
  range: "Range",
  event: "Event",
  ml: "ML",
  meta: "Meta",
  portfolio: "Portfolio",
};

/** Preferred style-filter order; unknown styles follow, alphabetically. */
export const STRATEGY_STYLE_ORDER: readonly string[] = [
  "trend",
  "mean_reversion",
  "breakout",
  "range",
  "pattern",
  "swing",
  "scalping",
  "grid",
  "pair",
  "carry",
  "market_making",
  "accumulation",
  "event",
  "ml",
  "meta",
  "portfolio",
];

function normalizeStyle(style: string | null | undefined): string {
  return (style ?? "").trim().toLowerCase();
}

/** Display label for a raw style value; falls back to Title Case of the token. */
export function strategyStyleLabel(style: string | null | undefined): string {
  const key = normalizeStyle(style);
  if (!key) {
    return "Other";
  }
  if (STRATEGY_STYLE_LABELS[key]) {
    return STRATEGY_STYLE_LABELS[key];
  }
  return key
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

/** Ordered unique styles present in a catalog. */
export function strategyStyles(strategies: readonly StrategyLike[]): string[] {
  const present = new Set<string>();
  for (const strategy of strategies) {
    const style = normalizeStyle(strategy.style);
    if (style) {
      present.add(style);
    }
  }
  const ordered = STRATEGY_STYLE_ORDER.filter((style) => present.has(style));
  const extras = [...present].filter((style) => !STRATEGY_STYLE_ORDER.includes(style)).sort();
  return [...ordered, ...extras];
}

export type StrategyFilter = {
  query: string;
  styles: readonly string[];
};

/** True when a strategy matches the free-text query (id, name, summary, style label). */
export function strategyMatchesQuery(strategy: StrategyLike, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  const haystack = [
    strategy.id,
    strategy.name ?? "",
    strategy.summary ?? "",
    strategyStyleLabel(strategy.style),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(needle);
}

/** Filter the catalog by query and an optional set of styles (empty = all styles). */
export function filterStrategies<T extends StrategyLike>(
  strategies: readonly T[],
  filter: StrategyFilter,
): T[] {
  const wanted = new Set(filter.styles.map((style) => normalizeStyle(style)).filter(Boolean));
  return strategies.filter((strategy) => {
    if (wanted.size > 0 && !wanted.has(normalizeStyle(strategy.style))) {
      return false;
    }
    return strategyMatchesQuery(strategy, filter.query);
  });
}

/** Toggle a style in the active filter list (returns a new array). */
export function toggleStyle(styles: readonly string[], style: string): string[] {
  const key = normalizeStyle(style);
  if (!key) {
    return [...styles];
  }
  return styles.includes(key) ? styles.filter((item) => item !== key) : [...styles, key];
}

/** Human label for the selected count, e.g. "3 of 18 selected". */
export function selectionCountLabel(enabled: number, total: number): string {
  return `${enabled} of ${total} selected`;
}

/** Ids of every strategy that is currently visible under the filter. */
export function visibleStrategyIds<T extends StrategyLike>(
  strategies: readonly T[],
  filter: StrategyFilter,
): string[] {
  return filterStrategies(strategies, filter).map((strategy) => strategy.id);
}
