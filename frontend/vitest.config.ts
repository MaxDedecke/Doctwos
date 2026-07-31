import path from "path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
    // e2e/ is Playwright's domain (run via `npm run test:e2e`), not Vitest's.
    exclude: ["**/node_modules/**", "e2e/**"],
  },
});
