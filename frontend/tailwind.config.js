import tailwindAnimate from "tailwindcss-animate";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        'quant-gold': {
          DEFAULT: '#d4af37',
          light: '#f5e3a8',
          dark: '#9a7b1d',
          glow: 'rgba(212, 175, 55, 0.4)',
        },
        'quant-black': {
          base: '#050505',
          card: '#0f0f0f',
          border: 'rgba(212, 175, 55, 0.15)',
        }
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'monospace'],
      },
      boxShadow: {
        'gold-glow': '0 0 20px rgba(212, 175, 55, 0.08)',
      }
    },
  },
  plugins: [tailwindAnimate],
}
