from __future__ import annotations

# ── Dataset types + Views ───────────────────────────────────────────────
import app.modules.datasets.classification.models  # noqa: F401  # @dataset("image_classification"), image_input_v1, labeled_image_v1
import app.modules.sc.models  # noqa: F401  # @dataset("image_sc")

# ── View rows listed explicitly by the import-safe capability catalog ──────
import app.modules.types.view_registration  # noqa: F401

# ── Mappers ────────────────────────────────────────────────────────────────
import app.modules.sc.domain.mapper  # noqa: F401
import app.modules.datasets.domain.mapper  # noqa: F401

# ── Versioned view/trainer/predictor/materializer metadata is aggregated by
# ── app.modules.types.catalog. Worker executables live under
# ── app.runtime_compat and must not be imported by API startup. ─────────────
