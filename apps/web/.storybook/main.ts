import type { StorybookConfig } from "@storybook/vue3-vite";
import path from "path";

const config: StorybookConfig = {
  stories: [
    "../src/shared/**/*.stories.ts",
    "../src/features/**/*.stories.ts",
  ],
  addons: ["@storybook/addon-essentials"],
  framework: {
    name: "@storybook/vue3-vite",
    options: {},
  },
  docs: {
    autodocs: "tag",
  },
  async viteFinal(config) {
    const { default: Components } = await import("unplugin-vue-components/vite");
    const { NaiveUiResolver } = await import("unplugin-vue-components/resolvers");

    config.plugins = config.plugins || [];
    config.plugins.push(
      Components({
        dts: false,
        resolvers: [NaiveUiResolver()],
      }),
    );

    config.resolve = config.resolve || {};
    config.resolve.alias = {
      ...config.resolve.alias,
      "@": path.resolve(__dirname, "../src"),
    };

    config.resolve.dedupe = [...(config.resolve.dedupe || []), "vue"];

    return config;
  },
};

export default config;
