# Dataset And Model Compatibility

## Taxonomy

- `dataset_type` is the concrete, immutable dataset schema contract.
- `task_type` is the concrete, immutable learning objective.
- prediction `target` is the runtime output mode exposed by a preset or uploaded model.

Current supported dataset types:

- `image_classification`
- `image_vqa`

Current supported task types:

- `classification`
- `vqa`

Current valid dataset/task pairs:

- `image_classification` + `classification`
- `image_vqa` + `vqa`

## Presets

Engineer-managed presets now declare explicit compatibility metadata:

- supported `dataset_types`
- supported `task_types`
- supported prediction `targets`

Training-job creation rejects incompatible dataset/preset combinations before execution starts.

## Uploaded Models

Uploaded models must declare explicit compatibility metadata. Uploads are grouped into template families:

- `image-classifier`
- `image-embedder`
- `vqa`

Profiles such as `clip-zero-shot-v1`, `resnet50-cls-v1`, and `dspy-vqa-v1` are prefill helpers only. All model fields remain editable after choosing a profile.

Required upload metadata includes:

- template id
- profile id
- model spec (`framework`, `architecture`, `base_model`)
- compatibility (`dataset_types`, `task_types`, `prediction_targets`)

Additional rules:

- `image-classifier` requires a non-empty `label_space`
- `image-embedder` requires `embedding_dimension` and `normalized_output`
- `vqa` forbids `label_space`

## Prediction Validation

Prediction and review flows validate:

- model supports the requested target
- model supports the dataset type
- model supports the dataset task type

For image classification predictions, the model label space must be a subset of the dataset label space:

`set(model.label_space) <= set(dataset.label_space)`

This allows a classifier trained on a narrower label space to run on a broader dataset label space, but prevents predictions against datasets that are missing model labels.

## Immutability

- `dataset_type` is immutable after dataset creation.
- `task_type` is immutable after dataset creation.
- classification datasets may update `label_space`
- VQA datasets must keep `label_space` empty
