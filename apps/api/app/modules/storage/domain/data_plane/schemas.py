from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module

import pyarrow as pa

from app.modules.types import catalog

IMAGE_INPUT_V1_SCHEMA = pa.schema(
    [
        pa.field("sample_id", pa.string(), nullable=False),
        pa.field("image_uri", pa.string(), nullable=False),
        pa.field("image_bytes", pa.binary(), nullable=True),
    ]
)

SC_PATCH_IMAGE_V1_SCHEMA = pa.schema(
    [
        pa.field("sample_id", pa.string(), nullable=False),
        pa.field("inspection_time", pa.string(), nullable=False),
        pa.field("wafer_key", pa.int64(), nullable=False),
        pa.field("defect_id", pa.string(), nullable=False),
        pa.field("wafer_x", pa.int64(), nullable=False),
        pa.field("wafer_y", pa.int64(), nullable=False),
        pa.field("die_x", pa.int64(), nullable=True),
        pa.field("die_y", pa.int64(), nullable=True),
        pa.field("rough_bin", pa.int64(), nullable=False),
        pa.field("class_number", pa.int64(), nullable=True),
        pa.field("test_id", pa.int64(), nullable=True),
        pa.field("label", pa.string(), nullable=True),
        pa.field("predicted_label", pa.string(), nullable=True),
        pa.field("confidence", pa.float64(), nullable=True),
        pa.field("patch_template_bytes", pa.binary(), nullable=True),
        pa.field("patch_defective_bytes", pa.binary(), nullable=True),
    ]
)

SC_REVIEW_IMAGE_V1_SCHEMA = pa.schema(
    [
        pa.field("sample_id", pa.string(), nullable=False),
        pa.field("inspection_time", pa.string(), nullable=False),
        pa.field("wafer_key", pa.int64(), nullable=False),
        pa.field("defect_id", pa.string(), nullable=False),
        pa.field("wafer_x", pa.int64(), nullable=False),
        pa.field("wafer_y", pa.int64(), nullable=False),
        pa.field("die_x", pa.int64(), nullable=True),
        pa.field("die_y", pa.int64(), nullable=True),
        pa.field("rough_bin", pa.int64(), nullable=False),
        pa.field("class_number", pa.int64(), nullable=True),
        pa.field("test_id", pa.int64(), nullable=True),
        pa.field("review_image_bytes", pa.list_(pa.binary()), nullable=True),
    ]
)

LABELED_IMAGE_V1_SCHEMA = pa.schema(
    [
        pa.field("sample_id", pa.string(), nullable=False),
        pa.field("image_uri", pa.string(), nullable=False),
        pa.field("image_bytes", pa.binary(), nullable=True),
        pa.field("label", pa.string(), nullable=True),
    ]
)

BOX_DETECTION_V1_SCHEMA = pa.schema(
    [
        pa.field("sample_id", pa.string(), nullable=False),
        pa.field("image_uri", pa.string(), nullable=False),
        pa.field("image_bytes", pa.binary(), nullable=True),
        pa.field(
            "boxes",
            pa.large_list(
                pa.struct(
                    [
                        pa.field("label", pa.string(), nullable=False),
                        pa.field("x", pa.float64(), nullable=False),
                        pa.field("y", pa.float64(), nullable=False),
                        pa.field("width", pa.float64(), nullable=False),
                        pa.field("height", pa.float64(), nullable=False),
                    ]
                )
            ),
            nullable=True,
        ),
        pa.field("width", pa.int64(), nullable=True),
        pa.field("height", pa.int64(), nullable=True),
    ]
)

QA_INPUT_V1_SCHEMA = pa.schema(
    [
        pa.field("sample_id", pa.string(), nullable=False),
        pa.field("image_uri", pa.string(), nullable=False),
        pa.field("image_bytes", pa.binary(), nullable=True),
        pa.field("question", pa.string(), nullable=False),
    ]
)


@dataclass(frozen=True)
class DataPlaneSchemaRegistry:
    schemas: dict[tuple[str, str], pa.Schema]

    @classmethod
    def default(cls) -> DataPlaneSchemaRegistry:
        schemas: dict[tuple[str, str], pa.Schema] = {}
        for view in catalog.list_views():
            schema = _load_arrow_schema(view.arrow_schema_path)
            if view.ref.key in schemas:
                raise ValueError(f"Duplicate data-plane view schema: {view.ref.key!r}")
            schemas[view.ref.key] = schema
        return cls(schemas=schemas)

    def get(self, view_contract: str, view_schema_version: str) -> pa.Schema:
        key = (view_contract, view_schema_version)
        try:
            return self.schemas[key]
        except KeyError as exc:
            raise ValueError(
                f"Unknown data-plane view schema: {view_contract}/{view_schema_version}"
            ) from exc

    def schema_ref(self, view_contract: str, view_schema_version: str) -> str:
        self.get(view_contract, view_schema_version)
        return f"arrow-schema://{view_contract}/{view_schema_version}"


def _load_arrow_schema(symbol_path: str) -> pa.Schema:
    module_name, separator, symbol_name = symbol_path.partition(":")
    if not separator or not module_name or not symbol_name:
        raise ValueError(
            f"Arrow schema path must use 'module:symbol' syntax: {symbol_path!r}"
        )
    schema = getattr(import_module(module_name), symbol_name, None)
    if not isinstance(schema, pa.Schema):
        raise TypeError(f"{symbol_path!r} did not resolve to a pyarrow.Schema")
    return schema
