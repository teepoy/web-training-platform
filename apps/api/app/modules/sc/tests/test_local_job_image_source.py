from __future__ import annotations

import sys
import textwrap

import pytest

from app.modules.sc.adapter.local_job_image_source import (
    LocalJobImageSourceFactory,
)


@pytest.mark.asyncio
async def test_local_training_source_reuses_one_process_and_preserves_order(
    tmp_path,
) -> None:
    closed_marker = tmp_path / "closed"
    executable = tmp_path / "fake-image-parser-batch"
    executable.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import struct
            import sys

            from proto_stubs.imageparser.v1 import service_pb2 as pb

            source = sys.stdin.buffer
            sink = sys.stdout.buffer
            while True:
                header = source.read(4)
                if not header:
                    break
                size = struct.unpack(">I", header)[0]
                request = pb.ResolvePatchImagesRequest()
                request.ParseFromString(source.read(size))
                response = pb.ResolvePatchImagesBatchResponse()
                for item in request.items:
                    for role in request.roles:
                        result = response.results.add()
                        result.request_id = item.request_id
                        result.sample_id = item.sample_id
                        result.inspection_time = item.inspection_time
                        result.wafer_key = item.wafer_key
                        result.defect_id = item.defect_id
                        result.role = role
                        result.image_data = (item.request_id + ":" + role).encode()
                        result.content_type = "image/png"
                payload = response.SerializeToString()
                sink.write(struct.pack(">I", len(payload)) + payload)
                sink.flush()
            open({str(closed_marker)!r}, "w").close()
            """
        ),
        encoding="utf-8",
    )
    executable.chmod(0o755)
    factory = LocalJobImageSourceFactory(binary_path=str(executable))

    async with factory.open() as source:
        first = [
            item
            async for item in source.resolve_patch_images(
                source_format="filesystem.role-paths.v1",
                roles=["patch_template", "patch_defective"],
                items=[
                    {
                        "request_id": "first",
                        "sample_id": "sample-1",
                        "inspection_time": "20260816_100000",
                        "wafer_key": 42,
                        "defect_id": "1",
                        "role_paths": {
                            "patch_template": "sample-1/template.png"
                        },
                    },
                    {
                        "request_id": "second",
                        "sample_id": "sample-2",
                        "inspection_time": "20260816_100000",
                        "wafer_key": 42,
                        "defect_id": "2",
                    },
                ],
            )
        ]
        second = [
            item
            async for item in source.resolve_patch_images(
                source_format="filesystem.role-paths.v1",
                roles=["patch_template"],
                items=[
                    {
                        "request_id": "third",
                        "sample_id": "sample-3",
                        "inspection_time": "20260816_100000",
                        "wafer_key": 42,
                        "defect_id": "3",
                    }
                ],
            )
        ]
        assert not closed_marker.exists()

    assert [
        (item["request_id"], item["role"], item["image_data"]) for item in first
    ] == [
        ("first", "patch_template", b"first:patch_template"),
        ("first", "patch_defective", b"first:patch_defective"),
        ("second", "patch_template", b"second:patch_template"),
        ("second", "patch_defective", b"second:patch_defective"),
    ]
    assert second[0]["request_id"] == "third"
    assert closed_marker.exists()
