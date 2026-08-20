from __future__ import annotations

from pathlib import Path

import pytest

from klarf import (
    Klarf12Builder,
    Klarf12ImageList,
    KlarfParseError,
    KlarfSymbol,
    KlarfValidationError,
    UnsupportedKlarfVersionError,
    dump12,
    dumps12,
    load12,
    loads12,
)

SAMPLE_KLARF_12 = """
FileVersion 1 2;
FileTimestamp 08-03-2026 09:30:00;
InspectionStationID "KLA" "MODEL" "TOOL-01";
SampleType WAFER;
LotID "LOT-01";
WaferID "W01";
ClassLookup 2
0 "Unclassified"
1 "Particle";
SampleTestPlan 2
-1 0
0 0;
DefectRecordSpec 6 DEFECTID XREL YREL CLASSNUMBER IMAGECOUNT IMAGELIST;
DefectList
1 125.5 210.25 1 2 2 1 0 2 1
2 301.0 411.5 0 0 0;
SummarySpec 5 TESTNO NDEFECT DEFDENSITY NDIE NDEFDIE;
SummaryList
1 2 0.25 2 2;
EndOfFile;
"""


def test_loads12_parses_flat_records_counted_lists_and_spec_tables() -> None:
    document = loads12(SAMPLE_KLARF_12)

    assert document.version == (1, 2)
    assert document.find_records("SampleType")[0].values == (KlarfSymbol("WAFER"),)
    assert document.find_counted_lists("ClassLookup")[0].rows == (
        (0, "Unclassified"),
        (1, "Particle"),
    )
    assert document.find_counted_lists("SampleTestPlan")[0].rows == (
        (-1, 0),
        (0, 0),
    )

    defects = document.find_tables("DefectList")[0].as_dicts()
    assert defects[0]["DEFECTID"] == 1
    assert defects[0]["IMAGELIST"] == Klarf12ImageList(items=((1, 0), (2, 1)))
    assert defects[1]["IMAGELIST"] == Klarf12ImageList(items=())
    assert document.find_tables("SummaryList")[0].rows == ((1, 2, 0.25, 2, 2),)


def test_dumps12_round_trips_semantically() -> None:
    document = loads12(SAMPLE_KLARF_12)

    rendered = dumps12(document)

    assert rendered.startswith("FileVersion 1 2;\n")
    assert rendered.endswith("EndOfFile;\n")
    assert loads12(rendered) == document


def test_klarf12_builder_round_trip() -> None:
    document = (
        Klarf12Builder((1, 2))
        .add_record("SampleType", KlarfSymbol("WAFER"))
        .add_record("LotID", "LOT-01")
        .add_counted_list(
            "ClassLookup",
            rows=((0, "Unclassified"), (1, "Particle")),
        )
        .add_schema(
            "DefectRecordSpec",
            "DEFECTID",
            "XREL",
            "IMAGECOUNT",
            "IMAGELIST",
        )
        .add_table(
            "DefectList",
            schema_name="DefectRecordSpec",
            rows=(
                (1, 125.5, 1, Klarf12ImageList(items=((1, 0),))),
                (2, 301.0, 0, Klarf12ImageList(items=())),
            ),
        )
        .build()
    )

    assert loads12(dumps12(document)) == document


def test_load12_and_dump12_path_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "source-12.klarf"
    destination = tmp_path / "destination-12.klarf"
    source.write_text(SAMPLE_KLARF_12, encoding="utf-8")

    document = load12(source)
    dump12(document, destination)

    assert load12(destination) == document


def test_parser_reuses_schema_for_multiple_and_empty_defect_lists() -> None:
    document = loads12(
        """
FileVersion 1 1;
DefectRecordSpec 3 DEFECTID IMAGECOUNT IMAGELIST;
DefectList;
TiffFileName first.tif;
DefectList 1 1 1 9 0;
TiffFileName second.tif;
DefectList 2 0 0;
EndOfFile;
"""
    )

    defect_lists = document.find_tables("DefectList")
    assert document.version == (1, 1)
    assert tuple(len(table.rows) for table in defect_lists) == (0, 1, 1)
    assert defect_lists[1].rows[0][2] == Klarf12ImageList(items=((9, 0),))


@pytest.mark.parametrize(
    ("text", "message"),
    (
        (
            "FileVersion 1 2; DefectRecordSpec 2 A; EndOfFile;",
            "expected 'ATOM', got ';'",
        ),
        (
            "FileVersion 1 2; DefectList; EndOfFile;",
            "requires a preceding 'DefectRecordSpec'",
        ),
        (
            "FileVersion 1 2; DefectRecordSpec 2 A B; DefectList 1; EndOfFile;",
            "ended before column 'B'",
        ),
        (
            "FileVersion 1 2; DefectRecordSpec 3 A IMAGECOUNT IMAGELIST; "
            "DefectList 1 2 1 9 0; EndOfFile;",
            "IMAGECOUNT is 2 but IMAGELIST declares 1",
        ),
        (
            "FileVersion 1 2; ClassLookup 1 0; EndOfFile;",
            "fewer than 2 values",
        ),
    ),
)
def test_loads12_rejects_ambiguous_or_inconsistent_tables(
    text: str,
    message: str,
) -> None:
    with pytest.raises(KlarfParseError, match=message):
        loads12(text)


def test_klarf12_model_rejects_image_count_mismatch() -> None:
    with pytest.raises(KlarfValidationError, match="contains 1 items"):
        (
            Klarf12Builder((1, 2))
            .add_schema(
                "DefectRecordSpec",
                "DEFECTID",
                "IMAGECOUNT",
                "IMAGELIST",
            )
            .add_table(
                "DefectList",
                schema_name="DefectRecordSpec",
                rows=((1, 2, Klarf12ImageList(items=((1, 0),))),),
            )
        )


def test_loads12_rejects_hierarchical_18_and_unknown_flat_versions() -> None:
    with pytest.raises(UnsupportedKlarfVersionError, match="1.8"):
        loads12('Record FileRecord "1.8" {} EndOfFile;')
    with pytest.raises(UnsupportedKlarfVersionError, match="1.3"):
        loads12("FileVersion 1 3; EndOfFile;")
