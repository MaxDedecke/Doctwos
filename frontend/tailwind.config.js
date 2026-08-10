const ds = (name) => `rgb(var(--ds-${name}) / <alpha-value>)`;
const tonalScale = (shades, family) => Object.fromEntries(
  shades.map((shade) => [shade, ds(`${family}-${shade <= 300 ? "soft" : shade >= 700 ? "strong" : "base"}`)]),
);
const neutralScale = (shades) => Object.fromEntries(
  shades.map((shade) => [shade, ds(`neutral-${Math.min(950, Math.max(50, Math.round(shade / 50) * 50))}`)]),
);

/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
  ],
  prefix: "",
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    colors: {
      transparent: "transparent",
      current: "currentColor",
      inherit: "inherit",
      border: "rgb(var(--ds-border) / <alpha-value>)",
      input: "rgb(var(--ds-input) / <alpha-value>)",
      ring: "rgb(var(--ds-focus) / <alpha-value>)",
      background: "rgb(var(--ds-background) / <alpha-value>)",
      foreground: "rgb(var(--ds-foreground) / <alpha-value>)",
      primary: {
        DEFAULT: "rgb(var(--ds-accent) / <alpha-value>)",
        foreground: "rgb(var(--ds-on-accent) / <alpha-value>)",
      },
      secondary: {
        DEFAULT: "rgb(var(--ds-surface-muted) / <alpha-value>)",
        foreground: "rgb(var(--ds-foreground) / <alpha-value>)",
      },
      destructive: {
        DEFAULT: "rgb(var(--ds-danger) / <alpha-value>)",
        foreground: "rgb(var(--ds-on-danger) / <alpha-value>)",
      },
      muted: {
        DEFAULT: "rgb(var(--ds-surface-muted) / <alpha-value>)",
        foreground: "rgb(var(--ds-foreground-muted) / <alpha-value>)",
      },
      accent: {
        DEFAULT: "rgb(var(--ds-surface-muted) / <alpha-value>)",
        foreground: "rgb(var(--ds-foreground) / <alpha-value>)",
      },
      popover: {
        DEFAULT: "rgb(var(--ds-surface) / <alpha-value>)",
        foreground: "rgb(var(--ds-foreground) / <alpha-value>)",
      },
      card: {
        DEFAULT: "rgb(var(--ds-surface) / <alpha-value>)",
        foreground: "rgb(var(--ds-foreground) / <alpha-value>)",
      },
      ds: {
        white: "rgb(var(--ds-white) / <alpha-value>)",
        black: "rgb(var(--ds-black) / <alpha-value>)",
        zinc: neutralScale([50, 100, 150, 200, 250, 300, 350, 355, 400, 405, 450, 455, 500, 550, 555, 600, 605, 650, 655, 700, 750, 800, 805, 850, 855, 900, 925, 950, 955]),
        indigo: tonalScale([50, 55, 100, 200, 300, 350, 400, 405, 500, 550, 600, 650, 655, 700, 750, 800, 850, 900, 950], "accent"),
        blue: tonalScale([50, 100, 200, 300, 400, 450, 500, 600, 700, 850, 900, 950], "info"),
        emerald: tonalScale([50, 100, 200, 300, 400, 455, 500, 505, 600, 650, 700, 800, 850, 900, 950], "success"),
        green: tonalScale([500, 600, 650], "success"),
        amber: tonalScale([50, 100, 200, 300, 400, 500, 505, 600, 700, 900, 950], "warning"),
        yellow: tonalScale([500], "warning"),
        orange: tonalScale([100, 300, 400, 500, 600, 700, 900], "warning"),
        red: tonalScale([50, 200, 300, 400, 500, 600, 650, 800, 900, 950], "danger"),
        rose: tonalScale([100, 300, 400, 455, 500, 600, 700, 900, 950], "danger"),
        purple: tonalScale([50, 200, 400, 500, 600, 950], "graph-a"),
        violet: tonalScale([100, 300, 400, 500, 600, 700, 900], "graph-a"),
        pink: tonalScale([400, 650], "graph-b"),
        fuchsia: tonalScale([500], "graph-b"),
        sky: tonalScale([100, 300, 500, 700, 900], "info"),
        teal: tonalScale([500], "success"),
      },
    },
    extend: {
      /* All colors live above and resolve exclusively through --ds-* tokens. */
      fontFamily: {
        sans: ["var(--font-archivo)", "system-ui", "sans-serif"],
        heading: ["var(--font-space-grotesk)", "var(--font-archivo)", "system-ui", "sans-serif"],
        mono: ["var(--font-ibm-plex-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        // Lässt die kleinen Richtungspfeile im Quellen-Netzwerk-Graph nacheinander
        // aufblitzen und dabei minimal Richtung Doctus rutschen — mehrere Pfeile
        // mit versetztem animationDelay ergeben so einen "fließenden" Eindruck.
        "ds-arrow-pulse": {
          "0%, 100%": { opacity: "0", transform: "translate(-50%, -50%) translateX(3px)" },
          "50%": { opacity: "1", transform: "translate(-50%, -50%) translateX(-3px)" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "ds-arrow-pulse": "ds-arrow-pulse 1.6s ease-in-out infinite",
        "ds-arrow-pulse-fast": "ds-arrow-pulse 0.75s ease-in-out infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate"), require("@tailwindcss/container-queries")],
}
