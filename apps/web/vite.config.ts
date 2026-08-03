/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import Components from "unplugin-vue-components/vite";
import { NaiveUiResolver } from "unplugin-vue-components/resolvers";
import path from "path";
import legacy from "@vitejs/plugin-legacy";

const API_V1_PROXY_PREFIX = ["/api", "v1"].join("/");

export default defineConfig({
  plugins: [
    vue({
      template: {
        compilerOptions: {
          isCustomElement: (tag) => tag === "perspective-viewer" || tag === "sc-map",
        },
      },
    }),
    Components({ resolvers: [NaiveUiResolver()] }),
    legacy({
      modernTargets: ["chrome >= 108"],
      modernPolyfills: true,
      renderLegacyChunks: false,
    }),
  ],
  resolve: {
    alias: [
      {
        find: "@",
        replacement: path.resolve(__dirname, "src"),
      },
      {
        find: /^@platform\/sc-map-element$/,
        replacement: path.resolve(__dirname, "../../packages/sc-map-element/src/index.ts"),
      },
      {
        find: /^apache-arrow$/,
        replacement: path.resolve(__dirname, "node_modules/apache-arrow/Arrow.dom.mjs"),
      },
    ],
  },
  optimizeDeps: {
    esbuildOptions: {
      target: "esnext",
    },
    // Exclude full echarts bundle to prevent double-registration of components
    // (modular echarts/core + echarts/charts etc. are pre-bundled separately;
    // loading the full bundle on top causes registerInternalOptionCreator assertions)
    exclude: ["echarts", "@perspective-dev/viewer/inline", "@perspective-dev/client/inline"],
  },
  server: {
    port: 5173,
    proxy: {
      "/health": {
        target: process.env.VITE_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
      [`${API_V1_PROXY_PREFIX}/sc/images/`]: {
        target: process.env.VITE_IMAGE_PARSER_TARGET || "http://localhost:8090",
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/api\/v1/, ""),
      },
      [`${API_V1_PROXY_PREFIX}/sc/sprites/`]: {
        target: process.env.VITE_IMAGE_PARSER_TARGET || "http://localhost:8090",
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/api\/v1/, ""),
      },
      [`${API_V1_PROXY_PREFIX}/sc/warm/`]: {
        target: process.env.VITE_IMAGE_PARSER_TARGET || "http://localhost:8090",
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/api\/v1/, ""),
      },
      [`${API_V1_PROXY_PREFIX}/sc/perspective/`]: {
        target: process.env.VITE_PERSPECTIVE_WS_TARGET || "http://localhost:8001",
        changeOrigin: true,
        ws: true,
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
