from __future__ import annotations

from urllib.parse import quote


def infer_dataset_type(task_type: str) -> str:
    return "image_classification"


def make_ls_image_url(uri: str) -> str:
    """Convert platform image URI to LS-accessible URL."""
    if uri.startswith(("s3://", "memory://")):
        return f"/api/v1/images/resolve?uri={quote(uri, safe='')}"
    return uri


_infer_dataset_type = infer_dataset_type
_make_ls_image_url = make_ls_image_url
