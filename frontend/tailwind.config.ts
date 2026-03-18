import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          bg: "#0a0f1a",
          surface: "#111827",
          "surface-hover": "#1f2937",
          border: "#1f2937",
          "border-hover": "#374151",
          text: "#e2e8f0",
          "text-muted": "#94a3b8",
          accent: "#3b82f6",
          "accent-hover": "#2563eb",
        },
        ecosystem: {
          forest: "#1a4731",
          "forest-border": "#2d6b4f",
          swamp: "#2d3a1f",
          "swamp-border": "#4a5a2f",
          desert: "#8b7355",
          "desert-border": "#a6896a",
          seedbed: "#2d5a27",
          "seedbed-border": "#3d7a34",
          meadow: "#3d6b3d",
          "meadow-border": "#4d8b4d",
        },
        role: {
          pillar: "#22c55e",
          supporter: "#3b82f6",
          competitor: "#f97316",
          dead: "#6b7280",
        },
        severity: {
          critical: "#ef4444",
          high: "#f97316",
          medium: "#eab308",
          low: "#6b7280",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
