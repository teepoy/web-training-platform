import type { StorybookConfig } from "@storybook/vue3-vite";
import path from "path";

const config: StorybookConfig = {
  stories: [
    "../src/registrations/**/*.stories.ts",
    "../../../libs/web-ui/src/**/*.stories.ts",
  ],
  staticDirs: ["./public"],
  addons: ["@storybook/addon-essentials"],
  framework: {
    name: "@storybook/vue3-vite",
    options: {},
  },
  docs: {
    autodocs: "tag",
  },
  async viteFinal(config) {
    const { default: Components } =
      await import("unplugin-vue-components/vite");
    const { NaiveUiResolver } =
      await import("unplugin-vue-components/resolvers");

    config.plugins = config.plugins || [];
    config.plugins.push(
      Components({
        dts: false,
        resolvers: [NaiveUiResolver()],
      }),
    );

    config.resolve = config.resolve || {};
    const existingAliases: { find: string | RegExp; replacement: string }[] =
      Array.isArray(config.resolve.alias)
        ? config.resolve.alias
        : config.resolve.alias
          ? Object.entries(config.resolve.alias).map(
              ([find, replacement]) => ({
                find,
                replacement: replacement as string,
              }),
            )
          : [];

    config.resolve.alias = [
      ...existingAliases,
      {
        find: /^@platform\/web-data\/(.+)$/,
        replacement: path.resolve(
          __dirname,
          "../../../libs/web-data/src/$1/index.ts",
        ),
      },
      {
        find: "@platform/widget-sdk",
        replacement: path.resolve(
          __dirname,
          "../../../libs/widget-sdk/src/index.ts",
        ),
      },
      {
        find: "@platform/web-ui",
        replacement: path.resolve(
          __dirname,
          "../../../libs/web-ui/src/index.ts",
        ),
      },
      {
        find: "@platform/web-data",
        replacement: path.resolve(
          __dirname,
          "../../../libs/web-data/src/index.ts",
        ),
      },
    ];

    config.resolve.dedupe = [...(config.resolve.dedupe || []), "vue"];

    return config;
  },
};

export default config;
