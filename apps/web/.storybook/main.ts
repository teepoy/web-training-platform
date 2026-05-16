import type { StorybookConfig } from "@storybook/vue3-vite";
import path from "path";

const config: StorybookConfig = {
  stories: [
    "../../../libs/web-ui/src/**/*.stories.ts",
    "../src/**/*.stories.ts",
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
      "@platform/widget-sdk": path.resolve(__dirname, "../../../libs/widget-sdk/src/index.ts"),
      "@platform/web-ui": path.resolve(__dirname, "../../../libs/web-ui/src/index.ts"),
    };

    config.resolve.dedupe = [...(config.resolve.dedupe || []), "vue"];

    return config;
  },
};

export default config;
