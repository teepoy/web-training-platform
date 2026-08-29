from __future__ import annotations

import zlib
from collections.abc import Awaitable, Callable

from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send


class ScGzipRequestMiddleware:
    """Decode bounded gzip request bodies for the SC query service."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or _content_encoding(scope) != "gzip":
            await self._app(scope, receive, send)
            return

        config = scope["app"].state.sc_data_provider.config
        compressed_limit = int(config.max_compressed_request_bytes)
        decompressed_limit = int(config.max_decompressed_request_bytes)
        compressed = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                await self._app(scope, _single_receive(message), send)
                return
            compressed.extend(message.get("body", b""))
            if len(compressed) > compressed_limit:
                await _error(send, 413, "Compressed SC query request is too large")
                return
            if not message.get("more_body", False):
                break

        try:
            body = _bounded_gzip_decompress(bytes(compressed), decompressed_limit)
        except ValueError as exc:
            await _error(send, 413 if "too large" in str(exc) else 400, str(exc))
            return

        forwarded_scope = dict(scope)
        forwarded_scope["headers"] = _decoded_headers(scope, len(body))
        await self._app(
            forwarded_scope,
            _single_receive({"type": "http.request", "body": body, "more_body": False}),
            send,
        )


def _bounded_gzip_decompress(payload: bytes, maximum: int) -> bytes:
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    chunks: list[bytes] = []
    size = 0
    try:
        for offset in range(0, len(payload), 64 * 1024):
            part = decompressor.decompress(
                payload[offset : offset + 64 * 1024], maximum - size + 1
            )
            chunks.append(part)
            size += len(part)
            if size > maximum or decompressor.unconsumed_tail:
                raise ValueError("Decompressed SC query request is too large")
        tail = decompressor.flush(maximum - size + 1)
    except zlib.error as exc:
        raise ValueError("SC query request has invalid gzip content") from exc
    chunks.append(tail)
    size += len(tail)
    if size > maximum:
        raise ValueError("Decompressed SC query request is too large")
    if not decompressor.eof or decompressor.unused_data:
        raise ValueError("SC query request has invalid gzip content")
    return b"".join(chunks)


def _content_encoding(scope: Scope) -> str:
    for name, value in scope.get("headers", []):
        if name.lower() == b"content-encoding":
            return value.decode("latin-1").strip().lower()
    return ""


def _decoded_headers(scope: Scope, content_length: int) -> list[tuple[bytes, bytes]]:
    headers = [
        (name, value)
        for name, value in scope.get("headers", [])
        if name.lower() not in {b"content-encoding", b"content-length"}
    ]
    headers.append((b"content-length", str(content_length).encode("ascii")))
    return headers


def _single_receive(message: Message) -> Receive:
    delivered = False

    async def receive() -> Message:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return message

    return receive


async def _error(send: Send, status: int, detail: str) -> None:
    response = JSONResponse(status_code=status, content={"detail": detail})
    await response({"type": "http"}, _single_receive({"type": "http.disconnect"}), send)
