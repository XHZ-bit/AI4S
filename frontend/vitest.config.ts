import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    // Vitest 5 otherwise selects its silent minimal reporter inside coding agents.
    // Keep completed-file progress visible so a healthy run does not look stalled.
    reporters: process.env.GITHUB_ACTIONS === "true" ? ["default", "github-actions"] : ["default"],
    maxWorkers: 1,
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    testTimeout: 15000,
  },
});
