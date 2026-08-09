from __future__ import annotations

from app.modules.sc.data_provider.schemas import (
    ScSampleTableColumnDescriptor,
    ScSampleTableDescriptor,
)


def _column(
    key: str,
    title: str,
    *,
    width: int = 120,
    filter: str | None,
    visibility: str = "default",
    format: str = "plain",
) -> ScSampleTableColumnDescriptor:
    return ScSampleTableColumnDescriptor.model_validate(
        {
            "key": key,
            "title": title,
            "width": width,
            "filter": filter,
            "visibility": visibility,
            "format": format,
        }
    )


SC_SAMPLE_TABLE_DESCRIPTOR = ScSampleTableDescriptor(
    version="sc.sample-table.v1",
    columns=(
        _column("defect_id", "Defect ID", width=130, filter="set", format="integer"),
        _column("row_key", "Sample ID", width=260, filter="set"),
        _column("images", "Images", width=110, filter="range"),
        _column("test_id", "Test ID", filter="set"),
        _column("index_x", "Index X", filter="range"),
        _column("index_y", "Index Y", filter="range"),
        _column("wafer_x", "Wafer X", filter="range"),
        _column("wafer_y", "Wafer Y", filter="range"),
        _column("die_x", "Die X", filter="range"),
        _column("die_y", "Die Y", filter="range"),
        _column("size_x", "Size X", filter="range"),
        _column("size_y", "Size Y", filter="range"),
        _column("size_d", "Size D", filter="range"),
        _column("area", "Area", filter="range"),
        _column("class_number", "Class", filter="set"),
        _column("rough_bin", "Rough Bin", filter="set"),
        _column("final_bin", "Final Bin", filter="set"),
        _column("manual_bin", "Manual Bin", filter="set"),
        _column("adder", "Adder", filter="set"),
        _column("cluster_id", "Cluster ID", filter="set"),
        _column("kill_ratio", "Kill Ratio", filter="range", format="fixed_3"),
        _column(
            "annotation_label",
            "Annotation",
            width=140,
            filter="set",
            visibility="reclassify",
        ),
        _column(
            "prediction_label",
            "Prediction",
            width=140,
            filter="set",
            visibility="reclassify",
        ),
        _column(
            "prediction_confidence",
            "Confidence",
            width=130,
            filter="range",
            visibility="reclassify",
            format="fixed_3",
        ),
        _column(
            "final_class",
            "Final Class",
            filter="set",
            visibility="filter_only",
        ),
        _column("map_id", "Map ID", filter=None, visibility="internal"),
        _column("sample_id", "Sample ID", filter=None, visibility="internal"),
        _column(
            "source_sample_id",
            "Source Sample ID",
            filter=None,
            visibility="internal",
        ),
        _column(
            "collection_member_id",
            "Collection Member ID",
            filter=None,
            visibility="internal",
        ),
        _column(
            "review_image_ids_json",
            "Review Image IDs",
            filter=None,
            visibility="internal",
        ),
    ),
)
