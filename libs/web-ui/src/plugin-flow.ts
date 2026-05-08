import type { Component } from "vue";

export type PluginKind = "import" | "export" | "preview";

export interface PluginCard {
  id: string;
  label: string;
  description?: string;
  icon?: string;
  component: Component;
}
