from __future__ import annotations

from importlib import import_module

from app.modules.types import catalog


def register_catalog_view_rows() -> None:
    """Import each explicitly declared view row module exactly once."""

    for definition in catalog.list_views():
        module_path, separator, _ = definition.row_type_path.partition(":")
        if not separator or not module_path:
            raise RuntimeError(
                f"View {definition.id!r} has invalid row_type_path "
                f"{definition.row_type_path!r}; expected 'module:symbol'"
            )
        import_module(module_path)


register_catalog_view_rows()
