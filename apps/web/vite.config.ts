/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import Components from "unplugin-vue-components/vite";
import { NaiveUiResolver } from "unplugin-vue-components/resolvers";
import path from "path";
import legacy from "@vitejs/plugin-legacy";

export default defineConfig({
  plugins: [
    vue(),
    Components({ resolvers: [NaiveUiResolver()] }),
    legacy({
      targets: ["chrome >= 108", "not IE 11"],
    }),
  ],
  build: {
    target: "chrome108",
  },
  resolve: {
    alias: [
      {
        find: "@",
        replacement: path.resolve(__dirname, "src"),
      },
    ],
  },
  optimizeDeps: {
    // Exclude full echarts bundle to prevent double-registration of components
    // (modular echarts/core + echarts/charts etc. are pre-bundled separately;
    // loading the full bundle on top causes registerInternalOptionCreator assertions)
    exclude: ["echarts"],
  },
  server: {
    port: 5173,
    proxy: {
      "/health": {
        target: process.env.VITE_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
      "/api/v1/sc/images/": { // ast-grep-ignore: forbid-raw-api-url
        target: process.env.VITE_IMAGE_PARSER_TARGET || "http://localhost:8090",
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/api\/v1/, ""),
      },
      "/api/v1/sc/sprites/": { // ast-grep-ignore: forbid-raw-api-url
        target: process.env.VITE_IMAGE_PARSER_TARGET || "http://localhost:8090",
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/api\/v1/, ""),
      },
      "/api/v1/sc/warm/": { // ast-grep-ignore: forbid-raw-api-url
        target: process.env.VITE_IMAGE_PARSER_TARGET || "http://localhost:8090",
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/api\/v1/, ""),
      },
      "/api": {
        target: process.env.VITE_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: ["src/testing/setup.ts"],
    exclude: ["tests/**", "node_modules/**"],
  },
});
