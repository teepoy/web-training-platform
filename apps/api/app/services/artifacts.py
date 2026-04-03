from __future__ import annotations

import hashlib
import json

from app.domain.models import Annotation, ArtifactRef, Dataset, Sample


class ArtifactService:
    def __init__(self, storage, repository) -> None:
        self.storage = storage
        self.repository = repository

    async def persist_dataset_export(self, dataset: Dataset, samples: list[Sample], annotations: list[Annotation]) -> str:
        payload = self.build_dataset_export(dataset, samples, annotations)
        object_name = f"exports/{dataset.id}/dataset-export.json"
        return await self.storage.put_bytes(object_name=object_name, data=json.dumps(payload).encode("utf-8"), content_type="application/json")

    async def persist_job_artifacts(self, job_id: str, artifacts: list[ArtifactRef]) -> list[ArtifactRef]:
        persisted: list[ArtifactRef] = []
        for artifact in artifacts:
            content = json.dumps(
                {
                    "source_uri": artifact.uri,
                    "kind": artifact.kind,
                    "metadata": artifact.metadata,
                },
                sort_keys=True,
            ).encode("utf-8")
            checksum = hashlib.sha256(content).hexdigest()
            object_name = f"artifacts/{job_id}/{artifact.id}.json"
            stored_uri = await self.storage.put_bytes(object_name=object_name, data=content, content_type="application/json")
            persisted.append(
                ArtifactRef(
                    id=artifact.id,
                    uri=stored_uri,
                    kind=artifact.kind,
                    metadata={
                        **artifact.metadata,
                        "source_uri": artifact.uri,
                        "checksum_sha256": checksum,
                    },
                )
            )
        await self.repository.add_artifacts(job_id, persisted)
        return persisted

    def build_dataset_export(self, dataset: Dataset, samples: list[Sample], annotations: list[Annotation]) -> dict:
        return {
            "format": "hf-datasets-friendly-json",
            "dataset": dataset.model_dump(mode="json"),
            "samples": [s.model_dump(mode="json") for s in samples],
            "annotations": [a.model_dump(mode="json") for a in annotations],
            "artifact_layout": {
                "dataset_snapshot": "s3://artifacts/{tenant}/{project}/{task}/{job}/dataset_snapshot/",
                "model": "s3://artifacts/{tenant}/{project}/{task}/{job}/model/",
            },
        }
