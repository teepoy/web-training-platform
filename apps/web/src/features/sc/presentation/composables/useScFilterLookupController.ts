import { ref } from "vue";

export interface ScFilterLookupPayload {
  field: string;
  itemId?: string;
}

export function useScFilterLookupController() {
  const distinctValues = ref<Record<string, Array<string | number>>>({});
  const numericRanges = ref<Record<string, { min: number; max: number } | null>>({});
  const numericRangeLoading = ref<Record<string, boolean>>({});
  const numericRangeErrors = ref<Record<string, boolean>>({});
  const distinctVersions = new Map<string, number>();
  const rangeVersions = new Map<string, number>();

  async function searchDistinct(
    payload: { field: string; search: string },
    load: () => Promise<Array<string | number>>,
    onError?: (error: unknown) => void,
  ): Promise<void> {
    const version = (distinctVersions.get(payload.field) ?? 0) + 1;
    distinctVersions.set(payload.field, version);
    try {
      const values = await load();
      if (distinctVersions.get(payload.field) !== version) return;
      distinctValues.value = { ...distinctValues.value, [payload.field]: values };
    } catch (error) {
      if (distinctVersions.get(payload.field) === version) onError?.(error);
    }
  }

  async function requestRange(
    payload: ScFilterLookupPayload,
    load: () => Promise<{ min: number; max: number } | null>,
    options: { key?: string; onError?: (error: unknown) => void } = {},
  ): Promise<void> {
    const key = options.key ?? payload.itemId ?? payload.field;
    const version = (rangeVersions.get(key) ?? 0) + 1;
    rangeVersions.set(key, version);
    numericRangeLoading.value = { ...numericRangeLoading.value, [key]: true };
    numericRangeErrors.value = { ...numericRangeErrors.value, [key]: false };
    try {
      const range = await load();
      if (rangeVersions.get(key) !== version) return;
      numericRanges.value = { ...numericRanges.value, [key]: range };
    } catch (error) {
      if (rangeVersions.get(key) !== version) return;
      numericRangeErrors.value = { ...numericRangeErrors.value, [key]: true };
      options.onError?.(error);
    } finally {
      if (rangeVersions.get(key) === version) {
        numericRangeLoading.value = { ...numericRangeLoading.value, [key]: false };
      }
    }
  }

  function reset(): void {
    distinctVersions.clear();
    rangeVersions.clear();
    distinctValues.value = {};
    numericRanges.value = {};
    numericRangeLoading.value = {};
    numericRangeErrors.value = {};
  }

  return {
    distinctValues,
    numericRanges,
    numericRangeLoading,
    numericRangeErrors,
    requestRange,
    reset,
    searchDistinct,
  };
}
