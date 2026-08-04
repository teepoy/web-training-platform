# SC Map Element

Framework-independent native Web Component for SC map rendering.

```ts
import { defineScMapElement } from "@platform/sc-map-element";

defineScMapElement();
```

```html
<sc-map></sc-map>
```

The element exposes typed JavaScript properties rather than JSON attributes:

- `arrowData`: Arrow IPC `ArrayBuffer` containing `defect_id`, all wafer/die/reticle
  coordinate columns, the active legend column, and optional `images`
- `legendColumn`: column used to color and group points
- `hiddenLegendKeys`: legend values excluded during projection
- `mode`: `wafer`, `die`, or `reticle`
- `colorMap`: legend key to CSS color
- `showImageMarkers`: enables or disables black image-availability boxes
- `defectSize`: rendered defect square size in CSS pixels
- `zoom`: `{ x, y, w, h } | null`
- `geometry`: wafer, die, and reticle geometry
- `interactionMode`: `select`, `lasso`, `zoomin`, or `pan`

Area selections are additive. Box selection emits `box-select`; lasso selection
emits `lasso-select` with the polygon and its bounding region. Double-click emits
`clear-selection`. Right-click emits `map-context-menu` with the viewport `x` and
`y` coordinates. Zoom reset is controlled explicitly by assigning `zoom = null`.

Left-button dragging follows `interactionMode`. Right-button dragging always pans
without changing that mode. Ordinary trackpad `wheel` input uses `deltaX` and
`deltaY` to pan. Trackpad pinch input, represented by browsers as `wheel` with
`ctrlKey`, zooms around the pointer. Wheel deltas are normalized and accumulated
per animation frame, visual viewport changes are previewed immediately, and one
final `zoom-in` event plus Arrow reprojection is committed 120 ms after input
stops. Zoom sensitivity is defined by `SC_MAP_WHEEL_ZOOM_SENSITIVITY`.
Zoomed Arrow projections retain 20% overscan on every edge so a nearby pan can
render image data immediately while the next projection is being prepared.

`<sc-map>` owns both workers. Its Arrow worker retains and iterates the Arrow
vectors directly for mode selection, zoom filtering, pixel-grid binning, and
deduplication. Its render worker owns the `OffscreenCanvas`. Zoom, pan, resize,
legend visibility, and mode changes do not recreate the Arrow dataset.
