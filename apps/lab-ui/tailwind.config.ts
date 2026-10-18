import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
      },
      colors: {
        surface: "#090c11",
        panel: "#111822",
        "panel-elevated": "#161f2c",
        border: "#243044",
        "border-bright": "#334155",
        accent: "#5b9aff",
        "accent-dim": "#3b82f6",
        muted: "#8b9cb3",
      },
      boxShadow: {
        nav: "0 8px 32px -8px rgba(0, 0, 0, 0.55), 0 1px 0 0 rgba(255, 255, 255, 0.04) inset",
        card: "0 1px 0 0 rgba(255, 255, 255, 0.05) inset, 0 4px 24px -6px rgba(0, 0, 0, 0.4)",
        glow: "0 0 0 1px rgba(91, 154, 255, 0.15), 0 8px 32px -8px rgba(91, 154, 255, 0.2)",
        "glow-sm": "0 0 20px -4px rgba(91, 154, 255, 0.35)",
      },
      backgroundImage: {
        "grid-fade":
          "linear-gradient(to right, rgba(148, 163, 184, 0.04) 1px, transparent 1px), linear-gradient(to bottom, rgba(148, 163, 184, 0.04) 1px, transparent 1px)",
        "gradient-radial-accent": "radial-gradient(ellipse at top, rgba(91, 154, 255, 0.15), transparent 55%)",
        "shimmer": "linear-gradient(110deg, transparent 25%, rgba(255,255,255,0.06) 50%, transparent 75%)",
      },
      backgroundSize: {
        grid: "48px 48px",
      },
      keyframes: {
        "page-in": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "nav-glow": {
          "0%, 100%": { opacity: "0.5" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        "page-in": "page-in 0.5s cubic-bezier(0.22, 1, 0.36, 1) both",
        "nav-glow": "nav-glow 3s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
