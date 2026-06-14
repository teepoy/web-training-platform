import type { SidebarPanelDescriptor } from "@/shared/types/components";

export const previewPanels: SidebarPanelDescriptor[] = [
  {
    id: "label-distribution",
    component: "label-distribution",
    title: "Label Distribution",
    props: { orientation: "horizontal", showValues: true, maxBars: 20 },
  },
  {
    id: "wafer-map",
    component: "wafer-map",
    title: "Wafer Map",
    order: 15,
    size: "normal",
    props: {
      data: { inline: { points: [] } },
      config: { maxPoints: 100000 },
    },
  },
  {
    id: "browser-summary",
    component: "browser-summary",
    title: "Browser Summary",
    order: 20,
    size: "compact",
    props: {},
  },
];
