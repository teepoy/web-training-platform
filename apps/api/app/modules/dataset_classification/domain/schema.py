from __future__ import annotations

from typing import Any

from app.modules.preview.domain.entities.preview import PreviewItem
from app.modules.datasets.domain.entities import schema_registry
from app.modules.datasets.domain.entities.dataset_schema import DatasetSchema


def _generate_ls_config(label_space: list[str]) -> str:
    choices_xml = "\n".join(f'      <Choice value="{label}"/>' for label in label_space)
    return (
        "<View>\n"
        '  <Image name="image" value="$image"/>\n'
        '  <Choices name="classification" toName="image">\n'
        f"{choices_xml}\n"
        "  </Choices>\n"
        "</View>"
    )


def _platform_annotation_to_ls(
    label: str, annotation_value: Any
) -> list[dict[str, Any]]:
    return [
        {
            "from_name": "classification",
            "to_name": "image",
            "type": "choices",
            "value": {"choices": [label]},
        }
    ]


def _ls_annotation_to_platform(ls_results: list[dict[str, Any]]) -> tuple[str, Any]:
    for item in ls_results:
        if item.get("type") == "choices":
            choices = item.get("value", {}).get("choices", [])
            if choices:
                return choices[0], None
    return "", None


def _mock_item_generator(index: int, label_space: list[str]) -> PreviewItem:
    labels = label_space or ["unknown"]
    return PreviewItem(
        upstream_item_id=f"cls-{index}",
        image_uris=[f"https://picsum.photos/seed/cls{index}/400/300"],
        metadata={"index": index, "label": labels[index % len(labels)]},
    )


SCHEMA = DatasetSchema(
    dataset_type="image_classification",
    task_type="classification",
    annotation_type="choice",
    label_space_mode="required",
    generate_ls_config=_generate_ls_config,
    platform_annotation_to_ls=_platform_annotation_to_ls,
    ls_annotation_to_platform=_ls_annotation_to_platform,
    mock_item_generator=_mock_item_generator,
)

schema_registry.register(SCHEMA)
