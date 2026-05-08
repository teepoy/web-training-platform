import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import Components from "unplugin-vue-components/vite";
import { NaiveUiResolver } from "unplugin-vue-components/resolvers";
import path from "path";

export default defineConfig({
  plugins: [vue(), Components({ resolvers: [NaiveUiResolver()] })],
  resolve: {
    alias: {
      "@platform/plugin-sdk": path.resolve(
        __dirname,
        "../../libs/plugin-sdk/src/index.ts",
      ),
      "@platform/web-ui": path.resolve(
        __dirname,
        "../../libs/web-ui/src/index.ts",
      ),
    },
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
