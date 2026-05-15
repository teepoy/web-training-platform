import path from "path";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@platform/widget-sdk": path.resolve(__dirname, "../widget-sdk/src/index.ts"),
      "@platform/web-ui": path.resolve(__dirname, "../../libs/web-ui/src"),
      "@platform/web-data": path.resolve(__dirname, "../../libs/web-ui/src/api"),
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.spec.ts"],
  },
});
