/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/bubble/**/*.{html,js,py}", "./swash/**/*.{html,js,py}"],
  theme: {
    extend: {
      fontFamily: {
        serif: ["Equity OT", "Big Caslon", "Times New Roman", "serif"],
        mono: ["Iosevka Medium Extended", "monospace"],
      },
      boxShadow: {
        DEFAULT: "1px 1px 0 0 rgb(0 0 0 / 0.1)",
        md: "2px 2px 0 0 rgb(0 0 0 / 0.1)",
        lg: "4px 4px 0 0 rgb(0 0 0 / 0.1)",
        xl: "6px 6px 0 0 rgb(0 0 0 / 0.1)",
        "2xl": "8px 8px 0 0 rgb(0 0 0 / 0.1)",
        inner: "inset 1px 1px 0 0 rgb(0 0 0 / 0.1)",
        none: "none",
      },
    },
  },
  plugins: [require("@tailwindcss/forms")],
}
