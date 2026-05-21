from __future__ import annotations

from typing import Any

from app.modules.preview.domain.entities.preview import PreviewItem
from app.modules.datasets.domain.entities import schema_registry
from app.modules.datasets.domain.entities.dataset_schema import DatasetSchema


def _generate_ls_config(label_space: list[str]) -> str:
    return (
        "<View>\n"
        '  <Image name="image" value="$image"/>\n'
        '  <Text name="question" value="$question"/>\n'
        '  <TextArea name="answer" toName="image" perRegion="false" rows="4"/>\n'
        "</View>"
    )


def _platform_annotation_to_ls(
    label: str, annotation_value: Any
) -> list[dict[str, Any]]:
    text = annotation_value if isinstance(annotation_value, str) else label
    return [
        {
            "from_name": "answer",
            "to_name": "image",
            "type": "textarea",
            "value": {"text": [text]},
        }
    ]


def _ls_annotation_to_platform(ls_results: list[dict[str, Any]]) -> tuple[str, Any]:
    for item in ls_results:
        if item.get("type") == "textarea":
            texts = item.get("value", {}).get("text", [])
            if texts:
                return texts[0], None
    return "", None


def _mock_item_generator(index: int, label_space: list[str]) -> PreviewItem:
    questions = [
        "What is shown in this image?",
        "Describe the main subject.",
        "What color is the dominant object?",
    ]
    return PreviewItem(
        upstream_item_id=f"vqa-{index}",
        image_uris=[f"https://picsum.photos/seed/vqa{index}/400/300"],
        metadata={"index": index, "question": questions[index % len(questions)]},
    )


SCHEMA = DatasetSchema(
    dataset_type="image_vqa",
    task_type="vqa",
    annotation_type="text",
    label_space_mode="forbidden",
    generate_ls_config=_generate_ls_config,
    platform_annotation_to_ls=_platform_annotation_to_ls,
    ls_annotation_to_platform=_ls_annotation_to_platform,
    mock_item_generator=_mock_item_generator,
)

schema_registry.register(SCHEMA)
