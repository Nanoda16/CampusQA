/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: {
          0: '#f6f2e9',
          1: '#fbf8f1',
          2: '#ffffff',
        },
        ink: {
          1: '#1c1b17',
          2: '#55504a',
          3: '#746d61',
        },
        rule: {
          DEFAULT: '#e4ddce',
          strong: '#d3c9b7',
        },
        accent: {
          DEFAULT: '#a63d2f',
          strong: '#8a3025',
          wash: '#f5e5de',
        },
        ok: { DEFAULT: '#41694f', wash: '#e6efe8' },
        warn: { DEFAULT: '#a87616', wash: '#f7efdd' },
        danger: { DEFAULT: '#a33128' },
      },
      fontFamily: {
        sans: [
          'PingFang SC',
          'HarmonyOS Sans SC',
          'Source Han Sans SC',
          'Noto Sans SC',
          'Microsoft YaHei UI',
          'Microsoft YaHei',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'sans-serif',
        ],
        mono: [
          'Cascadia Mono',
          'SF Mono',
          'JetBrains Mono',
          'Consolas',
          'ui-monospace',
          'monospace',
        ],
      },
      boxShadow: {
        r1: '0 1px 2px rgba(28,27,23,0.05), 0 1px 1px rgba(28,27,23,0.03)',
        r2: '0 1px 2px rgba(28,27,23,0.05), 0 10px 24px -14px rgba(28,27,23,0.18)',
        r3: '0 2px 4px rgba(28,27,23,0.06), 0 18px 40px -20px rgba(28,27,23,0.22)',
      },
      borderRadius: {
        r1: '4px',
        r2: '8px',
        r3: '12px',
      },
      transitionTimingFunction: {
        quiet: 'cubic-bezier(0.2, 0, 0, 1)',
      },
    },
  },
  plugins: [],
}
