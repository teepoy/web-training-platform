# Export Formats

This document describes the annotation-version export format system and how to add new formats.

## Overview

Export formats are registered via a **strategy pattern** in `apps/api/app/services/artifacts.py`. Each format is a builder function that receives review action context and returns a JSON-serializable dict.

The API exposes:

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/export-formats` | List all registered format IDs |
| `GET /api/v1/prediction-reviews/{id}/export?format_id=...` | Preview export JSON |
| `POST /api/v1/prediction-reviews/{id}/export/persist` | Persist to artifact storage |

## Built-in Formats

### `annotation-version-full-context-v1`

Full-context JSON with review action metadata, dataset info, touched samples, and annotations with version details plus Label Studio context.

```json
{
  "format": "annotation-version-full-context-v1",
  "review_action": { "id", "dataset_id", "model_id", "model_version", "created_by", "created_at" },
  "dataset": { ... },
  "samples": [ { "id", "dataset_id", "image_uris", "metadata", ... } ],
  "annotations": [
    {
      "annotation": { "id", "sample_id", "label", "created_by", "created_at" },
      "version": { "id", "review_action_id", "annotation_id", "source_prediction_id", "predicted_label", "final_label", "confidence", "created_at" },
      "ls_context": { "prediction_id", "predicted_label" }
    }
  ]
}
```

### `annotation-version-compact-v1`

Flat rows for quick analysis or downstream pipelines.

```json
{
  "format": "annotation-version-compact-v1",
  "review_action_id": "...",
  "dataset_id": "...",
  "rows": [
    { "sample_id": "...", "predicted_label": "cat", "final_label": "dog", "confidence": 0.85 }
  ]
}
```

## How to Add a New Export Format

### Checklist

1. **Choose a format ID** with a `-vN` version suffix (e.g. `my-custom-format-v1`).

2. **Add the builder function** in `apps/api/app/services/artifacts.py`:
   ```python
   @register_format("my-custom-format-v1")
   def build_my_custom_export(
       *,
       review_action: PredictionReviewAction,
       dataset: Dataset,
       samples: list[Sample],
       annotations: list[Annotation],
       versions: list[AnnotationVersion],
   ) -> dict[str, Any]:
       # Build and return your export dict
       return {
           "format": "my-custom-format-v1",
           # ... your fields
       }
   ```

3. **Add a test** in `apps/api/tests/test_prediction_review.py`:
   - Call `GET /api/v1/prediction-reviews/{id}/export?format_id=my-custom-format-v1`
   - Verify the response shape and `format` field.

4. **Verify registration**: Run the existing `test_list_export_formats` test to confirm your format appears in the list.

5. **Update this document** with the new format's JSON shape.

### Code Touchpoints

| File | What to change |
|------|----------------|
| `apps/api/app/services/artifacts.py` | Add `@register_format(...)` builder function |
| `apps/api/tests/test_prediction_review.py` | Add test for the new format |
| `docs/export-formats.md` | Document the JSON shape |

### Versioning Guidance

- Format IDs **must** end with `-vN` (e.g. `-v1`, `-v2`).
- When making breaking changes to an existing format's shape, create a new version (`-v2`) rather than modifying the existing one.
- Old versions should be kept for backward compatibility unless explicitly deprecated.
- The builder function signature (keyword arguments) is fixed by the export endpoint. All builders receive the same inputs: `review_action`, `dataset`, `samples`, `annotations`, `versions`.

### Builder Function Contract

All builder functions must:

1. Accept keyword-only arguments: `review_action`, `dataset`, `samples`, `annotations`, `versions`.
2. Return a JSON-serializable `dict[str, Any]`.
3. Include a `"format"` key matching their registered format ID.
4. Only include samples and annotations that were touched in the review session (these are pre-filtered by the endpoint handler).
