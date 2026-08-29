from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import math

from .artifacts import InspectionArtifactPublisher
from .domain import DefectDraft, InspectionDraft, InspectionKey, InspectionRecord
from .repository import (
    SimulatorRecordNotFoundError,
    SimulatorRepository,
    SimulatorStateError,
)


@dataclass(frozen=True)
class ShowcaseScenario:
    inspection_time: datetime
    published_at: datetime
    total_defects: int
    imaged_defects: int
    images_per_defect: int
    gallery_defects: int
    gallery_imaged_defects: int
    defects_per_archive: int
    append_batch_size: int


@dataclass(frozen=True)
class ScenarioInspectionResult:
    inspection: InspectionRecord
    reused: bool


@dataclass(frozen=True)
class ScenarioResult:
    inspections: tuple[ScenarioInspectionResult, ...]


@dataclass(frozen=True)
class _InspectionSpec:
    wafer_key: int
    lot_id: str
    wafer_id: str
    layer_id: str
    device: str
    total_defects: int
    imaged_defects: int
    images_per_defect: int
    patch_bit_depth: int
    reference_count: int
    difference_count: int


class ShowcaseScenarioRunner:
    def __init__(
        self,
        *,
        repository: SimulatorRepository,
        artifacts: InspectionArtifactPublisher,
    ) -> None:
        self._repository = repository
        self._artifacts = artifacts

    async def publish(self, scenario: ShowcaseScenario) -> ScenarioResult:
        self._validate(scenario)
        specs = (
            _InspectionSpec(
                wafer_key=1,
                lot_id="A123456",
                wafer_id="24",
                layer_id="LAYER-M1",
                device="DEVICE-DEMO-A",
                total_defects=scenario.total_defects,
                imaged_defects=scenario.imaged_defects,
                images_per_defect=scenario.images_per_defect,
                patch_bit_depth=12,
                reference_count=2,
                difference_count=2,
            ),
            _InspectionSpec(
                wafer_key=81,
                lot_id="GALLERY-VQA",
                wafer_id="GRAY8-1R1D",
                layer_id="LAYER-GRAY8",
                device="DEVICE-GALLERY-VQA",
                total_defects=scenario.gallery_defects,
                imaged_defects=scenario.gallery_imaged_defects,
                images_per_defect=1,
                patch_bit_depth=8,
                reference_count=1,
                difference_count=1,
            ),
            _InspectionSpec(
                wafer_key=82,
                lot_id="GALLERY-VQA",
                wafer_id="GRAY16-1R1D",
                layer_id="LAYER-GRAY16-1X",
                device="DEVICE-GALLERY-VQA",
                total_defects=scenario.gallery_defects,
                imaged_defects=scenario.gallery_imaged_defects,
                images_per_defect=1,
                patch_bit_depth=16,
                reference_count=1,
                difference_count=1,
            ),
            _InspectionSpec(
                wafer_key=83,
                lot_id="GALLERY-VQA",
                wafer_id="GRAY16-2R2D",
                layer_id="LAYER-GRAY16-2X",
                device="DEVICE-GALLERY-VQA",
                total_defects=scenario.gallery_defects,
                imaged_defects=scenario.gallery_imaged_defects,
                images_per_defect=1,
                patch_bit_depth=16,
                reference_count=2,
                difference_count=2,
            ),
        )
        results = []
        for spec in specs:
            results.append(await self._ensure_inspection(scenario, spec))
        return ScenarioResult(inspections=tuple(results))

    async def _ensure_inspection(
        self,
        scenario: ShowcaseScenario,
        spec: _InspectionSpec,
    ) -> ScenarioInspectionResult:
        key = InspectionKey(
            wafer_key=spec.wafer_key,
            inspection_time=scenario.inspection_time,
        )
        try:
            existing = await self._repository.get_inspection(key)
        except SimulatorRecordNotFoundError:
            existing = None
        if existing is not None:
            if existing.state != "published":
                raise SimulatorStateError(
                    "showcase inspection exists as a draft; inspect and resolve it "
                    "before replaying the scenario"
                )
            await self._validate_existing(
                existing,
                spec,
                defects_per_archive=scenario.defects_per_archive,
            )
            return ScenarioInspectionResult(inspection=existing, reused=True)

        await self._repository.create_draft(self._inspection_draft(key, spec))
        published_artifacts = await asyncio.to_thread(
            self._artifacts.publish,
            wafer_key=spec.wafer_key,
            inspection_time=scenario.inspection_time,
            total_defects=spec.total_defects,
            imaged_defects=spec.imaged_defects,
            images_per_defect=spec.images_per_defect,
            defects_per_archive=scenario.defects_per_archive,
            patch_bit_depth=spec.patch_bit_depth,
            reference_count=spec.reference_count,
            difference_count=spec.difference_count,
        )
        await self._repository.append_records(
            key,
            defects=(),
            review_images=published_artifacts.review_images,
            patch_archives=published_artifacts.patch_archives,
        )
        for start in range(1, spec.total_defects + 1, scenario.append_batch_size):
            end = min(start + scenario.append_batch_size, spec.total_defects + 1)
            await self._repository.append_records(
                key,
                defects=tuple(
                    self._defect(spec, defect_id) for defect_id in range(start, end)
                ),
                review_images=(),
                patch_archives=(),
            )
        await self._repository.publish(key, published_at=scenario.published_at)
        return ScenarioInspectionResult(
            inspection=await self._repository.get_inspection(key),
            reused=False,
        )

    async def _validate_existing(
        self,
        existing: InspectionRecord,
        spec: _InspectionSpec,
        *,
        defects_per_archive: int,
    ) -> None:
        expected = (spec.lot_id, spec.wafer_id, spec.layer_id, spec.device)
        actual = (
            existing.lot_id,
            existing.wafer_id,
            existing.layer_id,
            existing.device,
        )
        if actual != expected:
            raise SimulatorStateError(
                "published showcase inspection conflicts with the requested scenario"
            )
        counts = await self._repository.child_counts(existing.key)
        expected_counts = (
            spec.total_defects,
            min(spec.total_defects, spec.imaged_defects) * spec.images_per_defect,
            math.ceil(spec.total_defects / defects_per_archive),
        )
        if (
            counts.defects != expected_counts[0]
            or counts.review_images != expected_counts[1]
        ):
            raise SimulatorStateError(
                "published showcase inspection has different defect or review-image counts"
            )
        if counts.patch_archives != expected_counts[2]:
            raise SimulatorStateError(
                "published showcase inspection has a different archive count"
            )

    @staticmethod
    def _inspection_draft(key: InspectionKey, spec: _InspectionSpec) -> InspectionDraft:
        return InspectionDraft(
            key=key,
            lot_id=spec.lot_id,
            wafer_id=spec.wafer_id,
            layer_id=spec.layer_id,
            device=spec.device,
            inspect_equip_id="EQ-TOOL-A1",
            recipe_key=1,
            recipe_id="RECIPE-STD-001",
            origin_index_x=0,
            origin_index_y=0,
            center_x=150_000_000,
            center_y=150_000_000,
            origin_x=145_000_000,
            origin_y=145_000_000,
            die_size_x=8_000_000,
            die_size_y=5_000_000,
            defects=(),
            review_images=(),
            patch_archives=(),
        )

    @staticmethod
    def _defect(spec: _InspectionSpec, defect_id: int) -> DefectDraft:
        die_x = defect_id % 7 - 3
        die_y = (defect_id // 7) % 7 - 3
        wafer_x = 150_000_000 + die_x * 8_000_000 + defect_id % 2_000_000
        wafer_y = 150_000_000 + die_y * 5_000_000 + defect_id % 1_000_000
        size_x = 50 + defect_id % 451
        size_y = 50 + (defect_id * 7) % 451
        class_number = defect_id % 3
        return DefectDraft(
            defect_id=defect_id,
            test_id=defect_id % 1000 + 1,
            class_number=class_number,
            rough_bin=class_number or 1,
            wafer_x=wafer_x,
            wafer_y=wafer_y,
            index_x=int((wafer_x - 145_000_000) / 8_000_000),
            index_y=int((wafer_y - 145_000_000) / 5_000_000),
            adder=0,
            cluster=0,
            images=spec.images_per_defect if defect_id <= spec.imaged_defects else 0,
            size_x=size_x,
            size_y=size_y,
            size_d=int(math.sqrt(size_x**2 + size_y**2)),
            area=size_x * size_y,
            final_bin=defect_id % 256,
            manual_bin=(defect_id * 3) % 256,
            kill_ratio=round((defect_id % 1000) / 1000, 3),
        )

    @staticmethod
    def _validate(scenario: ShowcaseScenario) -> None:
        if scenario.published_at < scenario.inspection_time:
            raise ValueError("published_at must not precede inspection_time")
        positive = {
            "total_defects": scenario.total_defects,
            "images_per_defect": scenario.images_per_defect,
            "gallery_defects": scenario.gallery_defects,
            "defects_per_archive": scenario.defects_per_archive,
            "append_batch_size": scenario.append_batch_size,
        }
        for name, value in positive.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if scenario.imaged_defects < 0 or scenario.gallery_imaged_defects < 0:
            raise ValueError("imaged defect counts cannot be negative")
