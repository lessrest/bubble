/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./bubble/**/*.{html,js,py}"],
  theme: {
    extend: {
      fontFamily: {
        serif: ["Equity OT", "Big Caslon", "Times New Roman", "serif"],
        mono: ["Iosevka Medium Extended", "monospace"],
      },
    },
  },
  plugins: [require("@tailwindcss/forms")],
}
