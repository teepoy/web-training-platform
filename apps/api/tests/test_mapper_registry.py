from __future__ import annotations

import pytest

from app.core.mapper_registry import MapperRegistry


class _FakeSrc:
    pass


class _FakeDst:
    pass


# ── Registry instance ──────────────────────────────────────────────────


@pytest.fixture
def fresh_registry() -> MapperRegistry:
    return MapperRegistry()


# ── test_register_and_get_by_type ──────────────────────────────────────


def test_register_and_get_by_type(fresh_registry: MapperRegistry) -> None:
    @fresh_registry.register([_FakeSrc], [_FakeDst])
    def convert(src: _FakeSrc) -> _FakeDst:
        return _FakeDst()

    fn = fresh_registry.get_mapper(_FakeSrc, _FakeDst)
    result = fn(_FakeSrc())
    assert isinstance(result, _FakeDst)


# ── test_register_and_get_by_string ────────────────────────────────────


def test_register_and_get_by_string(fresh_registry: MapperRegistry) -> None:
    @fresh_registry.register(["from_id"], ["to_id"])
    def convert(obj: object) -> str:
        return str(obj)

    fn = fresh_registry.get_mapper("from_id", "to_id")
    assert fn(42) == "42"


# ── test_register_and_get_by_mixed_type_and_string ─────────────────────


def test_register_and_get_by_mixed_type_and_string(
    fresh_registry: MapperRegistry,
) -> None:
    @fresh_registry.register([_FakeSrc, "from_str"], [_FakeDst, "to_str"])
    def convert(src: _FakeSrc) -> _FakeDst:
        return _FakeDst()

    # Type → Type
    fn1 = fresh_registry.get_mapper(_FakeSrc, _FakeDst)
    assert callable(fn1)

    # Type → String
    fn2 = fresh_registry.get_mapper(_FakeSrc, "to_str")
    assert callable(fn2)

    # String → Type
    fn3 = fresh_registry.get_mapper("from_str", _FakeDst)
    assert callable(fn3)

    # String → String
    fn4 = fresh_registry.get_mapper("from_str", "to_str")
    assert callable(fn4)

    # All return the same function
    assert fn1 is fn2 is fn3 is fn4


# ── test_cartesian_product_registration ────────────────────────────────


def test_cartesian_product_registration(fresh_registry: MapperRegistry) -> None:
    @fresh_registry.register([_FakeSrc, "id_a"], [_FakeDst, "id_b"])
    def convert(src: _FakeSrc) -> _FakeDst:
        return _FakeDst()

    # 2 × 2 = 4 keys
    fn1 = fresh_registry.get_mapper(_FakeSrc, _FakeDst)
    fn2 = fresh_registry.get_mapper(_FakeSrc, "id_b")
    fn3 = fresh_registry.get_mapper("id_a", _FakeDst)
    fn4 = fresh_registry.get_mapper("id_a", "id_b")

    assert fn1 is fn2 is fn3 is fn4


# ── test_duplicate_registration_raises ─────────────────────────────────


def test_duplicate_registration_raises(fresh_registry: MapperRegistry) -> None:
    @fresh_registry.register([_FakeSrc], [_FakeDst])
    def convert_first(src: _FakeSrc) -> _FakeDst:
        return _FakeDst()

    with pytest.raises(ValueError) as exc_info:

        @fresh_registry.register([_FakeSrc], [_FakeDst])
        def convert_second(src: _FakeSrc) -> _FakeDst:
            return _FakeDst()

    assert "Duplicate" in str(exc_info.value)


# ── test_duplicate_via_cartesian_product ───────────────────────────────


def test_duplicate_via_cartesian_product(
    fresh_registry: MapperRegistry,
) -> None:
    @fresh_registry.register([_FakeSrc, "src_id"], [_FakeDst])
    def convert_first(src: _FakeSrc) -> _FakeDst:
        return _FakeDst()

    with pytest.raises(ValueError) as exc_info:

        @fresh_registry.register([_FakeSrc], [_FakeDst, "dst_id"])
        def convert_second(src: _FakeSrc) -> _FakeDst:
            return _FakeDst()

    assert "Duplicate" in str(exc_info.value)


# ── test_missing_mapper_raises ─────────────────────────────────────────


def test_missing_mapper_raises(fresh_registry: MapperRegistry) -> None:
    with pytest.raises(KeyError) as exc_info:
        fresh_registry.get_mapper(_FakeSrc, _FakeDst)

    assert "No mapper registered" in str(exc_info.value)


# ── test_resolve_key_for_type ──────────────────────────────────────────


def test_resolve_key_for_type(fresh_registry: MapperRegistry) -> None:
    key = fresh_registry._resolve_key(_FakeSrc)
    assert "test_mapper_registry" in key
    assert "_FakeSrc" in key


# ── test_resolve_key_for_string ────────────────────────────────────────


def test_resolve_key_for_string(fresh_registry: MapperRegistry) -> None:
    key = fresh_registry._resolve_key("plain_string")
    assert key == "plain_string"


# ── Integration: real mappers exist after side-effect imports ──────────


def test_real_mappers_are_registered() -> None:
    from app.core.mapper_registry import mapper

    from app.modules.sc.models import PatchSample
    from app.modules.sc.views.patch_image.v1.schemas import ScPatchImageV1Row

    # Type-based lookup
    fn = mapper.get_mapper(PatchSample, ScPatchImageV1Row)
    assert callable(fn)

    # String-based (ClassVar) lookup
    fn2 = mapper.get_mapper(PatchSample.ID, ScPatchImageV1Row.view_id)
    assert callable(fn2)
    assert fn is fn2


def test_real_mappers_from_sample() -> None:
    from app.core.mapper_registry import mapper
    from app.shared.api.schemas import Sample

    from app.modules.sc.models import PatchSample
    from app.modules.datasets.classification.models import ClassificationSample
    from app.modules.datasets.detection.models import DetectionSample
    from app.modules.datasets.vqa.models import VQASample

    for cls in [PatchSample, ClassificationSample, DetectionSample, VQASample]:
        fn = mapper.get_mapper(Sample, cls)
        assert callable(fn)

        fn_str = mapper.get_mapper(Sample, cls.ID)
        assert callable(fn_str)
        assert fn is fn_str


def test_real_mappers_to_sample() -> None:
    from app.core.mapper_registry import mapper
    from app.shared.api.schemas import Sample

    from app.modules.sc.models import PatchSample
    from app.modules.datasets.classification.models import ClassificationSample
    from app.modules.datasets.detection.models import DetectionSample
    from app.modules.datasets.vqa.models import VQASample

    for cls in [PatchSample, ClassificationSample, DetectionSample, VQASample]:
        fn = mapper.get_mapper(cls, Sample)
        assert callable(fn)

        fn_str = mapper.get_mapper(cls.ID, Sample)
        assert callable(fn_str)
        assert fn is fn_str


def test_real_mappers_to_view() -> None:
    from app.core.mapper_registry import mapper

    from app.modules.datasets.classification.models import ClassificationSample
    from app.modules.datasets.views.labeled_image.v1.schemas import (
        LabeledImageV1Row,
    )

    fn = mapper.get_mapper(ClassificationSample, LabeledImageV1Row)
    assert callable(fn)

    fn2 = mapper.get_mapper(
        ClassificationSample.ID, "labeled_image_v1"
    )
    assert callable(fn2)
    assert fn is fn2


def test_real_mapper_conversion_produces_correct_output() -> None:
    from app.core.mapper_registry import mapper

    from app.modules.datasets.classification.models import ClassificationSample
    from app.modules.datasets.views.labeled_image.v1.schemas import (
        LabeledImageV1Row,
    )

    sample = ClassificationSample(
        sample_id="s1",
        image_uris=["http://img/a.jpg"],
        label="cat",
    )
    fn = mapper.get_mapper(ClassificationSample, LabeledImageV1Row)
    result = fn(sample)
    assert isinstance(result, LabeledImageV1Row)
    assert result.sample_id == "s1"
    assert result.label == "cat"


def test_real_mapper_from_sample_conversion() -> None:
    from app.core.mapper_registry import mapper
    from app.shared.api.schemas import Sample

    from app.modules.datasets.classification.models import ClassificationSample

    transport = Sample(
        id="s-from",
        dataset_id="ds-1",
        image_uris=["http://img/b.jpg"],
        metadata={"question": "what?"},
    )
    fn = mapper.get_mapper(Sample, ClassificationSample)
    result = fn(transport)
    assert isinstance(result, ClassificationSample)
    assert result.sample_id == "s-from"
    assert result.image_uris == ["http://img/b.jpg"]


def test_real_mapper_patch_sample_v1_conversion() -> None:
    import datetime

    from app.core.mapper_registry import mapper

    from app.modules.sc.models import PatchSample
    from app.modules.sc.views.patch_image.v1.schemas import ScPatchImageV1Row

    ps = PatchSample(
        sample_id="ps-1",
        inspection_time=datetime.datetime(2024, 1, 15, 12, 0, 0),
        wafer_key=42,
        defect_id="d001",
        wafer_x=10,
        wafer_y=20,
        rough_bin=3,
        class_number=5,
        label="scratch",
    )
    fn = mapper.get_mapper(PatchSample, ScPatchImageV1Row)
    result = fn(ps)
    assert isinstance(result, ScPatchImageV1Row)
    assert result.sample_id == "ps-1"
    assert result.wafer_key == 42
    assert result.defect_id == "d001"
    assert result.label == "scratch"
