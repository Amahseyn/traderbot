"use client";

import { useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/Field";
import {
  filterStrategies,
  selectionCountLabel,
  strategyStyleLabel,
  strategyStyles,
  toggleStyle,
  type StrategyLike,
} from "@/lib/strategySelection";

export type StrategyMultiSelectRow = StrategyLike & { id: string };

type StrategyMultiSelectProps = {
  strategies: StrategyMultiSelectRow[];
  enabledIds: Set<string>;
  /** Toggle a single strategy on/off. */
  onToggle: (id: string) => void;
  /** Add every id in `ids` to the selection (union — never drops existing picks). */
  onAddIds: (ids: string[]) => void;
  /** Clear the whole selection. */
  onClear: () => void;
};

function styleChipClass(active: boolean): string {
  return `rounded-full border px-2.5 py-1 text-xs transition duration-150 ${
    active
      ? "border-accent/60 bg-accent/15 text-white"
      : "border-border/80 bg-panel-elevated/60 text-slate-300 hover:border-accent/40 hover:text-white"
  }`;
}

/**
 * Searchable, style-filtered multi-strategy picker for Custom Research step 2.
 *
 * Shows the current selection as removable chips, lets users narrow the catalog
 * by free text and style, and select the visible rows in one click.
 */
export function StrategyMultiSelect({
  strategies,
  enabledIds,
  onToggle,
  onAddIds,
  onClear,
}: StrategyMultiSelectProps) {
  const [query, setQuery] = useState("");
  const [activeStyles, setActiveStyles] = useState<string[]>([]);

  const styles = useMemo(() => strategyStyles(strategies), [strategies]);
  const visible = useMemo(
    () => filterStrategies(strategies, { query, styles: activeStyles }),
    [strategies, query, activeStyles],
  );
  const selectedRows = useMemo(
    () => strategies.filter((strategy) => enabledIds.has(strategy.id)),
    [strategies, enabledIds],
  );
  const visibleIds = useMemo(() => visible.map((strategy) => strategy.id), [visible]);
  const allVisibleSelected =
    visible.length > 0 && visible.every((strategy) => enabledIds.has(strategy.id));
  const filtersActive = query.trim().length > 0 || activeStyles.length > 0;

  return (
    <div className="space-y-3 rounded-xl border border-border/80 bg-surface/60 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-muted">Multi-strategy</span>
        <span className="badge badge-strategy">{selectionCountLabel(enabledIds.size, strategies.length)}</span>
      </div>

      {selectedRows.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          {selectedRows.map((strategy) => (
            <button
              key={strategy.id}
              type="button"
              onClick={() => onToggle(strategy.id)}
              title={`Remove ${strategy.name || strategy.id}`}
              className="group inline-flex items-center gap-1 rounded-full border border-accent/30 bg-accent/10 px-2.5 py-1 text-xs text-slate-100 transition hover:border-accent/60 hover:bg-accent/20"
            >
              <span className="max-w-[12rem] truncate">{strategy.name || strategy.id}</span>
              <span aria-hidden className="text-muted group-hover:text-white">
                ×
              </span>
            </button>
          ))}
          <button
            type="button"
            onClick={onClear}
            className="rounded-full px-2 py-1 text-xs text-muted transition hover:text-accent hover:underline"
          >
            Clear all
          </button>
        </div>
      ) : (
        <p className="text-xs text-muted">
          No strategies selected yet — tick one below, or use “Select shown”.
        </p>
      )}

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <TextInput
          type="search"
          value={query}
          placeholder="Search by name, id, or style…"
          aria-label="Search strategies"
          onChange={(event) => setQuery(event.target.value)}
          className="sm:flex-1"
        />
        <div className="flex shrink-0 gap-2">
          <Button
            type="button"
            variant="secondary"
            onClick={() => onAddIds(visibleIds)}
            disabled={visibleIds.length === 0 || allVisibleSelected}
            title="Add every strategy currently shown"
          >
            {filtersActive ? "Select shown" : "Select all"} ({visible.length})
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={onClear}
            disabled={enabledIds.size === 0}
          >
            Clear
          </Button>
        </div>
      </div>

      {styles.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-muted">Style</span>
          <button
            type="button"
            aria-pressed={activeStyles.length === 0}
            onClick={() => setActiveStyles([])}
            className={styleChipClass(activeStyles.length === 0)}
          >
            Any
          </button>
          {styles.map((style) => {
            const active = activeStyles.includes(style);
            return (
              <button
                key={style}
                type="button"
                aria-pressed={active}
                onClick={() => setActiveStyles((previous) => toggleStyle(previous, style))}
                className={styleChipClass(active)}
              >
                {strategyStyleLabel(style)}
              </button>
            );
          })}
        </div>
      )}

      <div className="max-h-72 space-y-1 overflow-y-auto rounded-lg border border-border/70 bg-panel/60 p-1.5">
        {visible.length === 0 ? (
          <p className="px-2 py-6 text-center text-xs text-muted">
            No strategies match your filters.
          </p>
        ) : (
          visible.map((strategy) => {
            const checked = enabledIds.has(strategy.id);
            return (
              <label
                key={strategy.id}
                className={`flex cursor-pointer items-start gap-2.5 rounded-lg px-2.5 py-2 text-sm transition ${
                  checked ? "bg-accent/[0.08]" : "hover:bg-panel-elevated/70"
                }`}
              >
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={checked}
                  onChange={() => onToggle(strategy.id)}
                />
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="text-slate-100">{strategy.name || strategy.id}</span>
                    {strategy.style && (
                      <span className="rounded-md bg-white/5 px-1.5 py-0.5 text-[10px] font-medium text-slate-300 ring-1 ring-white/10">
                        {strategyStyleLabel(strategy.style)}
                      </span>
                    )}
                  </span>
                  {strategy.summary && (
                    <span className="mt-0.5 block truncate text-xs text-muted">{strategy.summary}</span>
                  )}
                </span>
              </label>
            );
          })
        )}
      </div>

      <p className="text-xs leading-relaxed text-muted">
        Selected strategies run as one comparison batch. Use “Max strategies” to cap how many run
        (catalog order).
      </p>
    </div>
  );
}
