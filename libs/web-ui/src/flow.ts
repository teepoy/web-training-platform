import type { Component } from "vue";

export type FlowKind = "import" | "export" | "preview";

export interface FlowCard {
  id: string;
  label: string;
  description?: string;
  icon?: string;
  component: Component;
}
