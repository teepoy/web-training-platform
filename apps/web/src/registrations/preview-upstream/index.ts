import { defineAsyncComponent } from "vue"
import { definePreviewLauncher } from "@platform/widget-sdk"

export const upstreamPreviewPlugin = definePreviewLauncher({
  id: "preview-upstream",
  label: "Upstream Collection",
  description: "Browse a remote collection without importing it first.",
  icon: "🔍",
  surfaces: ["dataset-list", "preview"],
  component: defineAsyncComponent(() => import("./UpstreamPreviewLauncher.vue")),
})
