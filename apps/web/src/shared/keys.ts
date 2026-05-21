import type { InjectionKey, Ref } from "vue";
import type { AgentPanelDescriptor } from "./api/types";

export const GLOBAL_AGENT_PANELS_KEY: InjectionKey<Ref<AgentPanelDescriptor[]>> =
  Symbol("globalAgentPanels");
