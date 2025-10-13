/** @type {import('tailwindcss').Config} */
export default {
    content: [
      "./index.html",
      "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
      extend: {
        animation: {
          'pulse-light': 'pulse-light 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
          'slide-up': 'slide-up 0.3s ease-out',
        },
        keyframes: {
          'pulse-light': {
            '0%, 100%': { opacity: 1 },
            '50%': { opacity: 0.5 },
          },
          'slide-up': {
            from: { opacity: 0, transform: 'translateY(10px)' },
            to: { opacity: 1, transform: 'translateY(0)' },
          },
          'gradient-glow': {
            '0%': { backgroundPosition: '0% 50%' },
            '50%': { backgroundPosition: '100% 50%' },
            '100%': { backgroundPosition: '0% 50%' },
          },
          'pulse-shadow': {
            '0%, 100%': {
              boxShadow: '0 0 0 0 rgba(251, 146, 60, 0.7)',
            },
            '70%': {
              boxShadow: '0 0 0 8px rgba(251, 146, 60, 0)',
            },
          },
          'border-glow': {
            '0%, 100%': {
              boxShadow: '0 0 6px 0px var(--glow-color)',
            },
            '50%': {
              boxShadow: '0 0 12px 2px var(--glow-color)',
            },
          },
        },
        animation: {
          'gradient-glow': 'gradient-glow 3s ease-in-out infinite',
          'pulse-shadow': 'pulse-shadow 2s infinite',
          'border-glow': 'border-glow 2.5s ease-in-out infinite',
        },
      },
    },
    plugins: [],
  }