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

  interface DragPoint {
    clientX: number;
    clientY: number;
    contentX: number;
    contentY: number;
  }

  const isDragging = ref(false);
  const dragStart = ref<DragPoint | null>(null);
  const dragCurrent = ref<DragPoint | null>(null);
  const dragModifiers = ref<{ shift: boolean; ctrl: boolean; meta: boolean }>({
    shift: false,
    ctrl: false,
    meta: false,
  });
  const DRAG_THRESHOLD = 5;
  let autoScrollTimer: ReturnType<typeof setInterval> | null = null;

  function toDragPoint(clientX: number, clientY: number): DragPoint | null {
    if (!scrollRef.value) return null;
    const rect = scrollRef.value.getBoundingClientRect();
    return {
      clientX,
      clientY,
      contentX: clientX - rect.left + scrollRef.value.scrollLeft,
      contentY: clientY - rect.top + scrollRef.value.scrollTop,
    };
  }

  function refreshCurrentContentPoint(): void {
    if (!dragCurrent.value) return;
    const updated = toDragPoint(
      dragCurrent.value.clientX,
      dragCurrent.value.clientY,
    );
    if (updated) dragCurrent.value = updated;
  }

  const rubberRect = computed(() => {
    if (!dragStart.value || !dragCurrent.value) return null;
    const x1 = Math.min(dragStart.value.contentX, dragCurrent.value.contentX);
    const y1 = Math.min(dragStart.value.contentY, dragCurrent.value.contentY);
    const x2 = Math.max(dragStart.value.contentX, dragCurrent.value.contentX);
    const y2 = Math.max(dragStart.value.contentY, dragCurrent.value.contentY);
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
    const scrollLeft = scrollRef.value.scrollLeft;
    const scrollTop = scrollRef.value.scrollTop;

    for (const row of rows) {
      const rowRect = row.getBoundingClientRect();
      const rowTop = rowRect.top - containerRect.top + scrollTop;
      const rowBottom = rowTop + rowRect.height;
      const rowLeft = rowRect.left - containerRect.left + scrollLeft;
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
      const element = scrollRef.value;
      const rect = scrollRef.value.getBoundingClientRect();
      const edgeZone = 40;
      const speed = 12;
      let nextScrollTop = element.scrollTop;
      let nextScrollLeft = element.scrollLeft;
      if (dragCurrent.value.clientY < rect.top + edgeZone) {
        nextScrollTop -= speed;
      } else if (dragCurrent.value.clientY > rect.bottom - edgeZone) {
        nextScrollTop += speed;
      }
      if (dragCurrent.value.clientX < rect.left + edgeZone) {
        nextScrollLeft -= speed;
      } else if (dragCurrent.value.clientX > rect.right - edgeZone) {
        nextScrollLeft += speed;
      }
      nextScrollTop = Math.min(
        element.scrollHeight - element.clientHeight,
        Math.max(0, nextScrollTop),
      );
      nextScrollLeft = Math.min(
        element.scrollWidth - element.clientWidth,
        Math.max(0, nextScrollLeft),
      );
      const didScroll =
        nextScrollTop !== element.scrollTop || nextScrollLeft !== element.scrollLeft;
      if (!didScroll) return;
      element.scrollTop = nextScrollTop;
      element.scrollLeft = nextScrollLeft;
      refreshCurrentContentPoint();
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
    const point = toDragPoint(e.clientX, e.clientY);
    if (!point) return;
    dragStart.value = point;
    dragCurrent.value = point;
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
    const point = toDragPoint(e.clientX, e.clientY);
    if (!point) return;
    dragCurrent.value = point;
    const dx = e.clientX - dragStart.value.clientX;
    const dy = e.clientY - dragStart.value.clientY;
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
