import type { Config } from "tailwindcss";

/**
 * Design tokens are declared as CSS variables in `globals.css` and exposed here
 * as Tailwind colors. Components must reference these semantic tokens instead of
 * raw hex values or one-off Tailwind palette shades.
 */
const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      colors: {
        surface: "rgb(var(--surface) / <alpha-value>)",
        panel: "rgb(var(--panel) / <alpha-value>)",
        "panel-elevated": "rgb(var(--panel-elevated) / <alpha-value>)",
        border: "rgb(var(--border) / <alpha-value>)",
        "border-bright": "rgb(var(--border-bright) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
        "accent-dim": "rgb(var(--accent-dim) / <alpha-value>)",
        "on-accent": "rgb(var(--on-accent) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
      },
      boxShadow: {
        /* Restrained elevation: a hairline plus a soft, neutral drop. */
        card: "0 1px 2px 0 rgb(0 0 0 / 0.28)",
        overlay: "0 12px 32px -12px rgb(0 0 0 / 0.55)",
      },
      keyframes: {
        "page-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "page-in": "page-in 180ms cubic-bezier(0.22, 1, 0.36, 1) both",
      },
    },
  },
  plugins: [],
};

export default config;
