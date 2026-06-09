import { describe, expect, it } from "vitest";
import { defineComponent, h } from "vue";
import { mountWithProviders } from "@/testing";
import BrowserSidebar from "./BrowserSidebar.vue";
import PanelHost from "../panel-host/PanelHost.vue";
import type { SidebarPanelDescriptor } from "../../types/components";

const MockWidget = defineComponent({
  props: ["data", "config", "size"],
  setup(props) {
    return () =>
      h(
        "div",
        { class: "mock-widget-content" },
        JSON.stringify(props.data || props.config),
      );
  },
});

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

const componentResolver = (key: string) => {
  if (key === "mock-stats" || key === "mock-chart") return MockWidget;
  return null;
};

const mockContext = { totalLoaded: 120, filteredCount: 90 };

describe("BrowserSidebar", () => {
  it("renders panel titles and widget content", async () => {
    const { wrapper } = await mountWithProviders(BrowserSidebar, {
      props: {
        panels: mockPanels,
        context: mockContext,
        componentResolver,
      },
    });

    expect(wrapper.text()).toContain("Summary");
    expect(wrapper.text()).toContain("Distribution");

    expect(wrapper.text()).toContain('{"count":150}');
    expect(wrapper.text()).toContain('{"chartType":"pie"}');
  });

  it("hides panel content when collapsed", async () => {
    const { wrapper } = await mountWithProviders(BrowserSidebar, {
      props: {
        panels: mockPanels,
        context: mockContext,
        componentResolver,
        collapsed: true,
      },
    });

    expect(wrapper.text()).not.toContain("Summary");
    expect(wrapper.text()).not.toContain("Distribution");

    const toggle = wrapper.find(".cs-header__toggle");
    expect(toggle.exists()).toBe(true);
  });

  it("shows no panels when panels array is empty", async () => {
    const { wrapper } = await mountWithProviders(BrowserSidebar, {
      props: {
        panels: [],
        context: {},
      },
    });

    expect(wrapper.find(".cs-panel").exists()).toBe(false);
  });

  it("adds agent-owned accent class", async () => {
    const { wrapper } = await mountWithProviders(BrowserSidebar, {
      props: {
        panels: mockPanels,
        context: mockContext,
        componentResolver,
      },
    });

    const panels = wrapper.findAll(".cs-panel");
    expect(panels.length).toBe(2);

    const agentPanel = panels[1];
    expect(agentPanel.classes()).toContain("cs-panel--agent");

    const normalPanel = panels[0];
    expect(normalPanel.classes()).not.toContain("cs-panel--agent");
  });

  it("emits update:collapsed when toggle clicked", async () => {
    const { wrapper } = await mountWithProviders(BrowserSidebar, {
      props: {
        panels: mockPanels,
        context: mockContext,
        componentResolver,
        collapsed: false,
      },
    });

    const toggle = wrapper.find(".cs-header__toggle");
    await toggle.trigger("click");

    expect(wrapper.emitted("update:collapsed")).toBeTruthy();
    expect(wrapper.emitted("update:collapsed")![0]).toEqual([true]);
  });

  it("delegates panel rendering to PanelHost", async () => {
    const { wrapper } = await mountWithProviders(BrowserSidebar, {
      props: {
        panels: mockPanels,
        context: mockContext,
        componentResolver,
      },
    });

    const panelHost = wrapper.findComponent(PanelHost);
    expect(panelHost.exists()).toBe(true);

    expect(panelHost.props("panels")).toEqual(mockPanels);
    expect(panelHost.props("componentResolver")).toBe(componentResolver);
  });

  it("hides PanelHost when sidebar is collapsed", async () => {
    const { wrapper } = await mountWithProviders(BrowserSidebar, {
      props: {
        panels: mockPanels,
        context: mockContext,
        componentResolver,
        collapsed: true,
      },
    });

    const panelHost = wrapper.findComponent(PanelHost);
    expect(panelHost.exists()).toBe(false);

    expect(wrapper.find(".cs-header__toggle").exists()).toBe(true);
  });
});
