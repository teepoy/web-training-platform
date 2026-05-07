import { defineAsyncComponent } from "vue"
import { definePreviewPlugin } from "@platform/plugin-sdk"

export const upstreamPreviewPlugin = definePreviewPlugin({
  id: "preview-upstream",
  label: "Upstream Collection",
  description: "Browse a remote collection without importing it first.",
  icon: "🔍",
  surfaces: ["dataset-list", "preview"],
  component: defineAsyncComponent(() => import("./UpstreamPreviewLauncher.vue")),
})