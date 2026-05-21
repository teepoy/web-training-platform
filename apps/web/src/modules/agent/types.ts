export interface ChatEntry {
  id: string;
  role: "user" | "assistant" | "action";
  content: string;
  tool?: string;
  timestamp: number;
}

export type AgentChatStatus = "idle" | "streaming" | "error";

export interface AgentPanelDescriptor {
  id: string;
  component: string;
  title: string;
  order: number;
  collapsed: boolean;
  size: "compact" | "normal" | "large";
  data: Record<string, unknown> | null;
  data_source: AgentDataSourceApi | AgentDataSourceContext | null;
  config: Record<string, unknown>;
  ephemeral: boolean;
  ttl: number | null;
}

export interface AgentDataSourceApi {
  kind: "api";
  endpoint: string;
  params: Record<string, string>;
  refresh_interval: number;
}

export interface AgentDataSourceContext {
  kind: "context";
  key: string;
  path: string | null;
}

export interface SurfaceLayout {
  width: number;
  position: "right" | "left";
}

export interface SurfaceStateDocument {
  version: number;
  surface_id: string;
  panels: AgentPanelDescriptor[];
  layout: SurfaceLayout;
  exported_at: string | null;
  metadata: Record<string, unknown>;
}

export interface AgentContext {
  page: string;
  dataset_id?: string | null;
  job_id?: string | null;
  schedule_id?: string | null;
  extra?: Record<string, unknown>;
}

export interface GlobalChatRequest {
  message: string;
  context: AgentContext;
  session_id?: string | null;
}

export interface SSEFrame {
  event: string;
  data: string;
}
