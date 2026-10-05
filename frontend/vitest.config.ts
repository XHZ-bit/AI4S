import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: { maxWorkers: 1, environment: "jsdom", globals: true, setupFiles: ["./src/test-setup.ts"], testTimeout: 15000 },
});
