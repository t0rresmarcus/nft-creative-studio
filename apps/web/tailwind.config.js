/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0c0c0b",
        panel: "#161614",
        line: "rgba(244,239,230,0.12)",
        paper: "#f4efe6",
        mute: "#a39e93",
        lime: "#d6ff3f",
        ember: "#ff5a36",
      },
      fontFamily: {
        serif: ["var(--font-serif)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui"],
      },
      boxShadow: {
        card: "0 20px 60px rgba(0,0,0,0.35)",
      },
    },
  },
  plugins: [],
};
