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
  Train & Predict together. Missing Annotation, Prediction, and Final Class values appear as
  Unlabeled, No Prediction, and Unclassified.

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

- **Box selection** — draw a rectangle on the map to filter the Blink table to defects within that region.
- **Selection behavior** — right-click the map and choose **Exclude all others** to show only selected defects, **Exclude selected** to hide them, or **Invert selection** to reverse the active selection filter. The menu can also copy selected defect IDs, undo selection-filter changes, and switch selection tools.
- **Legend coloring** — by bin, class number, annotation status, or prediction label.
- **Custom colors** — label colors accept text labels as well as numeric classes and persist per
  dataset and legend source.
- **Zoom** — click to zoom into a region.
- **Map filters** — active filters are shown in the tab bar with a **Clear** option.

### Labels

- Labels are defined by the dataset or default to numeric labels 1–9.
- **Add new labels** on the fly via the label input in the annotation sidebar.
- Apply labels in bulk: select defects, choose a label, and submit.

### Sampling

Click **Sampling** to open the sampling modal:

- Specify a **sample count** (default: 200).
- Keep **Review candidates only** enabled to sample defects that have review images.
- Optionally limit candidates to the **current map selection**.
- Set a seed to reproduce the same draw from an unchanged candidate set.
- Optionally choose and assign a draft label. Existing drafts outside the sample are preserved.

The active cohort is shown in the Sampling button and limits the map, table, gallery, group
distribution, and Train & Predict. Changing the Global Filter, Review mode, or map selection clears
the cohort so stale sampling results cannot remain active silently.

### Train & Predict

1. Select a **trainer** from the dropdown.
2. Click **Train & Predict** to start a training job.
3. The UI polls job status in real time with status messages.
4. On completion, predictions run automatically and refresh labels and confidence scores across the view.

### Review Images

Review images from the upstream inspection are fetched and displayed for the current inspection context. These are accessible within the Blink table and annotation grid views.
