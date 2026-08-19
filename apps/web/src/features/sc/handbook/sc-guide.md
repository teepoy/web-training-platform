# SC Inspection Guide

This guide covers the Patch (SC) inspection preview and reclassify workflows.

## SC Preview

The SC Preview page (`/sc/preview`) is the entry point for exploring raw patch inspection data before importing it into the platform.

### Searching Inspections

1. Select a **date range** using the date picker.
2. Click **Search** to fetch inspection summaries from the upstream SC service.
3. Results appear as a sortable table showing inspection time, lot/wafer/layer IDs, defect count, image count, equipment ID, and recipe ID.

### Viewing an Inspection

Click any row in the summary table to open an **inspection tab**. Each tab displays:

- **Wafer Map** — full wafer view with defect points.
- **Die Map** — per-die detailed view.
- **Reticle Map** — reticle-level view with configurable die counts and offsets.

Defect points are color-coded by a configurable **legend grouping** (e.g., by rough bin or class number). You can:

- **Zoom** into rectangular regions on any map to fetch higher-resolution data.
- **Filter and sort** defects in the data table below the maps.
- Click defects to select them and view associated review images.
- Use **Global Filter** beside the page title to constrain the map, table, gallery, sampling, and
  Train & Predict together. The QueryBuilder supports nested **AND**/**OR** groups through
  **+ Condition** and **+ Group**. The same property may appear more than once, and sibling nodes
  can be reordered or deleted independently. Property, condition, and value are edited inline and
  remain visible on every completed condition. These edits are staged inside the modal; click
  **Apply filters** to update the workbench, or cancel/close to discard them. Set filters provide
  **Select all** for the currently visible options.
  Missing Annotation, Prediction, and Final Class values appear as Unlabeled, No Prediction, and
  Unclassified.

### Importing an Inspection

To import an inspection as a manageable dataset:

1. Click **Import as Dataset** in the toolbar (visible when an inspection tab is active).
2. In the modal, review the pre-filled inspection time, wafer key, and auto-generated dataset name.
3. Select a **storage mode** (default: Sparse Shard).
4. Click **Start Import**.

Import progress is tracked in real time via SSE. Once the first samples are available, a link to the reclassify page opens automatically.

### Tab Management

- The tab bar supports multiple concurrent tabs.
- Click the **+** button to create a new Summary tab.
- Click the **x** on any tab to close it.
- Up to 3 tabs are kept alive concurrently; unused tabs are re-activated on click.

## SC Reclassify

The Reclassify page (`/datasets/:id/sc/classify`) provides a full annotation and training workflow for imported SC datasets.

### Navigation

- The header shows the dataset name and a **← Back** button to return to the previous page.
- Dataset metadata (sample count, wafer key, inspection time) is available via the **…** menu.

### Annotation Workflow

The page has two main views, switchable via the tab bar:

#### Blink Table

A virtualized image grid showing each defect with three patch images:

- **Template** — reference patch.
- **Defective** — the defect patch.
- **Difference** — the computed difference.

Key actions:

- **Select defects** by clicking checkboxes or clicking directly on images.
- **Assign labels** using the dropdowns on each card or the bulk annotation sidebar.
- **Drafts** are saved locally; click **Submit Annotations** to persist them to the backend.
- A live draft count and annotated count track your progress.

#### Map View

The same wafer/die/reticle map triad as the preview page, integrated with annotation:

- **Box selection** — draw a rectangle on the map to append defects to the active map selection.
- **Selection behavior** — a box, lasso, legend, or distribution selection immediately narrows the
  table and gallery without changing the map. Right-click the map and choose **Exclude all others**
  or **Exclude selected** to commit the selected IDs into the Global Filter. The transient selection
  is then cleared and the map reloads, so additional regions can be selected and excluded
  continuously. Each commit remains visible as a separate, removable `map_id` condition. **Invert
  selection** replaces the transient selection with its complement inside the currently visible Map
  points; it does not commit a filter. Hidden legend values cannot be selected. Hiding a value removes
  its IDs from the current transient selection, cross marks, context-menu actions, and copied IDs;
  unhiding it does not restore the old selection. The menu can also copy selected defect IDs and switch
  selection tools. Selection IDs and black cross marks are produced together from the frontend Map
  Arrow snapshot; pan and zoom only reproject them and do not clear the selection.
- **Legend coloring** — by bin, class number, annotation status, or prediction label.
- **Custom colors** — label colors accept text labels as well as numeric classes and persist per
  dataset and legend source.
- **Zoom** — click to zoom into a region.
- **Committed map filters** — active map commits are ordinary conditions in the Global Filter
  expression; deleting that condition cancels only that commit.

### Labels

- Labels are defined by the dataset or default to numeric labels 1–9.
- **Add new labels** on the fly via the label input in the annotation sidebar.
- Apply labels in bulk: select defects, choose a label, and submit.

### Sampling

Click **Annotation Sampling** beside **Global Filter** to open the sampling modal:

- Choose All, Map Selection, or Table Selection as the candidate scope.
- Configure the enabled sampling rules and optional Extra filter.
- Percentage rules always round down to a whole sample; rounding is not configurable.
- In **After sampling**, draft-label assignment is enabled by default and uses the selected label.
  Disable it when the sampled cohort should not change annotation drafts. Existing drafts outside the
  sample are preserved.

The active cohort is shown in the Annotation Sampling button and narrows only the table and gallery. It
composes with Review mode, transient map selection, and table filters; it does not alter the map,
group distribution, Global Filter, or Train & Predict inputs. Clear or replace the cohort explicitly
from the Annotation Sampling control.

### Train & Predict

1. Select a **trainer** from the dropdown.
2. Click **Train & Predict** to start a training job.
3. The UI polls job status in real time with status messages.
4. On completion, predictions run automatically and refresh labels and confidence scores across the view.

### Review Images

Review images from the upstream inspection are fetched and displayed for the current inspection context. These are accessible within the Blink table and annotation grid views.
