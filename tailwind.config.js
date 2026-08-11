/** @type {import('tailwindcss').Config} */
module.exports = {
  // Klassen-basiertes Dark Mode: ein <html class="dark"> schaltet um.
  // Der Theme-Switch (base.html) setzt diese Klasse nach localStorage/DB.
  darkMode: 'class',
  content: [
    './app/templates/**/*.html',
    './app/static/js/**/*.js',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'material-1': '0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24)',
        'material-2': '0 3px 6px rgba(0,0,0,0.16), 0 3px 6px rgba(0,0,0,0.23)',
        'material-3': '0 10px 20px rgba(0,0,0,0.19), 0 6px 6px rgba(0,0,0,0.23)',
      },
      // Semantische Design-Tokens, die in tailwind.input.css auf CSS-Variablen
      // gemappt werden. Im Hell-Modus sind die Variablen in :root belegt, im
      // Dunkel-Modus in .dark. Templates nutzen bg-surface / text-primary /
      // border-base etc. und bleiben so ohne dark:-Varianten.
      colors: {
        surface: 'rgb(var(--color-surface) / <alpha-value>)',
        'surface-subtle': 'rgb(var(--color-surface-subtle) / <alpha-value>)',
        'surface-muted': 'rgb(var(--color-surface-muted) / <alpha-value>)',
        primary: 'rgb(var(--color-primary) / <alpha-value>)',
        'primary-soft': 'rgb(var(--color-primary-soft) / <alpha-value>)',
        'primary-text': 'rgb(var(--color-primary-text) / <alpha-value>)',
        secondary: 'rgb(var(--color-secondary) / <alpha-value>)',
        'border-base': 'rgb(var(--color-border) / <alpha-value>)',
        'border-strong': 'rgb(var(--color-border-strong) / <alpha-value>)',
      },
      // borderColor erbt standardmäßig von colors, aber nur die Keys, die
      // nicht mit "border-" vorbelegt sind. Die benannten Border-Tokens
      // müssen explizit gemappt werden, damit .border-base / .border-strong
      // als Utilities generiert werden.
      borderColor: {
        base: 'rgb(var(--color-border) / <alpha-value>)',
        strong: 'rgb(var(--color-border-strong) / <alpha-value>)',
      },
    },
  },
};