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
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Doctus brand accent (from the Doctus Design blueprint mock) — blue and
        // indigo are unified onto the same scale since the mock uses a single
        // accent blue (#4D7FFF) wherever the app previously mixed the two.
        blue: {
          50: "#EEF3FF",
          100: "#E0E9FF",
          200: "#C2D3FF",
          300: "#9BB4FF",
          400: "#7396FF",
          500: "#4D7FFF",
          600: "#3D66E6",
          700: "#2F52C2",
          800: "#24409C",
          900: "#1D3480",
          950: "#14235B",
        },
        indigo: {
          50: "#EEF3FF",
          100: "#E0E9FF",
          200: "#C2D3FF",
          300: "#9BB4FF",
          350: "#87A5FF",
          400: "#7396FF",
          405: "#7094FF",
          500: "#4D7FFF",
          550: "#4576F5",
          600: "#3D66E6",
          650: "#3D66E6",
          655: "#2F52C2",
          700: "#2F52C2",
          750: "#2A4AB0",
          800: "#24409C",
          850: "#20398C",
          900: "#1D3480",
          950: "#14235B",
        },
        // Neutral scale re-hued to the mock's blue-gray blueprint palette,
        // anchored at bg #0B0D10 (950), surface #101319 (900), text3 #5C6675
        // (500), text2 #98A2B3 (300) and text #E9EDF4 (100).
        zinc: {
          50: "#F5F7FA",
          100: "#E9EDF4",
          150: "#DEE3EC",
          200: "#C3CAD6",
          250: "#B6BFCC",
          300: "#A9B2C0",
          350: "#8F98A8",
          400: "#7C8798",
          450: "#6C7686",
          500: "#5C6675",
          550: "#4E5765",
          600: "#3B4250",
          650: "#313847",
          700: "#262B35",
          705: "#222732",
          750: "#1E232C",
          800: "#1B1F27",
          850: "#161A21",
          900: "#101319",
          950: "#0B0D10",
        },
      },
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
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate"), require("@tailwindcss/container-queries")],
}
