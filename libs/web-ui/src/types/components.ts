export interface TrainingEvent {
  job_id: string;
  ts: string;
  level: string;
  message: string;
  payload: Record<string, unknown>;
}

export interface RunLog {
  id: string | null;
  flow_run_id: string | null;
  level: number;
  timestamp: string;
  message: string;
}

export interface ChatEntry {
  id: string;
  role: "user" | "assistant" | "action";
  content: string;
  tool?: string;
  timestamp: number;
}

export type AgentChatStatus = "idle" | "streaming" | "error";

export interface PreviewItem {
  upstream_item_id: string;
  image_uris: string[];
  metadata: Record<string, unknown>;
}

export interface AnnotationGridItem {
  id: string;
  imageSrcs: string[];
  currentLabel: string | null;
  draftLabel: string | null;
  predictionLabel: string | null;
  predictionConfidence: number | null;
  predictionId: string | null;
  metadata: Record<string, unknown>;
}

export interface BrowserItem {
  id: string;
  imageSrcs: string[];
  metadata: Record<string, unknown>;
  sourceKind?: "dataset" | "preview" | "classify-review";
  currentLabel: string | null;
  draftLabel: string | null;
  predictionLabel: string | null;
  predictionConfidence: number | null;
  predictionId: string | null;
  activationLabel: string | null;
}

export interface SidebarPanelDescriptor {
  id: string;
  component: string;
  title: string;
  props: Record<string, unknown>;
  collapsed?: boolean;
  order?: number;
  size?: "compact" | "normal" | "large";
  _agentOwned?: boolean;
}
