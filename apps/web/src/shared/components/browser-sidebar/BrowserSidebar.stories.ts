import type { Meta, StoryObj } from "@storybook/vue3";
import { defineComponent } from "vue";
import BrowserSidebar from "./BrowserSidebar.vue";
import type { SidebarPanelDescriptor } from "../../types/components";

const MockWidget = defineComponent({
  props: { data: Object, config: Object, size: String },
  template: `<div style="padding:8px;color:#ccc;font-size:12px">{{ JSON.stringify(data || config) }}</div>`,
});

const mockPanels: SidebarPanelDescriptor[] = [
  { id: "p1", component: "mock-stats", title: "Summary", props: { data: { count: 150 } }, collapsed: false, order: 0 },
  { id: "p2", component: "mock-chart", title: "Distribution", props: { config: { chartType: "pie" } }, _agentOwned: true },
];

const componentResolver = (key: string) => {
  if (key === "mock-stats" || key === "mock-chart") return MockWidget;
  return null;
};

const mockContext = { totalLoaded: 120, filteredCount: 90 };

const meta = {
  title: "web-ui/components/BrowserSidebar",
  component: BrowserSidebar,
} satisfies Meta<typeof BrowserSidebar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    collapsed: false,
    panels: mockPanels,
    componentResolver,
    context: mockContext,
  },
};

export const Collapsed: Story = {
  args: {
    collapsed: true,
    panels: mockPanels,
    componentResolver,
    context: mockContext,
  },
};

export const EmptyPanels: Story = {
  args: {
    panels: [],
    context: {},
  },
};
