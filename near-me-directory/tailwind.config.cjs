/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/**/*.{astro,html,js,jsx,ts,tsx}',
    './src/pages/**/*.astro',
    './src/layouts/**/*.astro',
  ],
  theme: {
    extend: {},
  },
  plugins: [],
  // Lucide icons use currentColor and standard Tailwind classes
  // No special configuration needed for icon scaling
};