export interface BatchActionFailure<TItem> {
  item: TItem;
  error: unknown;
}

export interface BatchActionResult<TItem> {
  succeeded: TItem[];
  failed: BatchActionFailure<TItem>[];
}

export async function runBatchAction<TItem>(
  items: readonly TItem[],
  action: (item: TItem) => Promise<unknown>,
): Promise<BatchActionResult<TItem>> {
  const succeeded: TItem[] = [];
  const failed: BatchActionFailure<TItem>[] = [];

  for (const item of items) {
    try {
      await action(item);
      succeeded.push(item);
    } catch (error) {
      failed.push({ item, error });
    }
  }

  return { succeeded, failed };
}
