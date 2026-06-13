import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        page:    "#0B1628",
        card:    "#112240",
        cardhi:  "#162d50",
        ink:     "#E8F0FE",
        muted:   "#8FA3BF",
        gold:    "#E8A838",
        ok:      "#4ADE80",
        warn:    "#FBBF24",
        bad:     "#F87171",
        hblue:   "#60A5FA",
        userbg:  "#1D4ED8",
      },
      fontFamily: {
        heading: ["var(--font-heading)", "sans-serif"],
        body:    ["var(--font-body)", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
