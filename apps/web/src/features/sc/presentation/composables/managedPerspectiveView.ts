import type { Table, View } from "@perspective-dev/client";

export type ManagedPerspectiveResourceStatus = "active" | "retiring" | "deleted";

export interface ManagedPerspectiveView {
  readonly rawView: View;
  readonly status: ManagedPerspectiveResourceStatus;
  readonly pendingOperations: number;
  num_rows: () => Promise<number>;
  to_columns: (options?: unknown) => Promise<unknown>;
  to_json: (options?: unknown) => Promise<unknown>;
  to_arrow: (options?: unknown) => Promise<unknown>;
  onUpdateDebounced: (
    callback: (event: unknown) => void,
    options?: { waitMs?: number; shouldRun?: (event: unknown) => boolean },
  ) => void;
  retire: () => void;
}

export interface ManagedPerspectiveTable {
  readonly rawTable: Table;
  readonly status: ManagedPerspectiveResourceStatus;
  readonly pendingOperations: number;
  readonly views: ReadonlySet<ManagedPerspectiveView>;
  size: () => Promise<number>;
  view: (config?: unknown) => Promise<ManagedPerspectiveView>;
  update: (data: unknown, options?: unknown) => Promise<void>;
  make_port: () => Promise<number>;
  retire: (options?: { onDeleted?: () => void }) => void;
}

const managedViews = new WeakMap<View, ManagedPerspectiveViewImpl>();
const managedTables = new WeakMap<Table, ManagedPerspectiveTableImpl>();
const DEFAULT_UPDATE_DEBOUNCE_MS = 80;
const RETIRE_RETRY_MS = 50;
const RETIRE_SETTLE_MS = 16;
const VIEW_RETIRE_MAX_RETRIES = 50;
const TABLE_RETIRE_RETRY_MS = 100;
const TABLE_RETIRE_MAX_RETRIES = 50;

class ManagedPerspectiveViewImpl implements ManagedPerspectiveView {
  readonly rawView: View;
  private _status: ManagedPerspectiveResourceStatus = "active";
  private _pendingOperations = 0;
  private _retireTimer: ReturnType<typeof setTimeout> | null = null;
  private _retireRetries = 0;

  constructor(
    view: View,
    private readonly owner?: ManagedPerspectiveTableImpl,
  ) {
    this.rawView = view;
  }

  get status(): ManagedPerspectiveResourceStatus {
    return this._status;
  }

  get pendingOperations(): number {
    return this._pendingOperations;
  }

  async num_rows(): Promise<number> {
    return this.runWithLock((view) => view.num_rows());
  }

  async to_columns(options?: unknown): Promise<unknown> {
    return this.runWithLock((view) => view.to_columns(options as never));
  }

  async to_json(options?: unknown): Promise<unknown> {
    return this.runWithLock((view) => view.to_json(options as never));
  }

  async to_arrow(options?: unknown): Promise<unknown> {
    return this.runWithLock((view) => view.to_arrow(options as never));
  }

  onUpdateDebounced(
    callback: (event: unknown) => void,
    options: { waitMs?: number; shouldRun?: (event: unknown) => boolean } = {},
  ): void {
    const waitMs = options.waitMs ?? DEFAULT_UPDATE_DEBOUNCE_MS;
    let latestEvent: unknown;
    let timer: ReturnType<typeof setTimeout> | null = null;

    this.rawView.on_update((event: unknown) => {
      if (this._status !== "active" || options.shouldRun?.(event) === false) return;
      latestEvent = event;
      if (timer !== null) clearTimeout(timer);
      timer = setTimeout(() => {
        timer = null;
        if (this._status !== "active") return;
        callback(latestEvent);
      }, waitMs);
    });
  }

  retire(): void {
    if (this._status === "deleted") return;
    this._status = "retiring";
    this.scheduleDelete();
  }

  private async runWithLock<T>(operation: (view: View) => Promise<T>): Promise<T> {
    if (this._status === "deleted") {
      throw new Error("Perspective view has already been deleted");
    }
    this._pendingOperations += 1;
    try {
      return await operation(this.rawView);
    } finally {
      this._pendingOperations -= 1;
      if (this._status === "retiring") this.scheduleDelete();
    }
  }

  private scheduleDelete(): void {
    if (this._retireTimer !== null || this._status === "deleted") return;
    const delay = this._pendingOperations > 0 ? RETIRE_RETRY_MS : RETIRE_SETTLE_MS;
    this._retireTimer = setTimeout(async () => {
      this._retireTimer = null;
      if (this._status === "deleted") return;
      if (this._pendingOperations > 0) {
        this.scheduleDelete();
        return;
      }
      try {
        await this.rawView.delete();
      } catch {
        if (this._retireRetries < VIEW_RETIRE_MAX_RETRIES) {
          this._retireRetries += 1;
          this.scheduleDelete();
          return;
        }
      }
      this._status = "deleted";
      this.owner?.notifyViewDeleted(this);
    }, delay);
  }
}

class ManagedPerspectiveTableImpl implements ManagedPerspectiveTable {
  readonly rawTable: Table;
  private _status: ManagedPerspectiveResourceStatus = "active";
  private _pendingOperations = 0;
  private _retireTimer: ReturnType<typeof setTimeout> | null = null;
  private _retireRetries = 0;
  private _onDeleted: (() => void) | undefined;
  private readonly _views = new Set<ManagedPerspectiveViewImpl>();

  constructor(table: Table) {
    this.rawTable = table;
  }

  get status(): ManagedPerspectiveResourceStatus {
    return this._status;
  }

  get pendingOperations(): number {
    return this._pendingOperations;
  }

  get views(): ReadonlySet<ManagedPerspectiveView> {
    return this._views;
  }

  async size(): Promise<number> {
    return this.runWithLock((table) => table.size());
  }

  async view(config?: unknown): Promise<ManagedPerspectiveView> {
    if (this._status === "deleted") {
      throw new Error("Perspective table has already been deleted");
    }
    this._pendingOperations += 1;
    try {
      const view = await this.rawTable.view(config as never);
      return this.trackView(view);
    } finally {
      this._pendingOperations -= 1;
      if (this._status === "retiring") this.scheduleDelete();
    }
  }

  async update(data: unknown, options?: unknown): Promise<void> {
    await this.runWithLock((table) => table.update(data as never, options as never));
  }

  async make_port(): Promise<number> {
    return this.runWithLock((table) => table.make_port());
  }

  trackView(view: View): ManagedPerspectiveView {
    const existing = managedViews.get(view);
    if (existing) {
      this._views.add(existing);
      return existing;
    }
    const managed = new ManagedPerspectiveViewImpl(view, this);
    managedViews.set(view, managed);
    this._views.add(managed);
    return managed;
  }

  notifyViewDeleted(view: ManagedPerspectiveViewImpl): void {
    this._views.delete(view);
    if (this._status === "retiring") this.scheduleDelete();
  }

  retire(options: { onDeleted?: () => void } = {}): void {
    if (options.onDeleted) this._onDeleted = options.onDeleted;
    if (this._status === "deleted") {
      this._onDeleted?.();
      return;
    }
    this._status = "retiring";
    for (const view of this._views) view.retire();
    this.scheduleDelete();
  }

  private async runWithLock<T>(operation: (table: Table) => Promise<T>): Promise<T> {
    if (this._status === "deleted") {
      throw new Error("Perspective table has already been deleted");
    }
    this._pendingOperations += 1;
    try {
      return await operation(this.rawTable);
    } finally {
      this._pendingOperations -= 1;
      if (this._status === "retiring") this.scheduleDelete();
    }
  }

  private canDelete(): boolean {
    if (this._pendingOperations > 0) return false;
    for (const view of this._views) {
      if (view.status !== "deleted" || view.pendingOperations > 0) return false;
    }
    return true;
  }

  private scheduleDelete(): void {
    if (this._retireTimer !== null || this._status === "deleted") return;
    this._retireTimer = setTimeout(async () => {
      this._retireTimer = null;
      if (this._status === "deleted") return;
      if (!this.canDelete()) {
        this.scheduleDelete();
        return;
      }
      try {
        await this.rawTable.delete();
      } catch {
        if (this._retireRetries < TABLE_RETIRE_MAX_RETRIES) {
          this._retireRetries += 1;
          this.scheduleDelete();
          return;
        }
      }
      this._status = "deleted";
      this._views.clear();
      this._onDeleted?.();
    }, TABLE_RETIRE_RETRY_MS);
  }
}

export function managePerspectiveTable(table: Table): ManagedPerspectiveTable {
  const existing = managedTables.get(table);
  if (existing) return existing;
  const managed = new ManagedPerspectiveTableImpl(table);
  managedTables.set(table, managed);
  return managed;
}

export function managePerspectiveView(
  view: View,
  table?: Table | ManagedPerspectiveTable,
): ManagedPerspectiveView {
  if (table) {
    const managedTable =
      table instanceof ManagedPerspectiveTableImpl
        ? table
        : (managePerspectiveTable(table as Table) as ManagedPerspectiveTableImpl);
    return managedTable.trackView(view);
  }
  const existing = managedViews.get(view);
  if (existing) return existing;
  const managed = new ManagedPerspectiveViewImpl(view);
  managedViews.set(view, managed);
  return managed;
}

export function retirePerspectiveView(view: View | null | undefined): void {
  if (!view) return;
  managePerspectiveView(view).retire();
}
