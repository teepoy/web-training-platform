/**
 * useAgentAdapter — app-level agent adapter.
 *
 * Wraps the shared useAgentCore with:
 *  - route-derived AgentContext
 *  - auth-session wiring (sessionId)
 *  - panel lifecycle (clear on navigation away from classify)
 *  - provide/inject for ClassifyView sidebar integration
 */

import {
  ref,
  computed,
  watch,
  provide,
  type InjectionKey,
  type Ref,
} from "vue";
import { useRoute } from "vue-router";
import {
  useAgentCore,
  type AgentChatStatus,
  type ChatEntry,
  type UseAgentCoreReturn,
  type UseAgentCoreOptions,
} from "@/shared";
import {
  streamGlobalAgentChat,
  type AgentPanelDescriptor,
  type AgentContext,
} from "@/shared/api/agent";
import { useAuthStore } from "../../stores/auth";

export type { AgentChatStatus, ChatEntry };

export { useAgentCore };
export type { UseAgentCoreReturn, UseAgentCoreOptions };

/** Injection key for ClassifyView to read agent panels. */
export const GLOBAL_AGENT_PANELS_KEY: InjectionKey<Ref<AgentPanelDescriptor[]>> =
  Symbol("globalAgentPanels");

/** Injection key so child views know the global agent send function. */
export const GLOBAL_AGENT_SEND_KEY: InjectionKey<
  (message: string) => Promise<void>
> = Symbol("globalAgentSend");

export interface UseAgentAdapterReturn extends UseAgentCoreReturn {
  agentPanels: Ref<AgentPanelDescriptor[]>;
}

export function useAgentAdapter(): UseAgentAdapterReturn {
  const route = useRoute();
  const authStore = useAuthStore();

  const agentPanels = ref<AgentPanelDescriptor[]>([]);

  // Derive a stable session ID from the user
  const sessionId = computed(
    () => `global-${authStore.user?.id ?? "anon"}`,
  );

  // Build context from the current route
  function buildContext(): AgentContext {
    const path = route.path;
    const params = route.params;

    const ctx: AgentContext = {
      page: path,
    };

    if (path.includes("/datasets/") && params.id) {
      ctx.dataset_id = String(params.id);
    }
    if (path.includes("/jobs/") && params.id) {
      ctx.job_id = String(params.id);
    }
    if (path.includes("/schedules/") && params.id) {
      ctx.schedule_id = String(params.id);
    }

    return ctx;
  }

  // Clear agent panels when navigating away from classify page
  watch(
    () => route.path,
    (newPath) => {
      if (!newPath.includes("/classify")) {
        agentPanels.value = [];
      }
    },
  );

  // Stream factory: bridges route/auth context into the transport
  const streamFn: UseAgentCoreOptions["stream"] = async function* (
    message,
    signal,
  ) {
    const request = {
      message,
      context: buildContext(),
      session_id: sessionId.value,
    };
    yield* streamGlobalAgentChat(request, signal);
  };

  // ── Core ──
  const core = useAgentCore({
    stream: streamFn,
    onFrame: (frame) => {
      if (frame.event === "sidebar-update") {
        const data = JSON.parse(frame.data);
        if (Array.isArray(data.panels)) {
          agentPanels.value = data.panels as AgentPanelDescriptor[];
        }
      }
    },
  });

  // Provide agent panels for child views to inject
  provide(GLOBAL_AGENT_PANELS_KEY, agentPanels);
  provide(GLOBAL_AGENT_SEND_KEY, core.send);

  return {
    ...core,
    agentPanels,
  };
}
