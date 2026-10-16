/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Outfit', 'Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      colors: {
        brand: {
          50: '#EFF6FF',
          100: '#DBEAFE',
          500: '#3B82F6', // Accent blue
          600: '#2563EB',
          700: '#1D4ED8', // Primary action blue (contrast ratio >= 4.5:1 on white)
          800: '#1E40AF',
          900: '#1E3A8A',
        },
        surface: {
          white: '#FFFFFF',
          card: '#F8FAFC',
          muted: '#F1F5F9',
          border: '#E2E8F0',
          darkCard: '#1E293B',
          darkBg: '#0F172A',
          darkBorder: '#334155',
        },
        ink: {
          primary: '#0F172A',
          secondary: '#334155',
          muted: '#64748B',
          disabled: '#94A3B8',
        },
        state: {
          success: '#059669',
          successBg: '#ECFDF5',
          successBorder: '#A7F3D0',
          warning: '#D97706',
          warningBg: '#FFFBEB',
          warningBorder: '#FDE68A',
          danger: '#DC2626',
          dangerBg: '#FEF2F2',
          dangerBorder: '#FECACA',
          info: '#1D4ED8',
          infoBg: '#EFF6FF',
          infoBorder: '#BFDBFE',
        }
      },
      borderRadius: {
        'flat': '6px',
        'flat-lg': '8px',
      },
      keyframes: {
        'pulse-subtle': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.6' },
        },
        'wave-bar': {
          '0%, 100%': { height: '8px' },
          '50%': { height: '24px' },
        }
      },
      animation: {
        'pulse-subtle': 'pulse-subtle 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'wave-bar': 'wave-bar 1s ease-in-out infinite',
      }
    },
  },
  plugins: [],
}
