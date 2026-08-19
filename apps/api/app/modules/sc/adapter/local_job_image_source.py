from __future__ import annotations

import asyncio
import os
import struct
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from proto_stubs.imageparser.v1 import service_pb2 as pb

from app.modules.sc.domain.job_image_source import (
    ScPatchImageBatchResolver,
    normalize_role_paths,
)

_MAX_FRAME_BYTES = 256 * 1024 * 1024
_STDERR_TAIL_BYTES = 64 * 1024


class LocalJobImageSourceFactory:
    """Start one offline resolver process for one training or prediction job."""

    def __init__(
        self,
        *,
        binary_path: str,
        max_frame_bytes: int = _MAX_FRAME_BYTES,
        shutdown_timeout_seconds: float = 5.0,
    ) -> None:
        if not binary_path.strip():
            raise ValueError("job image resolver binary path is required")
        if max_frame_bytes <= 0:
            raise ValueError("max_frame_bytes must be greater than zero")
        if shutdown_timeout_seconds <= 0:
            raise ValueError("shutdown_timeout_seconds must be greater than zero")
        self._binary_path = binary_path
        self._max_frame_bytes = max_frame_bytes
        self._shutdown_timeout_seconds = shutdown_timeout_seconds

    @asynccontextmanager
    async def open(self) -> AsyncIterator[ScPatchImageBatchResolver]:
        process = await asyncio.create_subprocess_exec(
            self._binary_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        session = _LocalJobImageSourceSession(
            process,
            max_frame_bytes=self._max_frame_bytes,
            shutdown_timeout_seconds=self._shutdown_timeout_seconds,
        )
        body_failed = False
        try:
            yield session
        except BaseException:
            body_failed = True
            raise
        finally:
            await session.close(raise_on_process_error=not body_failed)


class _LocalJobImageSourceSession:
    def __init__(
        self,
        process: asyncio.subprocess.Process,
        *,
        max_frame_bytes: int,
        shutdown_timeout_seconds: float,
    ) -> None:
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise RuntimeError("image parser batch process pipes are unavailable")
        self._process = process
        self._stdin = process.stdin
        self._stdout = process.stdout
        self._stderr = process.stderr
        self._max_frame_bytes = max_frame_bytes
        self._shutdown_timeout_seconds = shutdown_timeout_seconds
        self._lock = asyncio.Lock()
        self._stderr_tail = bytearray()
        self._stderr_task = asyncio.create_task(self._capture_stderr())
        self._closed = False

    async def resolve_patch_images(
        self,
        *,
        source_format: str,
        roles: list[str],
        items: list[dict[str, object]],
    ) -> AsyncIterator[dict[str, object]]:
        request = pb.ResolvePatchImagesRequest(
            source_format=source_format,
            roles=roles,
            items=[
                pb.ResolvePatchImageItem(
                    request_id=str(item.get("request_id", "")),
                    sample_id=str(item.get("sample_id", "")),
                    inspection_time=str(item.get("inspection_time", "")),
                    wafer_key=int(cast(object, item.get("wafer_key", 0)) or 0),  # type: ignore[arg-type]
                    defect_id=str(item.get("defect_id", "")),
                    role_paths=normalize_role_paths(item.get("role_paths")),
                )
                for item in items
            ],
        )
        payload = request.SerializeToString()
        if not payload or len(payload) > self._max_frame_bytes:
            raise RuntimeError(
                f"job image resolver request frame size {len(payload)} is invalid"
            )

        async with self._lock:
            self._ensure_running()
            self._stdin.write(struct.pack(">I", len(payload)))
            self._stdin.write(payload)
            await self._stdin.drain()
            try:
                header = await self._stdout.readexactly(4)
                response_size = struct.unpack(">I", header)[0]
                if response_size <= 0 or response_size > self._max_frame_bytes:
                    raise RuntimeError(
                        "job image resolver returned invalid frame size "
                        f"{response_size}"
                    )
                response_payload = await self._stdout.readexactly(response_size)
            except asyncio.IncompleteReadError as exc:
                await self._wait_after_pipe_failure()
                raise RuntimeError(self._process_failure_message()) from exc

            response = pb.ResolvePatchImagesBatchResponse()
            try:
                response.ParseFromString(response_payload)
            except Exception as exc:
                raise RuntimeError(
                    "job image resolver returned an invalid protobuf response"
                ) from exc

            expected = [
                (str(item.get("request_id", "")), _canonical_role(role))
                for item in items
                for role in roles
            ]
            actual = [(result.request_id, result.role) for result in response.results]
            if actual != expected:
                raise RuntimeError(
                    "job image resolver response order/correlation mismatch: "
                    f"expected {expected!r}, got {actual!r}"
                )
            for result in response.results:
                yield {
                    "request_id": result.request_id,
                    "sample_id": result.sample_id,
                    "inspection_time": result.inspection_time,
                    "wafer_key": result.wafer_key,
                    "defect_id": result.defect_id,
                    "role": result.role,
                    "image_data": result.image_data,
                    "content_type": result.content_type,
                    "error": result.error,
                }

    async def close(self, *, raise_on_process_error: bool) -> None:
        if self._closed:
            return
        self._closed = True
        self._stdin.close()
        try:
            await self._stdin.wait_closed()
        except (BrokenPipeError, ConnectionResetError):
            pass
        try:
            await asyncio.wait_for(
                self._process.wait(), timeout=self._shutdown_timeout_seconds
            )
        except TimeoutError:
            self._process.terminate()
            try:
                await asyncio.wait_for(
                    self._process.wait(), timeout=self._shutdown_timeout_seconds
                )
            except TimeoutError:
                self._process.kill()
                await self._process.wait()
        await self._stderr_task
        if raise_on_process_error and self._process.returncode != 0:
            raise RuntimeError(self._process_failure_message())

    def _ensure_running(self) -> None:
        if self._closed:
            raise RuntimeError("job image resolver session is closed")
        if self._process.returncode is not None:
            raise RuntimeError(self._process_failure_message())

    async def _wait_after_pipe_failure(self) -> None:
        if self._process.returncode is None:
            try:
                await asyncio.wait_for(
                    self._process.wait(), timeout=self._shutdown_timeout_seconds
                )
            except TimeoutError:
                return
        if self._stderr_task.done():
            await self._stderr_task

    async def _capture_stderr(self) -> None:
        while chunk := await self._stderr.read(4096):
            self._stderr_tail.extend(chunk)
            if len(self._stderr_tail) > _STDERR_TAIL_BYTES:
                del self._stderr_tail[:-_STDERR_TAIL_BYTES]

    def _process_failure_message(self) -> str:
        stderr = self._stderr_tail.decode("utf-8", errors="replace").strip()
        detail = f": {stderr}" if stderr else ""
        return (
            "job image resolver process exited unexpectedly "
            f"(code={self._process.returncode}){detail}"
        )


def _canonical_role(raw_role: str) -> str:
    normalized = raw_role.strip().lower()
    if normalized in {
        "patch_template",
        "patchtemplate",
        "patch_reference",
        "patchreference",
        "template",
        "reference",
    }:
        return "patch_template"
    if normalized in {"patch_defective", "patchdefective", "defective"}:
        return "patch_defective"
    if normalized in {"patch_difference", "patchdifference", "difference"}:
        return "patch_difference"
    return raw_role.strip()


__all__ = ["LocalJobImageSourceFactory"]
