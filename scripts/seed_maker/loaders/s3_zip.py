from __future__ import annotations

import io
import json
import zipfile


class S3ZipWriter:
    def __init__(
        self,
        bucket: str,
        prefix: str,
        *,
        endpoint_url: str = "http://localhost:9000",
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
        region: str = "us-east-1",
        samples_per_zip: int = 500,
    ) -> None:
        import boto3  # type: ignore[import-untyped]
        self._bucket = bucket
        self._prefix = prefix.rstrip("/")
        self._samples_per_zip = samples_per_zip
        self._s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        self._buffer: list[dict] = []
        self._chunk_idx = 0
        self._global_idx = 0
        self._index: list[dict] = []

    def __call__(self, items: list[dict]) -> int:
        self._buffer.extend(items)
        while len(self._buffer) >= self._samples_per_zip:
            chunk = self._buffer[:self._samples_per_zip]
            self._buffer = self._buffer[self._samples_per_zip:]
            self._push_zip(chunk)
        return len(items)

    def flush(self) -> None:
        if self._buffer:
            self._push_zip(self._buffer)
            self._buffer = []
        if not self._index:
            return
        self._s3.put_object(
            Bucket=self._bucket,
            Key=f"{self._prefix}/index.json",
            Body=json.dumps(self._index, indent=2).encode("utf-8"),
        )
        print(f"  Wrote index.json ({len(self._index)} chunks) to s3://{self._bucket}/{self._prefix}/")

    def _push_zip(self, chunk_items: list[dict]) -> None:
        first_id = self._global_idx
        zip_buf = io.BytesIO()
        manifest: list[dict] = []

        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in chunk_items:
                sid = f"{self._global_idx:06d}"
                image_names: list[str] = []
                for img_idx, uri in enumerate(item.get("image_uris", [])):
                    fname = f"{sid}_{img_idx}"
                    ext = self._uri_ext(uri)
                    image_names.append(f"{fname}.{ext}")
                    zf.writestr(f"{fname}.{ext}", self._uri_bytes(uri))
                manifest.append({
                    "id": sid,
                    "label": item.get("label"),
                    "metadata": item.get("metadata", {}),
                    "image_count": len(image_names),
                    "images": image_names,
                })
                self._global_idx += 1

            zf.writestr("manifest.json", json.dumps(manifest, indent=2))

        key = f"{self._prefix}/chunk_{self._chunk_idx:05d}.zip"
        zip_bytes = zip_buf.getvalue()
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=zip_bytes,
            ContentType="application/zip",
        )
        self._index.append({
            "sample_range": [first_id, self._global_idx - 1],
            "chunk": key,
            "sample_count": len(chunk_items),
        })
        print(f"  Pushed {key} ({len(chunk_items)} samples, "
              f"{len(zip_bytes) / 1024 / 1024:.1f} MB) to s3://{self._bucket}/")
        self._chunk_idx += 1

    @staticmethod
    def _uri_ext(uri: str) -> str:
        if uri.startswith("data:image/png"):
            return "png"
        if uri.startswith("data:image/jpeg") or uri.startswith("data:image/jpg"):
            return "jpg"
        return "bin"

    @staticmethod
    def _uri_bytes(uri: str) -> bytes:
        import base64
        if "," in uri:
            return base64.b64decode(uri.split(",", 1)[1])
        return uri.encode("utf-8")
