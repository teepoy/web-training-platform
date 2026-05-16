import type { Preview } from "@storybook/vue3";
import { setup } from "@storybook/vue3";
import { VueQueryPlugin, QueryClient } from "@tanstack/vue-query";
import {
  NConfigProvider,
  NMessageProvider,
  NDialogProvider,
  NNotificationProvider,
} from "naive-ui";
import { createPinia } from "pinia";

setup((app) => {
  app.use(createPinia());
  app.use(VueQueryPlugin, {
    queryClient: new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    }),
  });
});

const preview: Preview = {
  parameters: {
    backgrounds: {
      default: "dark",
      values: [
        {
          name: "dark",
          value: "#1a1a2e",
        },
      ],
    },
  },
  decorators: [
    (story) => ({
      components: {
        story,
        NConfigProvider,
        NMessageProvider,
        NDialogProvider,
        NNotificationProvider,
      },
      template:
        '<NConfigProvider><NMessageProvider><NDialogProvider><NNotificationProvider><div style="background: #1a1a2e; min-height: 100vh; padding: 16px; color: #fff; font-family: -apple-system, BlinkMacSystemFont, sans-serif;"><story /></div></NNotificationProvider></NDialogProvider></NMessageProvider></NConfigProvider>',
    }),
  ],
};

export default preview;
