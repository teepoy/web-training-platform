import { ref, computed, onBeforeUnmount, type Ref } from "vue";

export interface UseBlinkRubberBandParams {
  scrollRef: Ref<HTMLElement | null>;
  onSelect: (
    defectIds: string[],
    modifiers: {
      shift: boolean;
      ctrl: boolean;
      meta: boolean;
      selectionMode?: "replace" | "add" | "toggle";
    },
  ) => void;
}

export function useBlinkRubberBand(params: UseBlinkRubberBandParams) {
  const { scrollRef, onSelect } = params;

  const isDragging = ref(false);
  const dragStart = ref<{ x: number; y: number } | null>(null);
  const dragCurrent = ref<{ x: number; y: number } | null>(null);
  const dragModifiers = ref<{ shift: boolean; ctrl: boolean; meta: boolean }>({
    shift: false,
    ctrl: false,
    meta: false,
  });
  const DRAG_THRESHOLD = 5;
  let autoScrollTimer: ReturnType<typeof setInterval> | null = null;

  const rubberRect = computed(() => {
    if (!dragStart.value || !dragCurrent.value || !scrollRef.value) return null;
    const rect = scrollRef.value.getBoundingClientRect();
    const x1 = Math.min(dragStart.value.x, dragCurrent.value.x) - rect.left;
    const y1 =
      Math.min(dragStart.value.y, dragCurrent.value.y) -
      rect.top +
      scrollRef.value.scrollTop;
    const x2 = Math.max(dragStart.value.x, dragCurrent.value.x) - rect.left;
    const y2 =
      Math.max(dragStart.value.y, dragCurrent.value.y) -
      rect.top +
      scrollRef.value.scrollTop;
    return { left: x1, top: y1, width: x2 - x1, height: y2 - y1 };
  });

  const rubberBandStyle = computed(() => {
    const rr = rubberRect.value;
    if (!rr) return { display: "none" };
    return {
      left: rr.left + "px",
      top: rr.top + "px",
      width: rr.width + "px",
      height: rr.height + "px",
    };
  });

  function computeSelectedDefectIds(): string[] {
    if (!rubberRect.value || !scrollRef.value) return [];
    const rr = rubberRect.value;
    const rrBottom = rr.top + rr.height;
    const rrRight = rr.left + rr.width;

    const rows = scrollRef.value.querySelectorAll<HTMLElement>(
      "[data-defect-id]",
    );
    const intersecting: string[] = [];
    const containerRect = scrollRef.value.getBoundingClientRect();
    const scrollTop = scrollRef.value.scrollTop;

    for (const row of rows) {
      const rowRect = row.getBoundingClientRect();
      const rowTop = rowRect.top - containerRect.top + scrollTop;
      const rowBottom = rowTop + rowRect.height;
      const rowLeft = rowRect.left - containerRect.left;
      const rowRight = rowLeft + rowRect.width;

      if (
        rowBottom >= rr.top &&
        rowTop <= rrBottom &&
        rowRight >= rr.left &&
        rowLeft <= rrRight
      ) {
        const id = row.dataset.defectId;
        if (id) intersecting.push(id);
      }
    }
    return intersecting;
  }

  function startAutoScroll(): void {
    if (autoScrollTimer) return;
    autoScrollTimer = setInterval(() => {
      if (!isDragging.value || !dragCurrent.value || !scrollRef.value) return;
      const rect = scrollRef.value.getBoundingClientRect();
      const edgeZone = 40;
      const speed = 12;
      if (dragCurrent.value.y < rect.top + edgeZone) {
        scrollRef.value.scrollTop -= speed;
      } else if (dragCurrent.value.y > rect.bottom - edgeZone) {
        scrollRef.value.scrollTop += speed;
      }
    }, 16);
  }

  function stopAutoScroll(): void {
    if (autoScrollTimer) {
      clearInterval(autoScrollTimer);
      autoScrollTimer = null;
    }
  }

  function onMouseDown(e: MouseEvent): void {
    if (e.button !== 0) return;
    if (
      (e.target as HTMLElement).closest(
        "button, input, .n-switch, .n-radio-group, .n-input-number",
      )
    )
      return;
    e.preventDefault();
    dragStart.value = { x: e.clientX, y: e.clientY };
    dragCurrent.value = { x: e.clientX, y: e.clientY };
    dragModifiers.value = {
      shift: e.shiftKey,
      ctrl: e.ctrlKey,
      meta: e.metaKey,
    };
    document.addEventListener("mousemove", onDocMouseMove);
    document.addEventListener("mouseup", onDocMouseUp);
  }

  function onDocMouseMove(e: MouseEvent): void {
    if (!dragStart.value) return;
    dragCurrent.value = { x: e.clientX, y: e.clientY };
    const dx = e.clientX - dragStart.value.x;
    const dy = e.clientY - dragStart.value.y;
    if (!isDragging.value && Math.sqrt(dx * dx + dy * dy) >= DRAG_THRESHOLD) {
      isDragging.value = true;
      startAutoScroll();
    }
  }

  function onDocMouseUp(): void {
    document.removeEventListener("mousemove", onDocMouseMove);
    document.removeEventListener("mouseup", onDocMouseUp);
    stopAutoScroll();

    if (isDragging.value) {
      const ids = computeSelectedDefectIds();
      if (ids.length > 0) {
        const shouldAdd =
          dragModifiers.value.shift ||
          dragModifiers.value.ctrl ||
          dragModifiers.value.meta;
        onSelect(ids, {
          ...dragModifiers.value,
          selectionMode: shouldAdd ? "add" : "replace",
        });
      }
    }

    isDragging.value = false;
    dragStart.value = null;
    dragCurrent.value = null;
    dragModifiers.value = { shift: false, ctrl: false, meta: false };
  }

  onBeforeUnmount(() => {
    stopAutoScroll();
    document.removeEventListener("mousemove", onDocMouseMove);
    document.removeEventListener("mouseup", onDocMouseUp);
  });

  return {
    isDragging,
    rubberRect,
    rubberBandStyle,
    onMouseDown,
    onDocMouseMove,
    onDocMouseUp,
  };
}
