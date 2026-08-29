from __future__ import annotations

import gzip

import pytest

from app.modules.sc.data_provider.request_compression import _bounded_gzip_decompress


def test_bounded_gzip_decompress_round_trips_query_json() -> None:
    payload = b'{"parameters":[[1,2,3]],"sql":"select 1"}'

    assert _bounded_gzip_decompress(gzip.compress(payload), 1_024) == payload


def test_bounded_gzip_decompress_rejects_expansion_past_limit() -> None:
    with pytest.raises(ValueError, match="too large"):
        _bounded_gzip_decompress(gzip.compress(b"x" * 2_000), 1_000)


def test_bounded_gzip_decompress_rejects_invalid_content() -> None:
    with pytest.raises(ValueError, match="invalid gzip"):
        _bounded_gzip_decompress(b"not gzip", 1_000)
