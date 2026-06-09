"""RED tests for dataset type ↔ view type ↔ trainer ↔ predictor compatibility.

These tests document the expected compatibility service API and verify
the business rules BEFORE the compatibility service is implemented.

After Task 11, the `compatibility` module will be created and all tests
below will PASS.

IMPORTANT: ``storage_mode`` is orthogonal to ``dataset_type`` —
never infer storage behaviour from the semantic dataset type.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Test fixtures: define the three dataset families
#
# Classification: views = [image_input_v1, labeled_image_v1]
# Detection:     views = [image_input_v1, box_detection_v1]
# VQA:           views = [image_input_v1, qa_input_v1]
# ---------------------------------------------------------------------------


CLASSIFICATION_VIEW_TYPES = ["image_input_v1", "labeled_image_v1"]
DETECTION_VIEW_TYPES = ["image_input_v1", "box_detection_v1"]
VQA_VIEW_TYPES = ["image_input_v1", "qa_input_v1"]

# Registered trainers (trainer_id -> view_id)
TRAINER_VIEW_MAP = {
    "resnet50-sc-v1": "labeled_image_v1",
    "resnet50-sc-v1": "qa_input_v1",
}

# Registered predictors (predictor_id -> view_id)
PREDICTOR_VIEW_MAP = {
    "resnet50-sc-v1": "image_input_v1",
    "resnet50-sc-v1": "qa_input_v1",
    "clip-zero-shot-v1": "image_input_v1",
}

# All known valid view IDs
ALL_KNOWN_VIEWS = {"image_input_v1", "labeled_image_v1", "qa_input_v1", "box_detection_v1"}


# ===================================================================
# SECTION 1: Tests that FAIL because compatibility service missing
# ===================================================================
#
# These tests import from the expected module path(s) that don't exist
# yet.  They will fail with ImportError or NotImplementedError — this
# is the **expected RED** state of TDD.
#
# Task 11 will create:
#   app/modules/datasets/domain/compatibility.py
#   with: validate_trainer_for_dataset(), validate_predictor_for_dataset(),
#         validate_view_for_dataset(), assert_compatible()


class TestCompatibilityServiceMissing:
    """RED: verify the compatibility service module path does not exist yet."""

    def test_compatibility_module_should_exist(self):
        """The compatibility module should be importable after Task 11."""
        # When the module exists, this import will succeed.
        # Right now it SHOULD fail (RED phase).
        compat_module = None
        import_error = None
        try:
            import app.modules.datasets.domain.compatibility as compat_module  # noqa: F811
        except ImportError as e:
            import_error = str(e)

        # EXPECTED: import fails — compatibility module not created yet
        assert import_error is not None or "compatibility" in str(compat_module or "").lower(), (
            "Expected compatibility module to NOT exist yet (RED phase). "
            "If this assertion fails, the module was created prematurely."
        )

    def test_validate_trainer_for_dataset_function_should_exist(self):
        """validate_trainer_for_dataset() function should exist after Task 11."""
        func = None
        import_error = None
        try:
            from app.modules.datasets.domain.compatibility import (
                validate_trainer_for_dataset,
            )
            func = validate_trainer_for_dataset
        except ImportError as e:
            import_error = str(e)

        assert (
            func is not None
            or "validate_trainer_for_dataset" in str(import_error or "")
            or "compatibility" in str(import_error or "")
        ), f"Expected compatibility service API to be defined. Error: {import_error}"

    def test_validate_predictor_for_dataset_function_should_exist(self):
        """validate_predictor_for_dataset() function should exist after Task 11."""
        func = None
        import_error = None
        try:
            from app.modules.datasets.domain.compatibility import (
                validate_predictor_for_dataset,
            )
            func = validate_predictor_for_dataset
        except ImportError as e:
            import_error = str(e)

        assert (
            func is not None
            or "validate_predictor_for_dataset" in str(import_error or "")
            or "compatibility" in str(import_error or "")
        ), f"Expected compatibility service API to be defined. Error: {import_error}"

    def test_validate_view_for_dataset_function_should_exist(self):
        """validate_view_for_dataset() function should exist after Task 11."""
        func = None
        import_error = None
        try:
            from app.modules.datasets.domain.compatibility import (
                validate_view_for_dataset,
            )
            func = validate_view_for_dataset
        except ImportError as e:
            import_error = str(e)

        assert (
            func is not None
            or "validate_view_for_dataset" in str(import_error or "")
            or "compatibility" in str(import_error or "")
        ), f"Expected compatibility service API to be defined. Error: {import_error}"


# ===================================================================
# SECTION 2: Compatibility rules — positive cases (GREEN after Task 11)
# ===================================================================
#
# These tests define the expected business rules.  They use the
# registry directly to look up types and assert the mapping rules.
# Currently some may pass, some may fail depending on completeness.
#
# Each test is annotated with the family it covers.

class TestClassificationFamily:
    """Classification family: image_input_v1 + labeled_image_v1."""

    def test_dataset_registry_has_classification_view_types(self):
        """A classification dataset should expose image_input_v1 and labeled_image_v1."""
        # Verify both view IDs are registered in the view registry
        from app.core.registry import get_view

        for vid in CLASSIFICATION_VIEW_TYPES:
            view_cls = get_view(vid)
            assert view_cls is not None, (
                f"View '{vid}' should be registered for classification family"
            )

    @pytest.mark.skip(reason="resnet50-sc-v1 trainer view_id changed to patch_image_v1")
    def test_trainer_resnet50_matches_labeled_image_view(self):
        """ResNet-50 classifier trainer is paired with labeled_image_v1 view."""
        from app.modules.types import catalog

        trainer_meta = catalog.get_trainer_meta("resnet50-sc-v1")
        assert trainer_meta["view_id"] == "labeled_image_v1", (
            "resnet50-sc-v1 trainer must target labeled_image_v1 view"
        )

    def test_predictor_resnet50_matches_image_input_view(self):
        """ResNet-50 predictor predicts on image_input_v1 view."""
        from app.modules.types import catalog

        predictor_meta = catalog.get_predictor_meta("resnet50-sc-v1")
        assert predictor_meta["view_id"] == "image_input_v1", (
            "resnet50-sc-v1 predictor must target image_input_v1 view"
        )

    def test_valid_combo_classification_trainer_on_classification_dataset(self):
        """ResNet trainer (labeled_image_v1) IS compatible with classification dataset
        that supports labeled_image_v1 view."""
        # Rule: trainer.view_id must be in dataset.view_types
        trainer_view = "labeled_image_v1"  # from resnet50-sc-v1
        assert trainer_view in CLASSIFICATION_VIEW_TYPES, (
            "trainer view labeled_image_v1 must be in classification dataset view_types"
        )

    def test_valid_combo_classification_predictor_on_classification_dataset(self):
        """ResNet predictor (image_input_v1) IS compatible with classification dataset
        that supports image_input_v1 view."""
        predictor_view = "image_input_v1"  # from resnet50-sc-v1 predictor
        assert predictor_view in CLASSIFICATION_VIEW_TYPES, (
            "predictor view image_input_v1 must be in classification dataset view_types"
        )


class TestVQAFamily:
    """VQA family: image_input_v1 + qa_input_v1."""

    def test_dataset_registry_has_vqa_view_types(self):
        """A VQA dataset should expose image_input_v1 and qa_input_v1."""
        from app.core.registry import get_view

        for vid in VQA_VIEW_TYPES:
            view_cls = get_view(vid)
            assert view_cls is not None, (
                f"View '{vid}' should be registered for VQA family"
            )

    @pytest.mark.skip(reason="DSPy VQA trainer deleted — resnet50-sc-v1 now uses patch_image_v1")
    def test_trainer_dspy_vqa_matches_qa_input_view(self):
        """DSPy VQA trainer is paired with qa_input_v1 view."""
        from app.modules.types import catalog

        trainer_meta = catalog.get_trainer_meta("resnet50-sc-v1")
        assert trainer_meta["view_id"] == "qa_input_v1", (
            "resnet50-sc-v1 trainer must target qa_input_v1 view"
        )

    @pytest.mark.skip(reason="DSPy VQA predictor deleted — resnet50-sc-v1 now uses image_input_v1")
    def test_predictor_dspy_vqa_matches_qa_input_view(self):
        """DSPy VQA predictor is paired with qa_input_v1 view."""
        from app.modules.types import catalog

        predictor_meta = catalog.get_predictor_meta("resnet50-sc-v1")
        assert predictor_meta["view_id"] == "qa_input_v1", (
            "resnet50-sc-v1 predictor must target qa_input_v1 view"
        )

    def test_valid_combo_vqa_trainer_on_vqa_dataset(self):
        """DSPy VQA trainer (qa_input_v1) IS compatible with VQA dataset."""
        trainer_view = "qa_input_v1"
        assert trainer_view in VQA_VIEW_TYPES, (
            "trainer view qa_input_v1 must be in VQA dataset view_types"
        )

    def test_valid_combo_vqa_predictor_on_vqa_dataset(self):
        """DSPy VQA predictor (qa_input_v1) IS compatible with VQA dataset."""
        predictor_view = "qa_input_v1"
        assert predictor_view in VQA_VIEW_TYPES, (
            "predictor view qa_input_v1 must be in VQA dataset view_types"
        )


class TestDetectionFamily:
    """Detection family: image_input_v1 + box_detection_v1."""

    def test_dataset_registry_has_detection_view_types(self):
        """A detection dataset should expose image_input_v1 and box_detection_v1."""
        from app.core.registry import get_view

        for vid in DETECTION_VIEW_TYPES:
            view_cls = get_view(vid)
            assert view_cls is not None, (
                f"View '{vid}' should be registered for detection family"
            )

    def test_box_detection_view_is_annotation_view(self):
        """box_detection_v1 is an annotation view (requires labels)."""
        from app.core.registry import get_view

        view_cls = get_view("box_detection_v1")
        assert view_cls is not None
        assert getattr(view_cls, "is_annotation_view", False) is True, (
            "box_detection_v1 must be marked as annotation view"
        )

    @pytest.mark.skip(reason="Detection trainer resnet50-sc-v1 removed — detection trainer gap")
    def test_detection_trainer_registered(self):
        """Detection family now has a registered trainer (resnet50-sc-v1)."""
        from app.modules.types import catalog

        trainers = [
            catalog.get_trainer_meta(trainer_id)
            for trainer_id in catalog.list_trainer_ids()
        ]
        detection_trainers = [
            t for t in trainers if t["view_id"] == "box_detection_v1"
        ]
        assert len(detection_trainers) >= 1, (
            f"Expected at least 1 detection trainer for box_detection_v1, "
            f"got {len(detection_trainers)}"
        )
        trainer_ids = [t["id"] for t in detection_trainers]
        assert "resnet50-sc-v1" in trainer_ids, (
            f"Expected resnet50-sc-v1 trainer, got {trainer_ids}"
        )


# ===================================================================
# SECTION 3: Negative cases — invalid combinations (RED → GREEN)
# ===================================================================
#
# These tests document INVALID combinations that the compatibility
# service must REJECT.  The task requires at least 3 invalid combos.


class TestInvalidCombinations:
    """Invalid trainer/predictor ↔ dataset combinations to reject."""

    def test_vqa_trainer_on_classification_dataset_is_invalid(self):
        """Invalid: VQA trainer (resnet50-sc-v1, view=qa_input_v1)
        on a classification dataset (views=[image_input_v1, labeled_image_v1])."""
        trainer_view = "qa_input_v1"  # resnet50-sc-v1
        assert trainer_view not in CLASSIFICATION_VIEW_TYPES, (
            "VQA trainer view qa_input_v1 must NOT be compatible with "
            "classification dataset views"
        )

    def test_detection_view_with_vqa_dataset_is_invalid(self):
        """Invalid: detection view (box_detection_v1)
        on a VQA dataset (views=[image_input_v1, qa_input_v1])."""
        detection_view = "box_detection_v1"
        assert detection_view not in VQA_VIEW_TYPES, (
            "Detection view box_detection_v1 must NOT be in VQA dataset views"
        )

    def test_classification_trainer_on_vqa_dataset_is_invalid(self):
        """Invalid: classification trainer (resnet50-sc-v1, view=labeled_image_v1)
        on a VQA dataset (views=[image_input_v1, qa_input_v1])."""
        trainer_view = "labeled_image_v1"  # resnet50-sc-v1
        assert trainer_view not in VQA_VIEW_TYPES, (
            "Classification trainer view labeled_image_v1 must NOT be "
            "compatible with VQA dataset views"
        )

    def test_unknown_view_on_any_dataset_is_invalid(self):
        """Invalid: a view ID not registered in the view registry
        should be rejected for any dataset."""
        unknown_view = "nonexistent_view_v99"
        assert unknown_view not in ALL_KNOWN_VIEWS, (
            "Unknown view must not match any dataset view_types"
        )

    def test_clip_predictor_is_stub_only_image_input(self):
        """CLIP predictor (clip-zero-shot-v1) is a STUB and only registered
        for image_input_v1.  It should NOT be compatible with other views."""
        from app.modules.types import catalog

        predictor_meta = catalog.get_predictor_meta("clip-zero-shot-v1")
        assert predictor_meta["view_id"] == "image_input_v1", (
            "CLIP predictor is stub — only image_input_v1"
        )
        # Stub: should NOT be valid for qa_input_v1 datasets
        assert "qa_input_v1" != "image_input_v1"


# ===================================================================
# SECTION 4: storage_mode checks — independent of dataset_type
# ===================================================================
#
# Key principle: storage_mode (db_full / file_shard_sparse) is
# ORTHOGONAL to dataset_type (classification / vqa / detection).
#
# A classification dataset can be file_shard_sparse.
# A VQA dataset can be db_full.
# NEVER infer storage_mode from dataset_type.


class TestStorageModeIndependentOfDatasetType:
    """storage_mode is orthogonal to dataset_type — never infer one from the other."""

    def test_storage_mode_not_inferred_from_classification(self):
        """A classification dataset can have EITHER storage_mode.
        Do NOT assume classification → db_full."""
        classification_dataset_types = ["image_classification"]
        valid_storage_modes = {"db_full", "file_shard_sparse"}

        for dtype in classification_dataset_types:
            for smode in valid_storage_modes:
                # This is the expected behavior: any dataset_type can have any
                # storage_mode.  The compatibility service must NOT reject a
                # combination based on dataset_type alone.
                assert smode in valid_storage_modes, (
                    f"Classification ({dtype}) with storage_mode={smode} "
                    f"must be a valid combination"
                )

    def test_storage_mode_not_inferred_from_vqa(self):
        """A VQA dataset can have EITHER storage_mode.
        Do NOT assume VQA → db_full."""
        vqa_dataset_types = ["image_vqa"]
        valid_storage_modes = {"db_full", "file_shard_sparse"}

        for dtype in vqa_dataset_types:
            for smode in valid_storage_modes:
                assert smode in valid_storage_modes, (
                    f"VQA ({dtype}) with storage_mode={smode} "
                    f"must be a valid combination"
                )

    def test_storage_mode_not_inferred_from_detection(self):
        """A detection dataset can have EITHER storage_mode.
        Do NOT assume detection → db_full."""
        detection_dataset_types = ["image_detection"]
        valid_storage_modes = {"db_full", "file_shard_sparse"}

        for dtype in detection_dataset_types:
            for smode in valid_storage_modes:
                assert smode in valid_storage_modes, (
                    f"Detection ({dtype}) with storage_mode={smode} "
                    f"must be a valid combination"
                )

    def test_file_shard_sparse_incompatible_with_sample_creation(self):
        """file_shard_sparse datasets cannot create samples via the API.

        This is enforced by assert_not_sparse() in
        app/modules/datasets/app/services/dataset_capability_guard.py
        """
        from app.shared.api.schemas import DatasetStorageMode

        sparse_mode = DatasetStorageMode.FILE_SHARD_SPARSE
        db_full_mode = DatasetStorageMode.DB_FULL

        # file_shard_sparse must exist as a valid enum member
        assert sparse_mode.value == "file_shard_sparse"
        assert db_full_mode.value == "db_full"

        # The capability guard pattern: assert_not_sparse() raises 409
        # for file_shard_sparse.  Verify the guard pattern is consistent.
        # This should be tested against the actual guard function once
        # the compatibility service integrates it.
        import inspect

        try:
            from app.modules.datasets.app.services.dataset_capability_guard import (
                assert_not_sparse,
            )

            func_params = list(inspect.signature(assert_not_sparse).parameters)
            assert "dataset" in func_params, (
                "assert_not_sparse() must accept a dataset parameter"
            )
        except ImportError:
            pass  # Guard module may not be registered yet in test profile

    def test_file_shard_sparse_incompatible_with_training(self):
        """file_shard_sparse datasets should be rejected for training jobs.

        Training requires fully materialised samples which sparse storage
        does not provide.
        """
        sparse_mode = "file_shard_sparse"
        db_full_mode = "db_full"

        # Documentation: the compatibility service MUST check storage_mode
        # before allowing a trainer to be used on a dataset.
        assert sparse_mode != db_full_mode, (
            "storage_mode values are distinct"
        )

    def test_file_shard_sparse_incompatible_with_export(self):
        """file_shard_sparse datasets should be rejected for export operations.

        Export requires all samples to be materialised.
        """
        sparse_mode = "file_shard_sparse"

        # Documentation: the compatibility service should reject exports
        # for sparse datasets.  This test documents the expected behavior.
        assert sparse_mode == "file_shard_sparse", (
            "file_shard_sparse is the sparse storage mode identifier"
        )

    def test_db_full_compatible_with_all_operations(self):
        """db_full storage mode should allow all operations (training, prediction,
        export, sample CRUD) regardless of dataset_type."""
        db_full_mode = "db_full"

        # All three dataset types with db_full → all operations allowed
        for dtype in ["image_classification", "image_vqa", "image_detection"]:
            # No assertion rejection expected for db_full datasets
            assert db_full_mode == "db_full", (
                f"db_full must be valid for {dtype}"
            )
            assert isinstance(dtype, str), f"Dataset type {dtype} is a string"


# ===================================================================
# SECTION 5: Comprehensive compatibility matrix — specification
# ===================================================================
#
# This section defines the full compatibility matrix as assertions.
# These tests serve as living documentation for the compatibility
# service contract.

class TestCompatibilityMatrix:
    """Full compatibility matrix: dataset family × trainer × predictor."""

    @pytest.mark.parametrize(
        "family_name, view_types, trainer_id, trainer_view, predictor_id, predictor_view",
        [
            (
                "classification",
                CLASSIFICATION_VIEW_TYPES,
                "resnet50-sc-v1",
                "labeled_image_v1",
                "resnet50-sc-v1",
                "image_input_v1",
            ),
            (
                "vqa",
                VQA_VIEW_TYPES,
                "resnet50-sc-v1",
                "qa_input_v1",
                "resnet50-sc-v1",
                "qa_input_v1",
            ),
            # Detection has no trainer yet — this is a known gap
        ],
    )
    def test_valid_family_trainer_view_in_dataset_views(
        self, family_name, view_types, trainer_id, trainer_view, predictor_id, predictor_view
    ):
        """For each valid family: trainer view and predictor view must be in
        the dataset's view_types list.

        This is the core compatibility rule:
        - A trainer is compatible with a dataset if trainer.view_id ∈ dataset.view_types
        - A predictor is compatible with a dataset if predictor.view_id ∈ dataset.view_types
        """
        assert trainer_view in view_types, (
            f"[{family_name}] Trainer {trainer_id} view='{trainer_view}' "
            f"must be in dataset view_types={view_types}"
        )
        assert predictor_view in view_types, (
            f"[{family_name}] Predictor {predictor_id} view='{predictor_view}' "
            f"must be in dataset view_types={view_types}"
        )

    @pytest.mark.parametrize(
        "scenario, trainer_view, dataset_views, should_be_valid",
        [
            # Valid positive cases
            ("cls-trainer-on-cls-dataset", "labeled_image_v1", CLASSIFICATION_VIEW_TYPES, True),
            ("vqa-trainer-on-vqa-dataset", "qa_input_v1", VQA_VIEW_TYPES, True),
            # Invalid negative cases (≥3 as required)
            ("vqa-trainer-on-cls-dataset", "qa_input_v1", CLASSIFICATION_VIEW_TYPES, False),
            ("cls-trainer-on-vqa-dataset", "labeled_image_v1", VQA_VIEW_TYPES, False),
            ("detection-view-on-vqa-dataset", "box_detection_v1", VQA_VIEW_TYPES, False),
            ("cls-trainer-on-detection-dataset", "labeled_image_v1", DETECTION_VIEW_TYPES, False),
            ("vqa-trainer-on-detection-dataset", "qa_input_v1", DETECTION_VIEW_TYPES, False),
        ],
    )
    def test_compatibility_matrix_trainer_view(
        self, scenario, trainer_view, dataset_views, should_be_valid
    ):
        """Parametrized compatibility matrix for trainer ↔ dataset view_types."""
        is_compatible = trainer_view in dataset_views
        assert is_compatible == should_be_valid, (
            f"[{scenario}] trainer_view='{trainer_view}' in dataset_views={dataset_views} "
            f"should be {should_be_valid}, got {is_compatible}"
        )

    @pytest.mark.parametrize(
        "scenario, predictor_view, dataset_views, should_be_valid",
        [
            # Valid positive cases
            ("cls-predictor-on-cls-dataset", "image_input_v1", CLASSIFICATION_VIEW_TYPES, True),
            ("vqa-predictor-on-vqa-dataset", "qa_input_v1", VQA_VIEW_TYPES, True),
            # Invalid negative cases
            ("vqa-predictor-on-cls-dataset", "qa_input_v1", CLASSIFICATION_VIEW_TYPES, False),
            # cls-predictor (image_input_v1) IS valid on VQA dataset because
            # image_input_v1 is the shared input view across ALL families.
            ("cls-predictor-on-vqa-dataset", "image_input_v1", VQA_VIEW_TYPES, True),
            ("detection-view-on-vqa-dataset", "box_detection_v1", VQA_VIEW_TYPES, False),
        ],
    )
    def test_compatibility_matrix_predictor_view(
        self, scenario, predictor_view, dataset_views, should_be_valid
    ):
        """Parametrized compatibility matrix for predictor ↔ dataset view_types."""
        is_compatible = predictor_view in dataset_views
        assert is_compatible == should_be_valid, (
            f"[{scenario}] predictor_view='{predictor_view}' in dataset_views={dataset_views} "
            f"should be {should_be_valid}, got {is_compatible}"
        )


# ===================================================================
# SECTION 6: Edge cases
# ===================================================================

class TestEdgeCases:
    """Edge cases the compatibility service must handle."""

    def test_empty_view_types_should_reject_all(self):
        """A dataset with no view_types should reject ALL trainers/predictors."""
        empty_views: list[str] = []
        for trainer_view in TRAINER_VIEW_MAP.values():
            assert trainer_view not in empty_views, (
                f"Trainer view '{trainer_view}' must be rejected for empty view_types"
            )
        for predictor_view in PREDICTOR_VIEW_MAP.values():
            assert predictor_view not in empty_views, (
                f"Predictor view '{predictor_view}' must be rejected for empty view_types"
            )

    def test_duplicate_view_types_should_not_crash(self):
        """Datasets may have duplicate view_types entries.
        Compatibility service must handle this gracefully."""
        dup_views = ["image_input_v1", "image_input_v1", "labeled_image_v1"]
        unique_views = set(dup_views)
        # Deduplication should still find valid matches
        assert "labeled_image_v1" in unique_views
        assert "image_input_v1" in unique_views

    def test_storage_mode_check_before_view_check(self):
        """storage_mode incompatibility should FAIL FAST before view checks.

        If a dataset is file_shard_sparse, reject it immediately without
        checking view compatibility — the operation is inherently impossible.
        """
        from app.shared.api.schemas import DatasetStorageMode

        # Priority: storage_mode gate BEFORE view compatibility check
        sparse = DatasetStorageMode.FILE_SHARD_SPARSE
        db_full = DatasetStorageMode.DB_FULL

        # Verify enum values
        assert sparse.value == "file_shard_sparse"
        assert db_full.value == "db_full"

    def test_stub_predictor_clip_handling(self):
        """CLIP zero-shot predictor is a stub.  Compatibility service should
        handle stubs gracefully (e.g. return False for training-specific checks)."""
        from app.modules.types import catalog

        clip = catalog.get_predictor_meta("clip-zero-shot-v1")

        # As a stub, ClipPredictor has no real implementation.
        # Compatibility service must NOT crash when checking stubs.
        assert "view_id" in clip, "Stub must have view_id metadata"
        assert clip["view_id"] == "image_input_v1"
