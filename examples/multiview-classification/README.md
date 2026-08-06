# Multiview classification with Label Studio and FiftyOne

This bundle models one logical sample as multiple images that share one
classification label.

```text
logical sample (sample_id, label)
  ├── front image
  ├── left image
  └── right image
```

It matches the platform's existing classification shape:
`ClassificationSample.sample_id`, `ClassificationSample.image_uris`, and one
`ClassificationSample.label`.

## Contents

| Artifact | Use |
| --- | --- |
| `label-studio/variable-views.xml` | Any number of images, shown in Label Studio's multi-image viewer |
| `label-studio/three-view-grid.xml` | Fixed `front`, `left`, and `right` views shown together |
| `label-studio/six-view-grid.xml` | Fixed six-camera inspection grid shown together |
| `label-studio/tasks.*.example.json` | Importable task payloads for the corresponding XML |
| `label-studio/export.example.json` | Minimal completed Label Studio export for sync testing |
| `LOCAL_FILES_TO_TASKS.md` | Build `tasks.json` from multiview images in local directories |
| `fiftyone/annotation_config.example.json` | FiftyOne Label Studio backend configuration |
| `fiftyone/multiview_classification.ipynb` | Self-contained grouped-dataset visualization and LS round trip |

## Pick a Label Studio config

- Use `variable-views.xml` when view names/counts vary. Its `Image` tag uses
  `valueList="$images"`; the images are browsed as one multi-image object.
- Use `three-view-grid.xml` when all three named views should be visible at the
  same time.
- Use `six-view-grid.xml` for a denser fixed camera layout.

All three configs emit the same logical annotation field:

```json
{
  "from_name": "classification",
  "type": "choices",
  "value": {"choices": ["ok"]}
}
```

The `to_name` differs by config because Label Studio controls must target an
object tag. It is `images` for the variable config and `front` for both grid
configs. The notebook importer intentionally keys on `from_name` and does not
couple the logical label to this UI-only target.

Replace the example `ok`, `misaligned`, and `damaged` choices in both the XML
and notebook parameters with the real dataset label space.

## Label Studio quick start

1. Configure a Label Studio project with one XML file, for example:

   ```bash
   label-studio multiview-demo start \
     --label-config label-studio/variable-views.xml
   ```

2. Import `label-studio/tasks.variable.example.json`.
3. Annotate each task once. The selected class applies to every image in that
   task.
4. Export JSON and point `LS_EXPORT_PATH` in the notebook at that file.

The checked-in task payloads use public placeholder URLs. For local media, set
these environment variables before starting Label Studio:

```bash
export LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED=true
export LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT=/absolute/path/to/media
label-studio start
```

Then provide task URLs in this form:

```text
/data/local-files/?d=sample-001/front.png
```

Do not put credentials or platform authorization headers in task JSON. Browser
image requests cannot attach custom headers; platform-managed images should use
the repository's authenticated image URL adapter/proxy.

## FiftyOne quick start

From the repository root:

```bash
uv run jupyter lab examples/multiview-classification/fiftyone/multiview_classification.ipynb
```

Run the notebook top to bottom. Its default mode creates six local synthetic
logical samples, each with three slices, then launches the FiftyOne App. Set
`GENERATE_DEMO_DATA = False` and provide `MANIFEST_PATH` to load real data.

The manifest schema is:

```json
[
  {
    "sample_id": "part-0001",
    "label": "ok",
    "images": [
      {"view": "front", "filepath": "/absolute/media/part-0001/front.png"},
      {"view": "left", "filepath": "/absolute/media/part-0001/left.png"},
      {"view": "right", "filepath": "/absolute/media/part-0001/right.png"}
    ]
  }
]
```

FiftyOne stores one image per physical `Sample`. The notebook assigns all
images of a logical sample to one `fo.Group`, stores `logical_sample_id` on
every slice, and copies `ground_truth` to every slice. Copying the label is
deliberate: it makes label filtering work from any selected slice. Metrics are
computed only on the default slice so each logical sample is counted once.

The standard FiftyOne Label Studio backend remains useful for per-image or
per-slice annotation. The notebook's small explicit JSON bridge is what creates
one custom Label Studio task containing all images in a group.

## Contracts and invariants

- `sample_id` is the stable logical identity; view names are not identities.
- Every `(sample_id, view)` pair must be unique.
- Every logical sample must contain the configured default slice.
- All slices in a group must have the same ground-truth label.
- Classification evaluation must select exactly one slice per group.
- A Label Studio sync fails if a task has no class, multiple completed
  annotations, an unknown class, or an unknown `sample_id`.

References: [Label Studio Image `valueList`](https://labelstud.io/tags/image),
[Label Studio multi-image classification](https://labelstud.io/templates/multi-image_classification),
[FiftyOne grouped datasets](https://docs.voxel51.com/user_guide/groups.html), and
[FiftyOne's Label Studio integration](https://docs.voxel51.com/integrations/labelstudio.html).
