from __future__ import annotations

import time

from seedmaker import SeedConfig, SeedRunner, registry
from seedmaker.images import pil_to_data_uri
from seedmaker.utils import api_request

config = SeedConfig(
    name="oxford-flowers",
    dataset_name="Oxford Flowers 102",
    description="Oxford Flowers 102 dataset from HuggingFace. ~8K flower images across 102 classes. Requires HF_TOKEN if dataset needs auth.",
    label_space=[],  # loaded dynamically from HF
    org_name="Flowers Lab",
    org_slug="flowers-lab",
    defer_dataset=True,
)


def run(args, runner: SeedRunner) -> int:
    try:
        from datasets import load_dataset  # type: ignore[import-untyped]
    except ImportError:
        print(
            "ERROR: 'datasets' package not found. Install: uv pip install datasets Pillow"
        )
        return 1

    max_samples: int = args.max_samples if args.max_samples is not None else 0
    batch_report: int = getattr(args, "batch_report", 100)

    print("[5/6] Loading Oxford Flowers 102 from HuggingFace ...")
    hf_dataset = load_dataset("dpdl-benchmark/oxford_flowers102")
    first_split = next(iter(hf_dataset.values()))
    label_names: list[str] = first_split.features["label"].names
    print(f"  {len(label_names)} classes, splits: {list(hf_dataset.keys())}")

    print("[5/6] Creating dataset ...")
    r = api_request(
        runner.client,
        "post",
        "/api/v1/datasets",
        json={
            "name": config.dataset_name,
            "dataset_type": "image_classification",
            "task_spec": {
                "task_type": "classification",
                "label_space": label_names,
            },
        },
    )
    if r.status_code not in (200, 201):
        print(f"  ERROR creating dataset: {r.status_code} {r.text}")
        return 1
    dataset_id = str(r.json()["id"])
    runner._dataset_id = dataset_id
    print(f"  Created dataset: {dataset_id}")

    print("[6/6] Creating samples ...")
    from seedmaker.loaders.dataset import DatasetLoader

    loader = DatasetLoader(runner.client, dataset_id)

    total_created = 0
    batch_size = 5000
    batch: list[dict] = []
    t0 = time.time()
    limit = max_samples if max_samples > 0 else float("inf")

    for split_name in sorted(hf_dataset.keys()):
        split = hf_dataset[split_name]
        print(f"  Processing split '{split_name}' ({len(split)} samples) ...")
        for example in split:
            if total_created >= limit:
                break
            data_uri = pil_to_data_uri(example["image"])
            label_idx = example["label"]
            label_name = (
                label_names[label_idx]
                if label_idx < len(label_names)
                else f"class_{label_idx}"
            )
            batch.append(
                {
                    "image_uris": [data_uri],
                    "metadata": {
                        "split": split_name,
                        "label_index": label_idx,
                        "label_name": label_name,
                    },
                    "label": label_name,
                }
            )
            if len(batch) >= batch_size or (
                max_samples > 0 and total_created + len(batch) >= limit
            ):
                imported = loader(batch)
                total_created += imported
                batch = []
                if total_created % batch_report == 0 and total_created > 0:
                    elapsed = time.time() - t0
                    rate = total_created / elapsed if elapsed > 0 else 0
                    print(f"    ... {total_created} samples ({rate:.1f}/s)")
        if total_created >= limit:
            break

    elapsed = time.time() - t0
    print(f"  Created {total_created} samples in {elapsed:.1f}s")
    runner._sample_count = total_created
    runner.summary()
    return 0


registry.register(config, run)
