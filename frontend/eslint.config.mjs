import nextCoreWebVitals from "eslint-config-next/core-web-vitals";

const eslintConfig = [...nextCoreWebVitals, {
  files: ["**/*.ts", "**/*.tsx"],
  rules: {
    "no-restricted-syntax": ["error", {
      selector: "TSAnyKeyword",
      message: "Use a shared domain/API type, or narrow unknown data at the boundary (O-063).",
    }],
  },
}];

export default eslintConfig;
