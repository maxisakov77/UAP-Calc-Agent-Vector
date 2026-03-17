import nextVitals from "eslint-config-next/core-web-vitals";

const config = [
  {
    ignores: [
      ".next/**",
      "coverage/**",
      "node_modules/**",
      "next-env.d.ts",
      "out/**",
      "tsconfig.tsbuildinfo",
    ],
  },
  ...nextVitals,
];

export default config;
