import type { StorybookConfig } from "@storybook/vue3-vite";
import path from "path";

const config: StorybookConfig = {
  stories: ["../src/**/*.stories.ts"],
  addons: ["@storybook/addon-essentials"],
  framework: {
    name: "@storybook/vue3-vite",
    options: {},
  },
  docs: {
    autodocs: "tag",
  },
  async viteFinal(config) {
    const { default: vue } = await import("@vitejs/plugin-vue");

    config.plugins = config.plugins || [];
    config.plugins.unshift(vue());

    const { default: Components } = await import("unplugin-vue-components/vite");
    const { NaiveUiResolver } = await import("unplugin-vue-components/resolvers");

    config.plugins.push(
      Components({
        dts: false,
        resolvers: [NaiveUiResolver()],
      }),
    );

    config.resolve = config.resolve || {};
    config.resolve.alias = {
      ...config.resolve.alias,
      "@platform/plugin-sdk": path.resolve(__dirname, "../../plugin-sdk/src/index.ts"),
    };

    config.resolve.dedupe = [...(config.resolve.dedupe || []), "vue"];

    return config;
  },
};

export default config;
