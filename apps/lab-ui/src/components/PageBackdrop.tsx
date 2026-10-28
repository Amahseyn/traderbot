/**
 * Canvas background — fixed, non-interactive.
 *
 * Clean, solid carbon surface without decorative AI graph grids or glowing blobs.
 */
export function PageBackdrop() {
  return <div className="pointer-events-none fixed inset-0 -z-10 bg-surface" aria-hidden />;
}

