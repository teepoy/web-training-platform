# klarf

`klarf` is a zero-dependency loader, immutable object model, writer, and fluent
builder for KLARF text files. It provides separate grammars for flat KLARF 1.1/1.2
and hierarchical KLARF 1.8 so neither parser has to guess the input version.

The 1.8 model keeps record item order and unknown vendor fields while validating
declared field, column, and row counts. The independent 1.2 model preserves flat
record order, resolves `DefectList` and `SummaryList` through their preceding specs,
and validates variable-width `IMAGELIST` values against `IMAGECOUNT`.

## Load a file

```python
from pathlib import Path

from klarf import KlarfList, load

document = load(Path("inspection.klarf"))
wafer = document.find_records("WaferRecord")[0]
defects: KlarfList = wafer.find_lists("DefectList")[0]

for defect in defects.as_dicts():
    print(defect["DEFECTID"], defect["XREL"], defect["YREL"])
```

Use `loads(...)` for in-memory text. Quoted values are returned as `str`, numeric
values as `int` or `float`, unquoted atoms such as `N` as `KlarfSymbol`, and compound
cells such as `Images 2 {...}` as `KlarfArray`.

## Build a file

```python
from klarf import KlarfBuilder, KlarfRecordBuilder, dump

wafer = (
    KlarfRecordBuilder("WaferRecord", "W01")
    .add_field("SlotNumber", 1)
    .add_list(
        "DefectList",
        columns=(("int32", "DEFECTID"), ("float", "XREL")),
        rows=((1, 125.5), (2, 301.0)),
    )
)

document = (
    KlarfBuilder("1.8")
    .add_record(KlarfRecordBuilder("LotRecord", "LOT-01").add_record(wafer))
    .build()
)
dump(document, "inspection.klarf")
```

`dumps(...)` returns deterministic formatted text. Loading the generated text produces
the same model, making builder output straightforward to test.

## KLARF 1.2

Use the explicitly versioned APIs for flat 1.1/1.2 files:

```python
from klarf import Klarf12Builder, Klarf12ImageList, KlarfSymbol, loads12

text = """
FileVersion 1 2;
SampleType WAFER;
DefectRecordSpec 3 DEFECTID IMAGECOUNT IMAGELIST;
DefectList 1 1 1 7 0;
EndOfFile;
"""
document = loads12(text)

defects = document.find_tables("DefectList")[0].as_dicts()
assert defects[0]["IMAGELIST"] == Klarf12ImageList(items=((7, 0),))

built = (
    Klarf12Builder((1, 2))
    .add_record("SampleType", KlarfSymbol("WAFER"))
    .add_schema("DefectRecordSpec", "DEFECTID", "IMAGECOUNT", "IMAGELIST")
    .add_table(
        "DefectList",
        schema_name="DefectRecordSpec",
        rows=((1, 0, Klarf12ImageList(items=())),),
    )
    .build()
)
```

The file helpers are `load12(...)` and `dump12(...)`; the in-memory helpers are
`loads12(...)` and `dumps12(...)`. KLARF 1.1 is accepted because it uses the same flat
grammar, and its original `FileVersion 1 1;` value is preserved by the writer.
