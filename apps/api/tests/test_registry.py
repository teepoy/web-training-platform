from __future__ import annotations

from copy import deepcopy

from app.core.registry import (
    DatasetTypeRegistration,
    _dataset_type_registry,
    dataset,
    get_dataset_adapter,
    list_dataset_types,
    register_dataset_type,
    resolve_task_type,
    resolve_view_types,
    validate_dataset_task,
)


class _RegistrySnapshot:
    def __enter__(self):
        self._saved = deepcopy(_dataset_type_registry)
        return self

    def __exit__(self, *args):
        _dataset_type_registry.clear()
        _dataset_type_registry.update(self._saved)


def save_restore_registry():
    return _RegistrySnapshot()


# ── test_register_dataset_type_success ────────────────────────────────────

def test_register_dataset_type_success() -> None:
    with save_restore_registry():
        key = "fruit_classify"

        reg = DatasetTypeRegistration(
            dataset_type=key,
            view_types=["image_input_v1", "labeled_image_v1"],
            task_type="classify",
            adapter_class=object,
        )
        register_dataset_type(reg)

        stored = _dataset_type_registry.get(key)
        assert stored is not None
        assert stored.dataset_type == key
        assert stored.view_types == ["image_input_v1", "labeled_image_v1"]
        assert stored.task_type == "classify"
        assert stored.adapter_class is object


# ── test_register_duplicate_raises ─────────────────────────────────────────

def test_register_duplicate_raises() -> None:
    with save_restore_registry():
        key = "dupe_type"

        reg = DatasetTypeRegistration(
            dataset_type=key,
            view_types=["image_input_v1"],
            task_type="classify",
            adapter_class=object,
        )
        register_dataset_type(reg)

        try:
            register_dataset_type(reg)
        except ValueError as exc:
            assert f"Dataset type '{key}' is already registered" in str(exc)
        else:
            raise AssertionError("Expected ValueError for duplicate registration")


def test_register_dataset_type_rejects_unknown_view() -> None:
    with save_restore_registry():
        reg = DatasetTypeRegistration(
            dataset_type="unknown_view_type",
            view_types=["missing_view_v1"],
            task_type="classify",
            adapter_class=object,
        )

        try:
            register_dataset_type(reg)
        except ValueError as exc:
            assert "missing_view_v1" in str(exc)
        else:
            raise AssertionError("Expected ValueError for unknown catalog view")


# ── test_dataset_decorator_registers_adapter ───────────────────────────────

def test_dataset_decorator_registers_adapter() -> None:
    with save_restore_registry():
        key = "deco_type"

        @dataset(
            dataset_type=key,
            view_types=["image_input_v1", "box_detection_v1"],
            task_type="detect",
        )
        class FakeAdapter:
            pass

        reg = _dataset_type_registry.get(key)
        assert reg is not None, "Registry should contain the decorated type"
        assert reg.dataset_type == key
        assert reg.view_types == ["image_input_v1", "box_detection_v1"]
        assert reg.task_type == "detect"
        assert reg.adapter_class is FakeAdapter


# ── test_create_adapter_returns_instance ───────────────────────────────────

def test_create_adapter_returns_instance() -> None:
    with save_restore_registry():

        class MyAdapter:
            def __init__(self) -> None:
                self.initialized = True

        key = "create_test"
        reg = DatasetTypeRegistration(
            dataset_type=key,
            view_types=["qa_input_v1"],
            task_type="vqa",
            adapter_class=MyAdapter,
        )
        register_dataset_type(reg)

        adapter = reg.create_adapter()
        assert isinstance(adapter, MyAdapter)
        assert adapter is not MyAdapter  # not the class itself
        assert adapter.initialized is True


# ── test_resolve_view_types_dynamic ────────────────────────────────────────

def test_resolve_view_types_dynamic() -> None:
    with save_restore_registry():

        @dataset(
            dataset_type="dynamic_vqa",
            view_types=["image_input_v1", "qa_input_v1"],
            task_type="vqa",
        )
        class DynAdapter:
            pass

        views = resolve_view_types("dynamic_vqa")
        assert views == ["image_input_v1", "qa_input_v1"]
        assert len(views) == 2


# ── test_resolve_view_types_fallback_to_legacy ─────────────────────────────

def test_resolve_view_types_fallback_to_legacy() -> None:
    with save_restore_registry():
        # Falls back to hardcoded _dataset_view_types dict for known types
        views = resolve_view_types("image_classification")
        assert len(views) > 0
        assert "image_input_v1" in views

        # Unknown types return empty list
        assert resolve_view_types("nonexistent_xyz") == []


# ── test_get_dataset_adapter_unknown_returns_none ──────────────────────────

def test_get_dataset_adapter_unknown_returns_none() -> None:
    with save_restore_registry():
        result = get_dataset_adapter("nonexistent_type")
        assert result is None


# ── test_validate_dataset_task_match ───────────────────────────────────────

def test_validate_dataset_task_match() -> None:
    with save_restore_registry():
        key = "task_validate"

        @dataset(
            dataset_type=key,
            view_types=["labeled_image_v1"],
            task_type="classify",
        )
        class ValAdapter:
            pass

        assert validate_dataset_task(key, "classify") is True
        assert validate_dataset_task(key, "other") is False


# ── test_list_dataset_types ────────────────────────────────────────────────

def test_list_dataset_types() -> None:
    with save_restore_registry():

        register_dataset_type(
            DatasetTypeRegistration(
                dataset_type="type_a",
                view_types=["image_input_v1"],
                task_type="classify",
                adapter_class=object,
            )
        )
        register_dataset_type(
            DatasetTypeRegistration(
                dataset_type="type_b",
                view_types=["image_input_v1", "box_detection_v1"],
                task_type="detect",
                adapter_class=object,
            )
        )

        types = list_dataset_types()
        assert "type_a" in types
        assert "type_b" in types
        assert len(types) >= 5


# ── test_resolve_task_type ─────────────────────────────────────────────────

def test_resolve_task_type() -> None:
    with save_restore_registry():
        key = "task_resolve"

        @dataset(
            dataset_type=key,
            view_types=["box_detection_v1"],
            task_type="detect",
        )
        class TaskAdapter:
            pass

        assert resolve_task_type(key) == "detect"
        assert resolve_task_type("unknown_type") is None
