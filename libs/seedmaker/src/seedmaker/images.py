from __future__ import annotations

import base64
import io
import random
import struct
import zlib


def png_data_uri(size: int, red: int, green: int, blue: int) -> str:
    raw_rows = bytearray()
    for _y in range(size):
        raw_rows.append(0)
        for _x in range(size):
            raw_rows.extend((red, green, blue))

    def _chunk(tag: bytes, data: bytes) -> bytes:
        payload = tag + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
    png += _chunk(b"IDAT", zlib.compress(bytes(raw_rows), 6))
    png += _chunk(b"IEND", b"")
    return f"data:image/png;base64,{base64.b64encode(png).decode()}"


def pil_to_data_uri(img, fmt: str = "JPEG", quality: int = 85) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format=fmt, quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/{fmt.lower()};base64,{b64}"


def generate_synthetic_image(index: int, size: int = 224) -> str:
    rng = random.Random(index)
    r, g, b = rng.randint(40, 220), rng.randint(40, 220), rng.randint(40, 220)
    return png_data_uri(size, r, g, b)
