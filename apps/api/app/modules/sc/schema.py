"""SC v2 image-in-shard schema contract.

Defines the SC-owned source shard image schema using PyArrow ``list<struct>``
for multi-image storage.  Each image struct carries identity, role, bytes,
and optional provenance so that downstream consumers (materializer, views,
training flows) can resolve images without out-of-band URI fetches.

Image role mapping
------------------
+---------------------+--------------------------------------------------+
| role value          | semantic mapping                                 |
+=====================+==================================================+
| ``"review"``        | ReviewImage entries — review / inspection images |
+---------------------+--------------------------------------------------+
| ``"patch_template"``| patch_images.template — reference / golden       |
|                     | die patch image                                  |
+---------------------+--------------------------------------------------+
| ``"patch_defective"``| patch_images.defective — defect region patch    |
|                     | image                                            |
+---------------------+--------------------------------------------------+
| ``"patch_difference"``| patch_images.difference — computed difference  |
|                     | patch image                                      |
+---------------------+--------------------------------------------------+

Schema version
--------------
``SC_SOURCE_SCHEMA_VERSION = "v2"`` — embedded in Parquet key-value metadata
so cross-deployment readers can detect schema drift.

Differences from v1
-------------------
- ``image_uris`` (JSON string) and ``metadata`` (JSON string) columns are
  removed.
- Replaced by a single ``images`` column of type ``list<struct>``.
- All existing scalar identity / location columns are preserved unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow as pa

if TYPE_CHECKING:
    from platform_runtime.sparse.models import DatasetManifest

# ── Schema version ────────────────────────────────────────────────────────

SC_SOURCE_SCHEMA_VERSION = "v2"

# ── Image struct dtype ────────────────────────────────────────────────────

SC_IMAGE_STRUCT_DTYPE = pa.struct(
    [
        pa.field("image_id", pa.string(), nullable=False),
        pa.field("image_type", pa.string(), nullable=False),
        pa.field("role", pa.string(), nullable=False),
        pa.field("content_type", pa.string(), nullable=False),
        pa.field("filename", pa.string(), nullable=False),
        pa.field("bytes", pa.binary(), nullable=True),
        pa.field("review_image_id", pa.int32(), nullable=True),
        pa.field("source_uri", pa.string(), nullable=True),
    ]
)
"""PyArrow struct dtype for a single SC image stored inline in shards.

Fields
------
image_id : string (not nullable)
    Unique identifier for the image within the sample.
    Corresponds to ``ReviewImage.image_id`` (int serialized as string).
image_type : string (not nullable)
    Image category.  One of ``"template"``, ``"defective"``,
    ``"difference"``, ``"review"``.
role : string (not nullable)
    Semantic role.  One of ``"review"``, ``"patch_template"``,
    ``"patch_defective"``, ``"patch_difference"``.  See :data:`IMAGE_ROLES`
    for the full mapping.
content_type : string (not nullable)
    MIME type (e.g. ``"image/jpeg"``, ``"image/png"``).
filename : string (not nullable)
    Original filename (e.g. ``"0000001_1.jpg"``, ``"template.png"``).
bytes : binary (nullable)
    Raw image bytes.  ``None`` when not yet fetched; resolved lazily via
    :class:`~app.modules.sc.domain.image_fetcher.ScImageFetcher`.
review_image_id : int32 (nullable)
    The ``review_image_id`` value for review images; ``None`` for
    patch/template/difference images.  Used as part of the
    ``GetScImageRequest`` to refetch images lazily.
source_uri : string (nullable)
    Optional upstream / provenance URI (e.g.
    ``"s3://review-images/20250101_120000/1/0000001_1.jpg"``).
    ``None`` for generated images that have no upstream origin.
"""

# ── Sparse shard schema (ColumnSchema-compatible dicts) ───────────────────

SC_SPARSE_SHARD_SCHEMA_V2: list[dict[str, str]] = [
    {"name": "sample_id", "type": "string"},
    {"name": "defect_id", "type": "string"},
    {"name": "inspection_time", "type": "string"},
    {"name": "wafer_key", "type": "int32"},
    {"name": "wafer_x", "type": "int32"},
    {"name": "wafer_y", "type": "int32"},
    {"name": "die_x", "type": "int32"},
    {"name": "die_y", "type": "int32"},
    {"name": "rough_bin", "type": "int32"},
    {"name": "class_number", "type": "int32"},
    {"name": "lot_id", "type": "string"},
    {"name": "images", "type": "list<struct>"},
]
"""SC v2 sparse shard schema as ColumnSchema-compatible dicts.

Each dict has ``name`` (column name) and ``type`` (string type name)
suitable for constructing ``ColumnSchema`` objects via::

    from platform_runtime.sparse import ColumnSchema
    columns = [ColumnSchema(**c) for c in SC_SPARSE_SHARD_SCHEMA_V2]

The ``images`` column type string ``"list<struct>"`` represents a
PyArrow ``list_(SC_IMAGE_STRUCT_DTYPE)``.  Use
:func:`_build_v2_pyarrow_schema` to obtain the concrete ``pa.schema()``
for table construction.

.. note::

    Compared to v1 (``_SC_SPARSE_SCHEMA`` in ``sc_import.py``):

    - ``"image_uris"`` and ``"metadata"`` columns are **removed**.
    - A new ``"images"`` column (``list<struct>``) carries all image
      identity, role, bytes, and provenance inline.
    - All other scalar columns (``sample_id`` … ``lot_id``) are
      **identical** in name and type.
"""

# ── Image role constants ──────────────────────────────────────────────────

IMAGE_ROLES: dict[str, str] = {
    "review": "ReviewImage entries — review / inspection images.  Maps to "
    "all entries in the review_images list.",
    "patch_template": "patch_images.template — reference / golden die "
    "patch image used for comparison.",
    "patch_defective": "patch_images.defective — defect region patch "
    "image that differs from the template.",
    "patch_difference": "patch_images.difference — computed difference patch image.",
}
"""Image role semantic mapping.

Each value is a tag stored in the ``role`` field of
:data:`SC_IMAGE_STRUCT_DTYPE`.  Consumers filter the ``images`` list
column by role using :func:`find_images_by_role`.

Mapping summary
---------------
===============  ===========================================================
Role             Semantic source
===============  ===========================================================
``review``       ReviewImage entries — inspection images
``patch_template`` patch_images.template — golden die reference
``patch_defective`` patch_images.defective — defect patch
``patch_difference`` patch_images.difference — difference patch
===============  ===========================================================
"""

# ── Helpers ───────────────────────────────────────────────────────────────


def check_sc_v2_or_raise(manifest: DatasetManifest) -> None:
    """Verify *manifest* carries the expected SC source shard schema version.

    Raises ``ValueError`` with a clear re-import message when the manifest
    was produced by a legacy importer (``schema_version`` is ``None`` or not
    ``"v2"``).
    """
    if manifest.schema_version != SC_SOURCE_SCHEMA_VERSION:
        desc = manifest.schema_version or "legacy (no version)"
        raise ValueError(
            f"Dataset {manifest.dataset_id!r} uses SC source shard schema "
            f"{desc!r}, expected {SC_SOURCE_SCHEMA_VERSION!r}. "
            f"Please re-import the dataset using the v2 importer."
        )


def find_images_by_role(
    images_list: list[dict[str, object]], role: str
) -> list[dict[str, object]]:
    """Select image struct(s) from the images list column that match *role*.

    Parameters
    ----------
    images_list:
        A list of image struct dicts as they appear in the ``images``
        column of a sparse shard row.  Each dict has keys matching the
        fields of :data:`SC_IMAGE_STRUCT_DTYPE`.
    role:
        The image role to filter by.  Must be one of the keys in
        :data:`IMAGE_ROLES` (``"review"``, ``"patch_template"``,
        ``"patch_defective"``).

    Returns
    -------
    list[dict]
        Matching image struct dicts.  Returns an empty list when no
        image matches the requested role.

    Examples
    --------
    >>> from app.modules.sc.schema import find_images_by_role
    >>> row = pa_table.to_pylist()[0]
    >>> review_imgs = find_images_by_role(row["images"], "review")
    >>> assert len(review_imgs) == 1
    >>> review_bytes = review_imgs[0]["bytes"]
    """
    return [img for img in images_list if img.get("role") == role]


def _build_v2_pyarrow_schema() -> pa.Schema:
    """Build a concrete PyArrow schema from the v2 column definitions.

    Combines the scalar columns encoded in
    :data:`SC_SPARSE_SHARD_SCHEMA_V2` with the
    :data:`SC_IMAGE_STRUCT_DTYPE` to produce a ``pa.schema()`` suitable
    for ``pa.Table.from_pylist(rows, schema=...)``.

    Returns
    -------
    pa.Schema
    """
    _SCALAR_TYPE_MAP: dict[str, pa.DataType] = {
        "string": pa.string(),
        "int32": pa.int32(),
        "int64": pa.int64(),
        "float32": pa.float32(),
        "float64": pa.float64(),
        "bool": pa.bool_(),
    }

    fields: list[pa.Field] = []
    for col in SC_SPARSE_SHARD_SCHEMA_V2:
        name = col["name"]
        type_name = col["type"]
        if name == "images":
            fields.append(pa.field(name, pa.list_(SC_IMAGE_STRUCT_DTYPE)))
        else:
            dt = _SCALAR_TYPE_MAP.get(type_name)
            if dt is None:
                raise ValueError(f"Unknown scalar type: {type_name}")
            fields.append(pa.field(name, dt))
    return pa.schema(fields)
