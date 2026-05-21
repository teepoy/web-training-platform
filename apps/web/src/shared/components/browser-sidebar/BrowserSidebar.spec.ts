import { describe, expect, it } from "vitest";
import { defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";
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
  it("renders panel titles and widget content", () => {
    const wrapper = mount(BrowserSidebar, {
      props: {
        panels: mockPanels,
        context: mockContext,
        componentResolver,
      },
    });

    // Panel titles rendered
    expect(wrapper.text()).toContain("Summary");
    expect(wrapper.text()).toContain("Distribution");

    // Widget content present (MockWidget renders JSON of its props)
    expect(wrapper.text()).toContain('{"count":150}');
    expect(wrapper.text()).toContain('{"chartType":"pie"}');
  });

  it("hides panel content when collapsed", () => {
    const wrapper = mount(BrowserSidebar, {
      props: {
        panels: mockPanels,
        context: mockContext,
        componentResolver,
        collapsed: true,
      },
    });

    // Panel content not visible
    expect(wrapper.text()).not.toContain("Summary");
    expect(wrapper.text()).not.toContain("Distribution");

    // Expand toggle present
    const toggle = wrapper.find(".cs-header__toggle");
    expect(toggle.exists()).toBe(true);
  });

  it("shows no panels when panels array is empty", () => {
    const wrapper = mount(BrowserSidebar, {
      props: {
        panels: [],
        context: {},
      },
    });

    // No widget panels rendered
    expect(wrapper.find(".cs-panel").exists()).toBe(false);
  });

  it("adds agent-owned accent class", () => {
    const wrapper = mount(BrowserSidebar, {
      props: {
        panels: mockPanels,
        context: mockContext,
        componentResolver,
      },
    });

    // The second panel (_agentOwned: true) should have cs-panel--agent class
    const panels = wrapper.findAll(".cs-panel");
    expect(panels.length).toBe(2);

    // Agent-owned panel should have accent class
    const agentPanel = panels[1];
    expect(agentPanel.classes()).toContain("cs-panel--agent");

    // Non-agent panel should not have accent class
    const normalPanel = panels[0];
    expect(normalPanel.classes()).not.toContain("cs-panel--agent");
  });

  it("emits update:collapsed when toggle clicked", async () => {
    const wrapper = mount(BrowserSidebar, {
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

  it("delegates panel rendering to PanelHost", () => {
    const wrapper = mount(BrowserSidebar, {
      props: {
        panels: mockPanels,
        context: mockContext,
        componentResolver,
      },
    });

    // PanelHost is rendered inside BrowserSidebar
    const panelHost = wrapper.findComponent(PanelHost);
    expect(panelHost.exists()).toBe(true);

    // PanelHost receives the panels and componentResolver
    expect(panelHost.props("panels")).toEqual(mockPanels);
    expect(panelHost.props("componentResolver")).toBe(componentResolver);
  });

  it("hides PanelHost when sidebar is collapsed", () => {
    const wrapper = mount(BrowserSidebar, {
      props: {
        panels: mockPanels,
        context: mockContext,
        componentResolver,
        collapsed: true,
      },
    });

    // PanelHost should not be rendered when sidebar is collapsed
    const panelHost = wrapper.findComponent(PanelHost);
    expect(panelHost.exists()).toBe(false);

    // Toggle button still present so sidebar can be expanded
    expect(wrapper.find(".cs-header__toggle").exists()).toBe(true);
  });
});
