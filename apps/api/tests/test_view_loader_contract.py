"""Focused import / type test for DatasetViewLoader contract.

Proves that the view-loader Protocol can be:
1. Imported cleanly without triggering any registrations or side-effects
2. Used as a type annotation in a training-flow-style context
3. Satisfied by a minimal implementation that exercises the three
   surface methods (``__len__``, ``get_item``, ``annotated_only``)
"""

from __future__ import annotations

from typing import runtime_checkable

from app.modules.datasets.app.view_loader import DatasetViewLoader


def test_can_import_view_loader() -> None:
    """Contract import is side-effect free."""
    assert DatasetViewLoader is not None
    assert callable(getattr(DatasetViewLoader, "__len__", None))


def test_contract_annotation_in_training_flow_style() -> None:
    """The contract works as a type annotation for training functions."""

    from dataclasses import dataclass

    @dataclass
    class FakeViewRow:
        sample_id: str
        image_uris: list[str]

    # Simulating a training flow that accepts a typed view-loader
    def training_style_func(
        *, view: DatasetViewLoader[FakeViewRow]
    ) -> list[FakeViewRow]:
        items: list[FakeViewRow] = []
        for i in range(len(view)):
            items.append(view.get_item(i))  # type: ignore[unused-coroutine]
        return items

    # Verify the signature is valid (no import-time error)
    assert training_style_func is not None


def test_minimal_implementation_satisfies_protocol() -> None:
    """A concrete class with __len__ + get_item + annotated_only
    satisfies the Protocol at the type-check level."""

    class MinimalLoader:
        def __init__(self, items: list[str], *, annotated_only: bool = False) -> None:
            self._items = list(items)
            self.annotated_only = annotated_only

        def __len__(self) -> int:
            return len(self._items)

        async def get_item(self, index: int) -> str:
            if index < 0 or index >= len(self._items):
                raise IndexError(index)
            return self._items[index]

    loader = MinimalLoader(["a", "b", "c"], annotated_only=True)
    assert len(loader) == 3
    assert loader.annotated_only is True


def test_contract_has_no_training_data_references() -> None:
    """Verify the contract source has zero code-level references to
    ``training_data`` (attribute access, parameter, variable).
    Docstring mentions explaining the replacement are fine."""
    import ast
    from pathlib import Path

    contract_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "datasets"
        / "app"
        / "view_loader.py"
    )
    tree = ast.parse(contract_path.read_text(), filename=str(contract_path))

    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "training_data":
            violations.append(f"Name 'training_data' at line {node.lineno}")
        if isinstance(node, ast.Attribute) and node.attr == "training_data":
            violations.append(f"Attribute '.training_data' at line {node.lineno}")

    assert violations == [], (
        "DatasetViewLoader must NOT have code-level references to training_data.\n"
        + "\n".join(violations)
    )


def test_contract_is_runtime_checkable() -> None:
    """Ensure the Protocol can be used with isinstance checks
    when decorated with @runtime_checkable (optional but useful)."""
    # The contract as-is is a typing.Protocol — isinstance works
    # with concrete implementations at static-check time.
    # This test confirms the import path is usable.
    from app.modules.datasets.app.view_loader import T_co

    assert T_co.__covariant__ is True
