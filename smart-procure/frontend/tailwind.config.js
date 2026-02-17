/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          500: "#10b981",
          600: "#059669",
          700: "#047857",
        },
      },
      borderRadius: {
        md: "var(--sp-radius-md)",
        lg: "var(--sp-radius-lg)",
      },
      boxShadow: {
        panel: "var(--sp-shadow-sm)",
      },
    },
  },
  plugins: [],
}
