/** @type {import('tailwindcss').Config} */
// ── افراپیام design tokens ────────────────────────────────────────────────────
// Single source of truth for the brand palette. Change the brand color for the
// whole platform from HERE (and the matching CSS variables in src/index.css).
// Light, professional theme. Persian/RTL first.
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        // The ONLY font across the whole UI. Difference comes from size/weight/color.
        sans: ["Vazirmatn", "Tahoma", "sans-serif"],
      },
      colors: {
        // Primary brand green + interaction shades.
        brand: {
          DEFAULT: "#16A34A", // primary
          hover: "#15803D",   // hover
          active: "#166534",  // pressed
          light: "#F0FDF4",   // light green surface
          dark: "#15803D",    // back-compat alias (older code used brand-dark as hover)
        },
        // Neutrals / semantic surfaces.
        ink: "#1F2937",      // primary text
        muted: "#6B7280",    // secondary text
        line: "#E5E7EB",     // borders / dividers
        canvas: "#F8FAFC",   // page background
        surface: "#FFFFFF",  // cards / forms
      },
      borderRadius: {
        // Consistent rounded corners for buttons/cards/inputs.
        btn: "0.625rem",  // 10px
      },
      boxShadow: {
        card: "0 1px 2px 0 rgba(16, 24, 40, 0.04), 0 1px 3px 0 rgba(16, 24, 40, 0.06)",
        pop: "0 8px 24px rgba(16, 24, 40, 0.12)",
      },
    },
  },
  plugins: [],
};
