from __future__ import annotations

# ── Dataset types + Views (from consolidated datasets/ subdomains) ─────
import app.modules.datasets.classification.models  # noqa: F401  # @dataset("image_classification"), image_input_v1, labeled_image_v1
import app.modules.datasets.detection.models  # noqa: F401  # image_input_v1, box_detection_v1
import app.modules.datasets.vqa.models  # noqa: F401  # image_input_v1, qa_input_v1
import app.modules.sc.models  # noqa: F401  # @dataset("image_sc")

# ── Adapters ────────────────────────────────────────────────────────────
import app.modules.sc.adapter  # noqa: F401  # ScDatasetStore

# ── Views (per-view subdomains) ────────────────────────────────────────
import app.modules.datasets.views.labeled_image.v1  # noqa: F401
import app.modules.datasets.views.qa_input.v1  # noqa: F401
import app.modules.datasets.views.box_detection.v1  # noqa: F401
import app.modules.datasets.views.image_input.v1  # noqa: F401
import app.modules.sc.views.patch_image.v1  # noqa: F401
import app.modules.sc.views.review_image.v1  # noqa: F401

# ── Mappers ────────────────────────────────────────────────────────────────
import app.modules.sc.domain.mapper  # noqa: F401
import app.modules.datasets.domain.mapper  # noqa: F401

# ── Trainer/predictor metadata lives in app.modules.types.catalog. Executable
# ── modules formerly under app.modules.types.trainers.* and
# ── app.modules.types.predictors.* are registered by worker.runtime, not API
# ── startup. ────────────────────────────────────────────────────────────────
