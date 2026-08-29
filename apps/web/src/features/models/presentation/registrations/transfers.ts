import { defineAsyncComponent } from "vue";
import { defineExporter, defineImporter } from "@/shared/widgets/sdk";

export const modelImporter = defineImporter({
  id: "model-artifact-v1",
  label: "Model artifact",
  labelKey: "models.importModel",
  description: "Upload an artifact for a compatible training job.",
  descriptionKey: "models.importHelp",
  icon: "⬆️",
  surfaces: ["model"],
  component: defineAsyncComponent(() => import("../components/ModelImporter.vue")),
});

export const modelExporter = defineExporter({
  id: "model-artifact-v1",
  label: "Model artifact",
  labelKey: "models.exportModel",
  description: "Download the immutable model artifact.",
  descriptionKey: "models.exportHelp",
  icon: "⬇️",
  surfaces: ["model"],
  component: defineAsyncComponent(() => import("../components/ModelExporter.vue")),
});
