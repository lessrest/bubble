/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./bubble/**/*.{html,js,py}"],
  theme: {
    extend: {
      fontFamily: {
        'mono': ['iosevka extended', 'monospace'],
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
  ],
}

