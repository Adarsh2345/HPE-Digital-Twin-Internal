/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#080b14',
        surface: '#0d1220',
        surface2: '#111827',
        surface3: '#151d2e',
        border: '#1e2a3f',
        accent: '#00d4aa',
        'accent-dim': 'rgba(0, 212, 170, 0.12)',
        muted: '#6b7a94',
        faint: '#3d4f6a',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
}
