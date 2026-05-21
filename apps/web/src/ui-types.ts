import type { components } from "./generated/openapi-types";

export interface BatchPredictionResult {
  model_id: string;
  dataset_id: string;
  total_samples: number;
  successful: number;
  failed: number;
  predictions: components["schemas"]["PredictionResultResponse"][];
  started_at: string;
  completed_at: string;
  model_version: string | null;
}


export interface AgentChatEvent {
  type: "agent-message" | "agent-action" | "sidebar-update" | "done";
}


export interface AgentMessageEvent extends AgentChatEvent {
  type: "agent-message";
  content: string;
}


export interface AgentActionEvent extends AgentChatEvent {
  type: "agent-action";
  tool: string;
  summary: string;
}


export interface AgentSidebarUpdateEvent extends AgentChatEvent {
  type: "sidebar-update";
  surface_id: string;
  panels: components["schemas"]["AgentPanelDescriptor"][];
}


export interface AgentDoneEvent extends AgentChatEvent {
  type: "done";
}


export interface MarkdownLogEntry {
  ts: string;
  level: string;
  message: string;
}


export interface MetricCardItem {
  label: string;
  value: string;
  color?: string;
}


export type TableWidgetEntity = "sample" | "prediction" | "row";


export type TableWidgetFilterMode = "all" | "selected-only";


export interface TableWidgetInteractionConfig {
  collection: string;
  entity: TableWidgetEntity;
  emitSelection?: boolean;
  followSelection?: boolean;
  filterFromSelection?: boolean;
  clearFilterOnEmptySelection?: boolean;
}


export interface TableWidgetColumn {
  key: string;
  label: string;
}


export interface TableWidgetRow {
  id: string;
  cells: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}


export interface InteractiveTableWidgetData {
  columns: TableWidgetColumn[];
  rows: TableWidgetRow[];
}
