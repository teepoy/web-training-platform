from __future__ import annotations

import asyncio
from io import BytesIO
from types import SimpleNamespace

from minio.commonconfig import Filter
from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule
import pytest

from app.shared.infrastructure.storage.minio import (
    MinioArtifactStorage,
    MinioExportLifecycle,
    build_minio_export_lifecycle,
    prepare_minio_storage,
    validate_minio_storage,
)


class _NoSuchLifecycleConfiguration(Exception):
    code = "NoSuchLifecycleConfiguration"


class _FakeMinioClient:
    def __init__(self, existing: LifecycleConfig | Exception | None = None) -> None:
        self.existing = existing
        self.lifecycle: LifecycleConfig | None = None
        self.events: list[str] = []
        self.object_payload = b"0123456789"

    def bucket_exists(self, bucket: str) -> bool:
        self.events.append(f"bucket_exists:{bucket}")
        return True

    def make_bucket(self, bucket: str) -> None:
        self.events.append(f"make_bucket:{bucket}")

    def get_bucket_lifecycle(self, bucket: str) -> LifecycleConfig | None:
        self.events.append(f"get_lifecycle:{bucket}")
        if isinstance(self.existing, Exception):
            raise self.existing
        return self.existing

    def set_bucket_lifecycle(self, bucket: str, config: LifecycleConfig) -> None:
        self.events.append(f"set_lifecycle:{bucket}")
        self.lifecycle = config
        self.existing = config

    def put_object(
        self,
        *,
        bucket_name: str,
        object_name: str,
        data: BytesIO,
        length: int,
        content_type: str,
    ) -> None:
        self.events.append(f"put_object:{bucket_name}/{object_name}")
        assert data.read() == b"payload"
        assert length == len(b"payload")
        assert content_type == "application/json"

    def stat_object(self, bucket_name: str, object_name: str) -> SimpleNamespace:
        self.events.append(f"stat_object:{bucket_name}/{object_name}")
        return SimpleNamespace(size=len(self.object_payload))

    def get_object(
        self,
        bucket_name: str,
        object_name: str,
        offset: int = 0,
        length: int = 0,
    ) -> "_FakeObjectResponse":
        self.events.append(f"get_object:{bucket_name}/{object_name}:{offset}:{length}")
        end = None if length == 0 else offset + length
        return _FakeObjectResponse(self.object_payload[offset:end])


class _FakeObjectResponse(BytesIO):
    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.released = False

    def release_conn(self) -> None:
        self.released = True


def _storage(fake: _FakeMinioClient) -> MinioArtifactStorage:
    storage = MinioArtifactStorage(
        endpoint="localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket="finetune-artifacts",
        export_lifecycle=MinioExportLifecycle(
            prefix="exports/",
            expiration_days=1,
        ),
    )
    storage.client = fake  # type: ignore[assignment]
    return storage


def _rules_by_id(config: LifecycleConfig) -> dict[str, Rule]:
    return {str(rule.rule_id): rule for rule in config.rules}


def test_default_config_enables_export_lifecycle() -> None:
    from app.core.config import load_config

    cfg = load_config(skip_runtime_validation=True)
    lifecycle = build_minio_export_lifecycle(cfg)

    assert lifecycle == MinioExportLifecycle(
        prefix="exports/",
        expiration_days=1,
    )


def test_minio_artifact_download_streams_requested_range() -> None:
    fake = _FakeMinioClient()
    storage = _storage(fake)

    async def read_range() -> tuple[int, list[bytes]]:
        uri = "s3://finetune-artifacts/exports/dataset/large.zip"
        size = await storage.get_size(uri)
        chunks = [
            chunk
            async for chunk in storage.iter_bytes(
                uri,
                offset=2,
                length=7,
                chunk_size=3,
            )
        ]
        return size, chunks

    size, chunks = asyncio.run(read_range())

    assert size == 10
    assert chunks == [b"234", b"567", b"8"]
    assert "get_object:finetune-artifacts/exports/dataset/large.zip:2:7" in fake.events


def test_prepare_installs_export_lifecycle_when_bucket_has_no_policy() -> None:
    fake = _FakeMinioClient(existing=_NoSuchLifecycleConfiguration())
    storage = _storage(fake)

    prepare_minio_storage(
        fake,  # type: ignore[arg-type]
        artifact_bucket="finetune-artifacts",
        runtime_bucket="finetune-runtime-inputs",
        export_lifecycle=storage.export_lifecycle,
    )

    assert fake.lifecycle is not None
    rules = _rules_by_id(fake.lifecycle)
    assert rules["finetune-export-expiration"].rule_filter == Filter(
        prefix="exports/"
    )
    assert rules["finetune-export-expiration"].expiration == Expiration(days=1)
    assert rules["finetune-export-expiration"].abort_incomplete_multipart_upload is None
    assert set(rules) == {"finetune-export-expiration"}


def test_prepare_preserves_unmanaged_lifecycle_rules() -> None:
    unmanaged = Rule(
        status="Enabled",
        rule_filter=Filter(prefix="artifacts/"),
        rule_id="keep-artifacts",
        expiration=Expiration(days=30),
    )
    stale_managed = Rule(
        status="Enabled",
        rule_filter=Filter(prefix="exports/"),
        rule_id="finetune-export-expiration",
        expiration=Expiration(days=7),
    )
    fake = _FakeMinioClient(
        existing=LifecycleConfig([unmanaged, stale_managed])
    )
    storage = _storage(fake)

    prepare_minio_storage(
        fake,  # type: ignore[arg-type]
        artifact_bucket="finetune-artifacts",
        runtime_bucket="finetune-runtime-inputs",
        export_lifecycle=storage.export_lifecycle,
    )

    assert fake.lifecycle is not None
    rules = _rules_by_id(fake.lifecycle)
    assert rules["keep-artifacts"] == unmanaged
    assert rules["finetune-export-expiration"].expiration == Expiration(days=1)
    assert len(fake.lifecycle.rules) == 2


@pytest.mark.asyncio
async def test_upload_does_not_mutate_bucket_or_lifecycle() -> None:
    fake = _FakeMinioClient(existing=None)
    storage = _storage(fake)

    await storage.put_bytes("exports/one.json", b"payload", "application/json")
    await storage.put_bytes("exports/two.json", b"payload", "application/json")

    assert fake.events == [
        "put_object:finetune-artifacts/exports/one.json",
        "put_object:finetune-artifacts/exports/two.json",
    ]


def test_validate_rejects_missing_managed_lifecycle() -> None:
    fake = _FakeMinioClient(existing=None)
    storage = _storage(fake)

    with pytest.raises(RuntimeError, match="lifecycle mismatch"):
        validate_minio_storage(
            fake,  # type: ignore[arg-type]
            artifact_bucket="finetune-artifacts",
            runtime_bucket="finetune-runtime-inputs",
            export_lifecycle=storage.export_lifecycle,
        )
