const INTERACTIVE_ROW_TARGET_SELECTOR = [
  "a",
  "button",
  "input",
  "label",
  "[role='button']",
  "[role='checkbox']",
  "[data-row-click-stop]",
].join(",");

export function shouldIgnoreSummaryRowClick(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest(INTERACTIVE_ROW_TARGET_SELECTOR) !== null;
}
