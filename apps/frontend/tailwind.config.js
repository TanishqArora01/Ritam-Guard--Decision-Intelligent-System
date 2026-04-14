/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        'risk-low': {
          DEFAULT: '#22c55e',
          50: '#f0fdf4',
          100: '#dcfce7',
          500: '#22c55e',
          700: '#15803d',
        },
        'risk-medium': {
          DEFAULT: '#eab308',
          50: '#fefce8',
          100: '#fef9c3',
          500: '#eab308',
          700: '#a16207',
        },
        'risk-high': {
          DEFAULT: '#f97316',
          50: '#fff7ed',
          100: '#ffedd5',
          500: '#f97316',
          700: '#c2410c',
        },
        'risk-critical': {
          DEFAULT: '#ef4444',
          50: '#fef2f2',
          100: '#fee2e2',
          500: '#ef4444',
          700: '#b91c1c',
        },
        brand: {
          DEFAULT: '#6366f1',
          50: '#eef2ff',
          100: '#e0e7ff',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
        },
      },
      animation: {
        'slide-in': 'slideIn 0.3s ease-out',
        pulse: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        slideIn: {
          '0%': { opacity: '0', transform: 'translateY(-8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
