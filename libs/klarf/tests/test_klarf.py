from __future__ import annotations

from pathlib import Path

import pytest

from klarf import (
    KlarfArray,
    KlarfBuilder,
    KlarfParseError,
    KlarfRecordBuilder,
    KlarfSymbol,
    KlarfValidationError,
    UnsupportedKlarfVersionError,
    dump,
    dumps,
    load,
    loads,
)

SAMPLE_KLARF = """
Record FileRecord "1.8"
{
  Record LotRecord "LOT-01"
  {
    Field SampleType 1 {"WAFER"}
    Record WaferRecord "W01"
    {
      Field SlotNumber 1 {7}
      List DefectList
      {
        Columns 4 { int32 DEFECTID, float XREL, string CLASSNAME, ImageList IMAGEINFO }
        Data 2
        {
          1 125.5 "Particle" Images 1 { "defect-1.tif" "TIFF" 1 "Patch" };
          2 301 "Scratch" N;
        }
      }
    }
  }
  Field FileTimestamp 2 {"2026-08-02", "12:00:00"}
}
EndOfFile;
"""


def test_loads_dynamic_defect_list_and_compound_image_value() -> None:
    document = loads(SAMPLE_KLARF)

    assert document.version == "1.8"
    wafer = document.find_records("WaferRecord")[0]
    assert wafer.find_fields("SlotNumber")[0].values == (7,)

    defects = wafer.find_lists("DefectList")[0]
    rows = defects.as_dicts()
    assert rows[0]["DEFECTID"] == 1
    assert rows[0]["XREL"] == 125.5
    assert rows[0]["IMAGEINFO"] == KlarfArray(
        name="Images",
        items=(("defect-1.tif", "TIFF", 1, "Patch"),),
    )
    assert rows[1]["IMAGEINFO"] == KlarfSymbol("N")


def test_builder_writer_and_loader_round_trip() -> None:
    wafer = (
        KlarfRecordBuilder("WaferRecord", "W01")
        .add_field("SlotNumber", 7)
        .add_list(
            "DefectList",
            columns=(
                ("int32", "DEFECTID"),
                ("float", "XREL"),
                ("ImageList", "IMAGEINFO"),
            ),
            rows=(
                (
                    1,
                    125.5,
                    KlarfArray(
                        "Images",
                        (("defect-1.tif", "TIFF", 1, "Patch"),),
                    ),
                ),
                (2, 301.0, KlarfSymbol("N")),
            ),
        )
    )
    document = (
        KlarfBuilder("1.8")
        .add_record(KlarfRecordBuilder("LotRecord", "LOT-01").add_record(wafer))
        .add_field("FileTimestamp", "2026-08-02", "12:00:00")
        .build()
    )

    rendered = dumps(document)

    assert rendered.endswith("EndOfFile;\n")
    assert loads(rendered) == document


def test_load_and_dump_path_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "source.klarf"
    destination = tmp_path / "destination.klarf"
    source.write_text(SAMPLE_KLARF, encoding="utf-8")

    document = load(source)
    dump(document, destination)

    assert load(destination) == document


@pytest.mark.parametrize(
    ("text", "message"),
    (
        (
            'Record FileRecord "1.8" { Field SlotNumber 2 {1} } EndOfFile;',
            "declares 2 values",
        ),
        (
            'Record FileRecord "1.8" { '
            "List DefectList { Columns 2 { int32 A, int32 B } "
            "Data 1 { 1; } } } EndOfFile;",
            "row has 1 values",
        ),
        (
            'Record FileRecord "1.8" { '
            "List DefectList { Columns 1 { int32 A } "
            "Data 2 { 1; } } } EndOfFile;",
            "declares 2 rows",
        ),
    ),
)
def test_loader_rejects_inconsistent_declared_counts(text: str, message: str) -> None:
    with pytest.raises(KlarfParseError, match=message):
        loads(text)


def test_builder_rejects_rows_that_do_not_match_dynamic_columns() -> None:
    with pytest.raises(KlarfValidationError, match="expected 2"):
        KlarfRecordBuilder("WaferRecord", "W01").add_list(
            "DefectList",
            columns=(("int32", "A"), ("int32", "B")),
            rows=((1,),),
        )


def test_loader_rejects_legacy_12_without_guessing() -> None:
    with pytest.raises(UnsupportedKlarfVersionError, match="1.2"):
        loads("FileVersion 1 2; EndOfFile;")


def test_builder_requires_an_explicit_supported_version() -> None:
    with pytest.raises(UnsupportedKlarfVersionError, match="1.7"):
        KlarfBuilder("1.7")
