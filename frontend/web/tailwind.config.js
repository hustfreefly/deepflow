/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#e8f0fe',
          100: '#d2e3fc',
          200: '#aecbfa',
          300: '#8ab4f8',
          400: '#669df6',
          500: '#1a73e8',
          600: '#1967d2',
          700: '#185abc',
          800: '#174ea6',
          900: '#155090',
        },
        surface: {
          DEFAULT: '#ffffff',
          variant: '#f8f9fa',
          inverse: '#202124',
        },
        onsurface: {
          DEFAULT: '#202124',
          variant: '#5f6368',
          inverse: '#ffffff',
        },
        outline: {
          DEFAULT: '#dadce0',
          variant: '#e8eaed',
        },
      },
      fontFamily: {
        sans: ['Roboto', 'Noto Sans SC', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        'md': '8px',
        'lg': '12px',
        'xl': '16px',
      },
    },
  },
  plugins: [],
}
