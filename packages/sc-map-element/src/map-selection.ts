export interface MapSelectionPoint {
  x: number;
  y: number;
}

export type MapSelectionSetOperation = "append" | "replace" | "invert" | "prune" | "clear";

export function combineMapSelectionIds(
  current: ReadonlySet<number>,
  candidates: ReadonlySet<number>,
  operation: MapSelectionSetOperation,
): Set<number> {
  if (operation === "clear") return new Set();
  if (operation === "replace") return new Set(candidates);
  if (operation === "append") return new Set([...current, ...candidates]);
  if (operation === "prune") {
    return new Set([...current].filter((id) => candidates.has(id)));
  }
  return new Set([...candidates].filter((id) => !current.has(id)));
}

export function pointInPolygon(
  point: MapSelectionPoint,
  polygon: readonly MapSelectionPoint[],
): boolean {
  let inside = false;
  for (
    let current = 0, previous = polygon.length - 1;
    current < polygon.length;
    previous = current++
  ) {
    const currentPoint = polygon[current];
    const previousPoint = polygon[previous];
    const edgeX = currentPoint.x - previousPoint.x;
    const edgeY = currentPoint.y - previousPoint.y;
    const pointX = point.x - previousPoint.x;
    const pointY = point.y - previousPoint.y;
    const cross = edgeX * pointY - edgeY * pointX;
    const edgeScale = Math.max(1, Math.abs(edgeX), Math.abs(edgeY));
    if (
      Math.abs(cross) <= Number.EPSILON * edgeScale * edgeScale * 8 &&
      point.x >= Math.min(previousPoint.x, currentPoint.x) &&
      point.x <= Math.max(previousPoint.x, currentPoint.x) &&
      point.y >= Math.min(previousPoint.y, currentPoint.y) &&
      point.y <= Math.max(previousPoint.y, currentPoint.y)
    ) {
      return true;
    }
    const crosses =
      currentPoint.y > point.y !== previousPoint.y > point.y &&
      point.x <
        ((previousPoint.x - currentPoint.x) * (point.y - currentPoint.y)) /
          (previousPoint.y - currentPoint.y) +
          currentPoint.x;
    if (crosses) inside = !inside;
  }
  return inside;
}
