import type { Meta, StoryObj } from "@storybook/vue3";
import PanelHost from "./PanelHost.vue";
import type { SidebarPanelDescriptor } from "../../types/components";

const mockPanels: SidebarPanelDescriptor[] = [
  {
    id: "p1",
    component: "mock-stats",
    title: "Summary",
    props: { data: { count: 150 } },
    collapsed: false,
    order: 0,
  },
  {
    id: "p2",
    component: "mock-chart",
    title: "Distribution",
    props: { config: { chartType: "pie" } },
    _agentOwned: true,
  },
];

const componentResolver = () => null;

const meta = {
  title: "Shared/PanelHost",
  component: PanelHost,
  args: {
    panels: mockPanels,
    componentResolver,
  },
} satisfies Meta<typeof PanelHost>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
