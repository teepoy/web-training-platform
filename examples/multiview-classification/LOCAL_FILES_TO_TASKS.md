# Build Label Studio tasks from local multiview directories

This guide builds one Label Studio task per directory. Every image inside that
directory becomes a view of the same logical sample.

## Directory layout

The examples below assume this structure:

```text
/Users/jin/data/multiview/
├── part-0001/
│   ├── front.png
│   ├── left.png
│   └── right.png
└── part-0002/
    ├── front.png
    ├── left.png
    └── right.png
```

The directory name becomes `sample_id`. The image filename without its
extension becomes the view name.

## Allow Label Studio to read the files

Start Label Studio with local file serving enabled and set the document root to
the common parent of every image:

```bash
export LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED=true
export LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT=/Users/jin/data/multiview
label-studio start
```

Task data must use URLs relative to this document root:

```text
/data/local-files/?d=part-0001/front.png
```

Do not use an absolute filesystem path or a `file://` URL in task data.

## Variable number of views

Save the following as `build_tasks.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

DOCUMENT_ROOT = Path("/Users/jin/data/multiview").resolve()
OUTPUT_PATH = Path("tasks.json")

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp",
    ".tif",
    ".tiff",
}


def local_file_url(path: Path) -> str:
    path = path.resolve()

    try:
        relative = path.relative_to(DOCUMENT_ROOT)
    except ValueError as exc:
        raise ValueError(f"{path} is outside {DOCUMENT_ROOT}") from exc

    encoded = quote(relative.as_posix(), safe="/")
    return f"/data/local-files/?d={encoded}"


tasks = []

for sample_dir in sorted(DOCUMENT_ROOT.iterdir()):
    if not sample_dir.is_dir():
        continue

    image_paths = sorted(
        path
        for path in sample_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )

    if not image_paths:
        raise ValueError(f"No images found for sample {sample_dir.name}")

    tasks.append(
        {
            "data": {
                "sample_id": sample_dir.name,
                "images": [local_file_url(path) for path in image_paths],
                "view_names": [path.stem for path in image_paths],
            }
        }
    )

OUTPUT_PATH.write_text(
    json.dumps(tasks, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print(f"Wrote {len(tasks)} tasks to {OUTPUT_PATH.resolve()}")
```

Run it:

```bash
python build_tasks.py
```

The resulting `tasks.json` has this shape:

```json
[
  {
    "data": {
      "sample_id": "part-0001",
      "images": [
        "/data/local-files/?d=part-0001/front.png",
        "/data/local-files/?d=part-0001/left.png",
        "/data/local-files/?d=part-0001/right.png"
      ],
      "view_names": ["front", "left", "right"]
    }
  }
]
```

Use this payload with `label-studio/variable-views.xml`.

## Fixed front, left, and right views

To use `label-studio/three-view-grid.xml`, replace the `tasks.append(...)`
block in the script with:

```python
paths_by_view = {path.stem: path for path in image_paths}
required_views = {"front", "left", "right"}

if set(paths_by_view) != required_views:
    raise ValueError(
        f"{sample_dir.name} requires exactly {sorted(required_views)}; "
        f"found {sorted(paths_by_view)}"
    )

tasks.append(
    {
        "data": {
            "sample_id": sample_dir.name,
            "front": local_file_url(paths_by_view["front"]),
            "left": local_file_url(paths_by_view["left"]),
            "right": local_file_url(paths_by_view["right"]),
        }
    }
)
```

This produces:

```json
[
  {
    "data": {
      "sample_id": "part-0001",
      "front": "/data/local-files/?d=part-0001/front.png",
      "left": "/data/local-files/?d=part-0001/left.png",
      "right": "/data/local-files/?d=part-0001/right.png"
    }
  }
]
```

## Import into Label Studio

1. Create a project and apply the matching XML labeling configuration.
2. Open **Data Import** and upload `tasks.json`.
3. If you configure **Local Files** under **Cloud Storage**, choose the
   **Tasks** import method.
4. Choose **Save**, not **Save & Sync**. Syncing the image directory directly
   would create one task per file instead of one multiview task per directory.

## Docker

When Label Studio runs in Docker, mount the host image directory into the
container and set `LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT` to the container
path. For example, if the host directory is mounted at `/label-studio/files`,
use:

```text
LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT=/label-studio/files
```

The paths after `?d=` remain relative to that container document root.

See the official
[Label Studio local storage guide](https://labelstud.io/guide/storage_local)
for storage configuration and security considerations.
