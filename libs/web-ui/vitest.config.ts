import path from "path";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@platform/plugin-sdk": path.resolve(__dirname, "../plugin-sdk/src/index.ts"),
      "@platform/web-data": path.resolve(__dirname, "../web-data/src"),
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.spec.ts"],
  },
});
