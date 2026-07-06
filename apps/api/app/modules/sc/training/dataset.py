"""PyTorch :class:`Dataset` that consumes SC training samples through a
:class:`~app.modules.datasets.app.view_loader.DatasetViewLoader`.

Replaces the former inline ``_DualScDataset`` in the SC trainer with a
view-loader-first contract.  Image bytes are resolved lazily per
``__getitem__`` call from already-materialized items.

Materialized path
    Records are plain dicts with ``defective_bytes`` and
    ``reference_bytes`` already embedded (runtime parquet from
    :class:`~app.modules.datasets.app.services.runtime_materializer.RuntimeMaterializer`).

Non-materialized path
    Items are :class:`~app.modules.sc.views.patch_image.v1.schemas.ScPatchImageV1Row`
    with ``images`` list of :class:`ScImageRef` — each carries a ``url``
    that is resolved through :func:`_decode_image_uri`.
"""

from __future__ import annotations

import asyncio
import base64
import io as _io
import urllib.request
from typing import Any

from PIL import Image
from torch.utils.data import Dataset

import nest_asyncio

nest_asyncio.apply()


def _decode_image_uri(uri: str) -> bytes:
    """Decode a URI (data:, http://, https://) into raw bytes."""
    if uri.startswith("data:"):
        _, encoded = uri.split(",", 1)
        return base64.b64decode(encoded)
    if uri.startswith(("http://", "https://")):
        with urllib.request.urlopen(uri, timeout=30) as resp:
            return resp.read()
    raise ValueError(f"unsupported image URI scheme: {uri[:80]}")


def _safe_open_rgb(data: bytes, sample_id: Any, role: str) -> Image.Image:
    """Open image bytes into an RGB :class:`~PIL.Image.Image`.

    Validates that *data* is non-empty and not truncated.
    """
    if not data:
        raise ValueError(
            f"Sample {sample_id!r} has empty {role}_bytes "
            "(zero-length payload from materialized parquet)."
        )
    try:
        img = Image.open(_io.BytesIO(data))
        img.load()  # force decode now to surface truncation
        return img.convert("RGB")
    except (OSError, ValueError) as exc:
        raise ValueError(
            f"Sample {sample_id!r} has invalid {role}_bytes "
            f"({len(data)} bytes, head={data[:8]!r}): {exc}. "
            "The materialized parquet likely contains a truncated or "
            "corrupted image payload — re-materialize the dataset."
        ) from exc


class ScTrainingDataset(Dataset):
    """PyTorch Dataset backed by a :class:`DatasetViewLoader`.

    Accepts the view loader contract directly — no pre-materialized list
    of records passed in from outside.  Async-to-sync bridging happens
    once at construction time via :func:`asyncio.run`.

    Each ``__getitem__`` call returns ``(defective_tensor, reference_tensor,
    label_idx)`` compatible with the dual-ResNet-50 SC trainer.

    After construction the :attr:`labels`, :attr:`label_to_idx`, and
    :attr:`num_classes` properties are populated for downstream use
    (checkpoint metadata, model architecture).
    """

    def __init__(
        self,
        view: Any,
        transform: Any,
        *,
        label_space: list[str] | None = None,
        label_map: dict[str, str] | None = None,
        artifact_storage: Any = None,
    ) -> None:
        """Create the legacy SC training dataset.

        ``label_map`` is deprecated. Current flow-level trainers read labels
        from the storage LazyFrame and build compact ``label_to_idx`` mappings
        from active training rows.
        """
        self._transform = transform
        self._artifact_storage = artifact_storage
        self._label_map = label_map

        # ── Validate ──────────────────────────────────────────────────
        if not (hasattr(view, "__len__") and hasattr(view, "get_item")):
            raise ValueError(
                "view must satisfy DatasetViewLoader Protocol "
                "(has __len__ and async get_item)"
            )

        # ── Materialize all items once (async → sync bridge) ──────────
        self._items: list[Any] = asyncio.run(_materialize(view))
        self._len = len(self._items)

        if self._len == 0:
            raise ValueError("view loader is empty — cannot train without samples")

        # ── Extract labels from materialized items ────────────────────
        self.labels: list[str] = sorted(
            {_extract_label(r) for r in self._items if _extract_label(r)}
        )
        if not self.labels and label_space:
            self.labels = sorted(label_space)

        if len(self.labels) < 2:
            raise ValueError(
                f"need at least 2 distinct labels for training, got: {self.labels}"
            )

        self.label_to_idx: dict[str, int] = {
            label: i for i, label in enumerate(self.labels)
        }
        self.num_classes: int = len(self.labels)

    def __len__(self) -> int:
        return self._len

    def __getitem__(self, idx: int) -> tuple[Any, Any, int]:
        """Return ``(defective_tensor, reference_tensor, label_idx)``."""
        record = self._items[idx]
        label = _extract_label(record)
        if not label and self._label_map is not None:
            sample_id = _extract_sample_id(record, idx)
            label = self._label_map.get(sample_id, "")
            if not label:
                defect_id = _extract_defect_id(record)
                if defect_id:
                    label = self._label_map.get(defect_id, "")
            if not label:
                _keys = sorted(self._label_map.keys())[:5]
                raise ValueError(
                    "Could not resolve training label for "
                    f"sample_id={sample_id!r} defect_id={defect_id!r}; "
                    f"label_map({len(self._label_map)}) keys={_keys}"
                )
        if not label:
            sample_id = _extract_sample_id(record, idx)
            defect_id = _extract_defect_id(record)
            raise ValueError(
                "Training record has no label for "
                f"sample_id={sample_id!r} defect_id={defect_id!r}"
            )

        defective_bytes = _extract_image_bytes(
            record, "defective", self._artifact_storage
        )
        reference_bytes = _extract_image_bytes(
            record, "reference", self._artifact_storage
        )

        sample_id = _extract_sample_id(record, idx)

        defective_img = _safe_open_rgb(defective_bytes, sample_id, "defective")
        reference_img = _safe_open_rgb(reference_bytes, sample_id, "reference")

        return (
            self._transform(defective_img),
            self._transform(reference_img),
            self.label_to_idx[label],
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _materialize(view: Any) -> list[Any]:
    """Resolve all items from *view* into a plain list."""
    length = len(view)
    return [await view.get_item(i) for i in range(length)]


def _extract_label(record: Any) -> str:
    """Extract label from a record dict or Pydantic model.

    For materialized records the ``label`` key is present directly.
    For :class:`~app.modules.sc.views.patch_image.v1.schemas.ScPatchImageV1Row`
    the label comes from the annotation side-channel — the view row does
    not carry it.  We fall back to ``""`` and rely on the ``label_space``
    fallback passed to :class:`ScTrainingDataset`.
    """
    if isinstance(record, dict):
        return str(record.get("label", ""))
    if hasattr(record, "label"):
        return str(getattr(record, "label"))
    return ""


def _extract_defect_id(record: Any) -> str | None:
    """Extract ``defect_id`` from a record dict or Pydantic model.

    Returns ``None`` when the record carries no defect identity, which is
    the case for non-SC views and older materialized parquet rows.
    """
    if isinstance(record, dict):
        val = record.get("defect_id")
        return str(val) if val else None
    if hasattr(record, "defect_id"):
        val = getattr(record, "defect_id")
        return str(val) if val else None
    return None


def _extract_sample_id(record: Any, fallback_idx: int) -> str:
    """Extract ``sample_id`` from a record or view row."""
    if isinstance(record, dict):
        return str(record.get("sample_id", f"idx_{fallback_idx}"))
    if hasattr(record, "sample_id"):
        return str(getattr(record, "sample_id"))
    return f"idx_{fallback_idx}"


def _extract_image_bytes(
    record: Any,
    role: str,
    artifact_storage: Any = None,
) -> bytes:
    """Extract image bytes for *role* (``"defective"`` or ``"reference"``).

    Resolution order:
    1. Embedded bytes column (``{role}_bytes``) — materialized runtime parquet
    2. URI column (``{role}_uri``) — decoded via :func:`_decode_image_uri`
    3. :class:`ScPatchImageV1Row` ``images`` list — resolved by *role*
       through :func:`_decode_image_uri`
    """
    bytes_key = f"{role}_bytes"
    uri_key = f"{role}_uri"

    # ── Path 1: embedded bytes (materialized) ────────────────────────
    if isinstance(record, dict):
        val = record.get(bytes_key)
        if val is not None and isinstance(val, bytes):
            return val
        uri = record.get(uri_key)
        if uri and isinstance(uri, str):
            return _decode_image_uri(uri)

    # ── Path 2: ScPatchImageV1Row with images list ────────────────────
    images_raw = getattr(record, "images", None)
    if isinstance(images_raw, list):
        for img_ref in images_raw:
            img_role = getattr(img_ref, "role", "")
            if _role_matches(img_role, role):
                img_bytes = getattr(img_ref, "bytes", None)
                if img_bytes is not None and isinstance(img_bytes, bytes):
                    return img_bytes
                url = getattr(img_ref, "url", "")
                if url:
                    return _decode_image_uri(url)

    # ── Fallback: non-materialized path without image refs ───────────
    raise ValueError(
        f"Cannot resolve {role}_bytes for record "
        f"{_extract_sample_id(record, 0)!r}. "
        "Ensure a materialized runtime parquet or view projection with "
        "embedded bytes is used for training."
    )


def _role_matches(img_role: str, requested: str) -> bool:
    """Check whether *img_role* satisfies the requested image *role*.

    SC v2 shards use ``"review"`` for defective images and
    ``"patch_template"`` for reference images.  This helper maps the
    trainer's canonical ``"defective"`` / ``"reference"`` names to the
    role strings used in sparse shards.
    """
    if img_role == requested:
        return True
    if requested == "defective" and img_role in ("review", "patch_defective"):
        return True
    if requested == "reference" and img_role in (
        "template",
        "patch_template",
        "reference_diff",
    ):
        return True
    return False
