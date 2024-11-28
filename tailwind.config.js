/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./bubble/**/*.{html,js,py}"],
  theme: {
    extend: {
      fontFamily: {
        serif: ["Equity OT", "Times New Roman", "serif"],
        sans: ["Iosevka Aile", "sans-serif"],
        mono: ["Iosevka Medium Extended", "monospace"],
      },
    },
  },
  plugins: [require("@tailwindcss/forms")],
};
