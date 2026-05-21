export interface PreviewSession {
  session_id: string;
  collection_ref: string;
  classification_enabled: boolean;
  estimated_total: number | null;
  loaded_count: number;
  next_cursor: string | null;
  has_more: boolean;
}

export interface PreviewItem {
  upstream_item_id: string;
  image_uris: string[];
  metadata: Record<string, unknown>;
}

export interface PreviewItemsPage {
  items: PreviewItem[];
  next_cursor: string | null;
  has_more: boolean;
  estimated_total: number | null;
}

export type PreviewPersistScope = "entire_collection" | "loaded_items_only";

export interface PreviewPersistStatus {
  dataset_id: string;
  persist_session_id: string;
  status: "pending" | "running" | "completed" | "failed";
  imported_count: number;
  remaining_count: number;
  error: string | null;
}
