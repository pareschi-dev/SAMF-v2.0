module.exports = {
  darkMode: 'class',
  content: ['./Interface_Web/backend/static/**/*.html', './Interface_Web/backend/static/**/*.js'],
  theme: {
    extend: {
      boxShadow: {
        soft: '0 10px 30px rgba(15, 23, 42, 0.08)',
      },
      colors: {
        brand: {
          50: '#f0f9ff',
          500: '#3b82f6',
          600: '#2563eb',
        },
      },
    },
  },
  plugins: [],
};
