/** @type {import('tailwindcss').Config} */
const color = (name) => `rgb(var(--c-${name}) / <alpha-value>)`;
const size = (rem, lineHeight) => [`calc(${rem}rem * var(--text-scale))`, `calc(${lineHeight}rem * var(--text-scale))`];

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: color("bg"),
        surface: color("surface"),
        surface2: color("surface2"),
        line: color("line"),
        ink: color("ink"),
        muted: color("muted"),
        primary: { DEFAULT: color("primary"), hover: color("primary-hover"), soft: "rgb(var(--c-primary) / 0.14)" },
        violet: { DEFAULT: color("violet"), deep: color("violet-deep") },
        ok: color("ok"),
        warn: color("warn"),
        danger: color("danger"),
      },
      fontSize: {
        "3xs": size(0.625, 0.875),
        "2xs": size(0.6875, 1),
        xs: size(0.75, 1),
        sm: size(0.875, 1.25),
        base: size(1, 1.5),
        lg: size(1.125, 1.75),
        xl: size(1.25, 1.75),
        "2xl": size(1.5, 2),
        "3xl": size(1.875, 2.25),
        "4xl": size(2.25, 2.5),
      },
      fontFamily: {
        sans: ["Inter", "IBM Plex Sans Arabic", "system-ui", "sans-serif"],
        arabic: ["IBM Plex Sans Arabic", "Inter", "system-ui", "sans-serif"],
      },
      backgroundImage: {
        brand: "linear-gradient(90deg, #2F7BFF 0%, #8B5CF6 100%)",
        "brand-soft": "linear-gradient(135deg, rgba(47,123,255,0.18), rgba(139,92,246,0.14))",
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(47,123,255,0.35), 0 8px 30px rgba(47,123,255,0.15)",
      },
    },
  },
  plugins: [],
};
