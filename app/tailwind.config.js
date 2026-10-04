/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0A0B10",
        surface: "#12141C",
        surface2: "#181B26",
        line: "#23263A",
        ink: "#E6E8F0",
        muted: "#9AA3B2",
        primary: { DEFAULT: "#2F7BFF", hover: "#4A8CFF", soft: "rgba(47,123,255,0.14)" },
        violet: { DEFAULT: "#8B5CF6", deep: "#7C3AED" },
        ok: "#10B981",
        warn: "#F59E0B",
        danger: "#EF4444",
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
