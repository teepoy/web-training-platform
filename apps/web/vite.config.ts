import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import Components from "unplugin-vue-components/vite";
import { NaiveUiResolver } from "unplugin-vue-components/resolvers";
import path from "path";

export default defineConfig({
  plugins: [vue(), Components({ resolvers: [NaiveUiResolver()] })],
  resolve: {
    alias: [
      {
        find: /^@platform\/web-data\/(.+)$/,
        replacement: path.resolve(__dirname, "../../libs/web-data/src/$1/index.ts"),
      },
      {
        find: "@platform/web-data",
        replacement: path.resolve(__dirname, "../../libs/web-data/src/index.ts"),
      },
      {
        find: "@platform/widget-sdk",
        replacement: path.resolve(__dirname, "../../libs/widget-sdk/src/index.ts"),
      },
      {
        find: /^@platform\/web-ui\/(.+)$/,
        replacement: path.resolve(__dirname, "../../libs/web-ui/src/$1"),
      },
      {
        find: "@platform/web-ui",
        replacement: path.resolve(__dirname, "../../libs/web-ui/src/index.ts"),
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
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
