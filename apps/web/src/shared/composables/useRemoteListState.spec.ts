import { nextTick, ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useRemoteListState } from "./useRemoteListState";

describe("useRemoteListState", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("debounces search and resets pagination and selection when filters change", async () => {
    const keyword = ref("");
    const creator = ref("all");
    const total = ref(48);
    const resetSelection = vi.fn();
    const state = useRemoteListState({
      keyword,
      filters: [creator],
      total,
      initialSorter: { columnKey: "created_at", order: "descend", sorter: true },
      onResetSelection: resetSelection,
    });

    state.pagination.page = 2;
    resetSelection.mockClear();
    keyword.value = "wafer";
    await nextTick();

    expect(state.pagination.page).toBe(1);
    expect(resetSelection).toHaveBeenCalled();
    expect(state.debouncedKeyword.value).toBe("");

    vi.advanceTimersByTime(250);
    await nextTick();
    expect(state.debouncedKeyword.value).toBe("wafer");

    state.pagination.page = 2;
    creator.value = "me";
    await nextTick();
    expect(state.pagination.page).toBe(1);
  });

  it("keeps pagination and sorting behavior consistent", async () => {
    const total = ref(10);
    const state = useRemoteListState({
      keyword: "",
      total,
      initialSorter: { columnKey: "updated_at", order: "descend", sorter: true },
    });

    expect(state.tablePagination.value).toBe(false);
    total.value = 21;
    await nextTick();
    expect(state.pagination.itemCount).toBe(21);
    expect(state.tablePagination.value).toBe(state.pagination);

    state.pagination.page = 2;
    state.handleSorterChange({ columnKey: "name", order: "ascend", sorter: true });
    expect(state.pagination.page).toBe(1);
    expect(state.sorter.value?.columnKey).toBe("name");
  });
});
