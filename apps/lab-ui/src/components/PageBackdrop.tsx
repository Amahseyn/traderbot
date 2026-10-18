/** Ambient background — fixed, non-interactive. */
export function PageBackdrop() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden" aria-hidden>
      <div className="absolute inset-0 bg-grid-fade opacity-[0.35]" />
      <div className="absolute -left-32 top-0 h-[28rem] w-[28rem] rounded-full bg-accent/[0.07] blur-3xl" />
      <div className="absolute -right-24 top-32 h-80 w-80 rounded-full bg-indigo-500/[0.06] blur-3xl" />
      <div className="absolute bottom-0 left-1/3 h-64 w-96 rounded-full bg-cyan-500/[0.04] blur-3xl" />
    </div>
  );
}
