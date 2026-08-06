import type { Config } from 'tailwindcss';

/**
 * The palette is a dark command-centre scheme: a deep slate canvas so the
 * status colours carry all the signal, plus a red/amber/green set checked
 * for contrast against that canvas. Status is never encoded by colour
 * alone — every tile also shows its value against its target, so the
 * dashboards stay readable for colour-blind users.
 */
const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        canvas: { DEFAULT: '#0b1220', raised: '#111b2e', border: '#1e2d47' },
        ink: { DEFAULT: '#e8eef7', muted: '#93a4bd', faint: '#64748b' },
        status: {
          green: '#34d399',
          amber: '#fbbf24',
          red: '#f87171',
          unknown: '#64748b',
        },
        accent: { DEFAULT: '#38bdf8', deep: '#0ea5e9' },
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        tile: '0 1px 3px rgba(0,0,0,0.4), 0 8px 24px -12px rgba(0,0,0,0.6)',
      },
    },
  },
  plugins: [],
};
export default config;
