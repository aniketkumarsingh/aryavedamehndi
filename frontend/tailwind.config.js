/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/pages/**/*.{js,jsx}", "./src/components/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ivory: "#F3EAD9",
        "ivory-raised": "#FBF6EC",
        ink: "#2B1712",
        "ink-soft": "#5A453D",
        line: "#E1D2B8",
        maroon: "#5C1A21",
        "maroon-soft": "#7A2A31",
        gold: "#A9761E",
        "gold-soft": "#EADFC3",
        leaf: "#4E5F3B",
        "leaf-soft": "#DCE4CC",
      },
      fontFamily: {
        display: ["var(--font-petrona)", "Georgia", "serif"],
        body: ["var(--font-manrope)", "-apple-system", "sans-serif"],
      },
      borderRadius: {
        card: "14px",
      },
    },
  },
  plugins: [],
};
