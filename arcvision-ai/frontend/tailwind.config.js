/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f0f5fb",
          100: "#dbe6f1",
          500: "#1f4e79",
          600: "#19416a",
          700: "#13344f",
        },
      },
      fontFamily: {
        sans: ["system-ui", "-apple-system", "Segoe UI", "Tahoma", "Arial", "sans-serif"],
      },
    },
  },
  plugins: [],
};
