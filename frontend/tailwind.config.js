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
          50:  '#fff7ed',
          100: '#ffedd5',
          200: '#fed7aa',
          300: '#fdba74',
          400: '#fb923c',
          500: '#f97316',
          600: '#ea580c',
          700: '#c2410c',
          800: '#9a3412',
          900: '#7c2d12',
        },
        ink: {
          50:  '#f8fafc',
          100: '#f1f5f9',
          200: '#e2e8f0',
          300: '#cbd5e1',
          400: '#94a3b8',
          500: '#64748b',
          600: '#475569',
          700: '#334155',
          800: '#1e293b',
          900: '#0f172a',
        },
      },
      fontFamily: {
        sans: ['"Inter"', '"PingFang SC"', '"Microsoft YaHei"', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'soft':  '0 4px 20px -6px rgba(15, 23, 42, 0.08)',
        'brand': '0 10px 30px -10px rgba(249, 115, 22, 0.45)',
      },
      backgroundImage: {
        'hero-glow':
          'radial-gradient(900px 500px at 50% -10%, rgba(249,115,22,0.10), transparent 60%), radial-gradient(700px 400px at 15% 30%, rgba(253,186,116,0.18), transparent 60%)',
      },
    },
  },
  plugins: [],
}
