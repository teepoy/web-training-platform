import type { Meta, StoryObj } from "@storybook/vue3";
import ClassifySidebar from "./ClassifySidebar.vue";
import type { SidebarPanelDescriptor } from "../../config";

const defaultPanels: SidebarPanelDescriptor[] = [
  {
    id: "annotation-progress",
    component: "annotation-progress",
    title: "Annotation Progress",
    props: {},
  },
  {
    id: "label-distribution",
    component: "label-distribution",
    title: "Label Distribution",
    props: {},
  },
];

const meta = {
  component: ClassifySidebar,
  title: "Classify/ClassifySidebar",
  parameters: {
    backgrounds: { default: "light" },
  },
} satisfies Meta<typeof ClassifySidebar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    panels: defaultPanels,
    context: { datasetId: "mock-dataset-1" },
    collapsed: false,
  },
};
