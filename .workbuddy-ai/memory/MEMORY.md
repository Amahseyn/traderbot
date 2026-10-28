# Project memory — traderbot

## Lab UI design system (2026-10-25)

- **Source of truth:** `apps/lab-ui/design-system/traderbot-lab/MASTER.md`. Read before changing
  layout, colour, or component styling.
- **Tokens:** defined as CSS variables in `apps/lab-ui/src/app/globals.css` and exposed in
  `tailwind.config.ts` via `rgb(var(--x) / <alpha-value>)`. Components must not use raw hex.
- **Semantics:** blue `#5B9AFF` is the only interaction accent. Green/red are reserved for PnL and
  status — never decorative. Primary buttons use `text-on-accent` on `bg-accent` (white on accent
  fails AA at 2.8:1).
- **Forbidden:** gradient backgrounds/text, glow shadows, decorative `backdrop-blur`, `blur-3xl`
  ambient blobs, hover lift/scale, hover-only affordances, per-card rainbow accents, emoji icons.
- **Motion:** 150 ms colour/border transitions; global `prefers-reduced-motion` block in
  `globals.css`.
- **UI/UX skill:** `.workbuddy-ai/skills/ui-ux-pro-max/` — `python3 scripts/search.py "<query>"
  --domain ux|style|chart|...` or `--stack nextjs|react`. Full clone OOMs; use
  `--filter=blob:none --sparse` + `git sparse-checkout set src`.

## Build caveat (this machine)

`next build` cannot complete under the sandbox: the safe-delete shim aborts on `.next` cleanup and
the brokered-fs shim rejects Next's `mkdir`. An aborted build leaves the dev server returning 500 —
recover by stopping dev, moving `.next` aside, and restarting `next dev`. Verify with
`tsc --noEmit`, the Tailwind CLI, and HTTP checks against the dev server instead.
