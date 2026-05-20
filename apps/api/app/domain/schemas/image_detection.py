from __future__ import annotations

from typing import Any

from app.domain.dataset_schema import DatasetSchema
from app.domain.preview import PreviewItem
from app.domain import schema_registry


def _generate_ls_config(label_space: list[str]) -> str:
    labels_xml = "\n".join(f'      <Label value="{label}"/>' for label in label_space)
    return (
        "<View>\n"
        '  <Image name="image" value="$image"/>\n'
        '  <RectangleLabels name="boxes" toName="image">\n'
        f"{labels_xml}\n"
        "  </RectangleLabels>\n"
        "</View>"
    )


def _platform_annotation_to_ls(
    label: str, annotation_value: Any
) -> list[dict[str, Any]]:
    """Convert a list of detection boxes to LS rectanglelabels results."""
    boxes: list[dict[str, Any]] = (
        annotation_value if isinstance(annotation_value, list) else []
    )
    results: list[dict[str, Any]] = []
    for box in boxes:
        results.append(
            {
                "from_name": "boxes",
                "to_name": "image",
                "type": "rectanglelabels",
                "value": {
                    "x": box.get("x", 0) * 100,
                    "y": box.get("y", 0) * 100,
                    "width": box.get("width", 0) * 100,
                    "height": box.get("height", 0) * 100,
                    "rectanglelabels": [box.get("label", "")],
                },
            }
        )
    return results


def _ls_annotation_to_platform(ls_results: list[dict[str, Any]]) -> tuple[str, Any]:
    """Extract bounding boxes from LS rectanglelabels results."""
    boxes: list[dict[str, Any]] = []
    for item in ls_results:
        if item.get("type") == "rectanglelabels":
            v = item.get("value", {})
            labels = v.get("rectanglelabels", [])
            boxes.append(
                {
                    "label": labels[0] if labels else "",
                    "x": v.get("x", 0) / 100,
                    "y": v.get("y", 0) / 100,
                    "width": v.get("width", 0) / 100,
                    "height": v.get("height", 0) / 100,
                }
            )
    return "", boxes if boxes else None


def _mock_item_generator(index: int, label_space: list[str]) -> PreviewItem:
    labels = label_space or ["object"]
    label = labels[index % len(labels)]
    # Deterministic but varied box positions
    x = (index * 13 % 60) / 100
    y = (index * 17 % 60) / 100
    return PreviewItem(
        upstream_item_id=f"det-{index}",
        image_uris=[f"https://picsum.photos/seed/det{index}/640/480"],
        metadata={
            "width": 640,
            "height": 480,
            "boxes": [
                {"label": label, "x": x, "y": y, "width": 0.25, "height": 0.2},
            ],
        },
    )


SCHEMA = DatasetSchema(
    dataset_type="image_detection",
    task_type="detection",
    annotation_type="boxes",
    label_space_mode="required",
    generate_ls_config=_generate_ls_config,
    platform_annotation_to_ls=_platform_annotation_to_ls,
    ls_annotation_to_platform=_ls_annotation_to_platform,
    mock_item_generator=_mock_item_generator,
    metadata_schema={
        "width": {"type": "number", "label": "Image width (px)"},
        "height": {"type": "number", "label": "Image height (px)"},
        "boxes": {"type": "json", "label": "Bounding boxes"},
    },
)

schema_registry.register(SCHEMA)
