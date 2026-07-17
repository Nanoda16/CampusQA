/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // 河海大学深水蓝 —— 单一主色，克制、学术、贴合"江河湖海"
        brand: {
          50: '#eef4fb',
          100: '#d5e3f3',
          200: '#adc7e6',
          300: '#7ea7d6',
          400: '#4f83c2',
          500: '#2c63a5',
          600: '#1f4d8a',
          700: '#183d6e',
          800: '#132f54',
          900: '#0e2440',
        },
      },
      boxShadow: {
        card: '0 1px 2px 0 rgb(15 36 64 / 0.04), 0 1px 3px 0 rgb(15 36 64 / 0.06)',
      },
      borderRadius: {
        card: '10px',
      },
    },
  },
  plugins: [],
}

