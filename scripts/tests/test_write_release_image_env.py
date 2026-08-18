from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from write_release_image_env import (  # noqa: E402
    render_release_image_env,
    validate_release_image_env,
    write_release_image_env,
)


class ReleaseImageEnvTest(unittest.TestCase):
    def test_renders_all_release_images_with_content_digests(self) -> None:
        digest = f"sha256:{'a' * 64}"
        digests = {
            component: digest
            for component in (
                "api",
                "web",
                "cpu-worker",
                "gpu-worker",
                "sc-upstream",
                "image-parser",
            )
        }

        rendered = render_release_image_env(
            registry="ghcr.io",
            repository="teepoy/web-training-platform",
            digests=digests,
        )

        self.assertEqual(
            rendered.splitlines(),
            [
                f"FINETUNE_API_IMAGE=ghcr.io/teepoy/web-training-platform-api@{digest}",
                f"FINETUNE_WEB_IMAGE=ghcr.io/teepoy/web-training-platform-web@{digest}",
                f"FINETUNE_CPU_WORKER_IMAGE=ghcr.io/teepoy/web-training-platform-cpu-worker@{digest}",
                f"FINETUNE_GPU_WORKER_IMAGE=ghcr.io/teepoy/web-training-platform-gpu-worker@{digest}",
                f"SC_UPSTREAM_IMAGE=ghcr.io/teepoy/web-training-platform-sc-upstream@{digest}",
                f"IMAGE_PARSER_IMAGE=ghcr.io/teepoy/web-training-platform-image-parser@{digest}",
            ],
        )

    def test_rejects_missing_or_invalid_digests(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing component digests"):
            render_release_image_env(
                registry="ghcr.io",
                repository="teepoy/web-training-platform",
                digests={"api": f"sha256:{'a' * 64}"},
            )

        with self.assertRaisesRegex(ValueError, "invalid sha256 digest"):
            render_release_image_env(
                registry="ghcr.io",
                repository="teepoy/web-training-platform",
                digests={
                    component: "sha256:deadbeef"
                    for component in (
                        "api",
                        "web",
                        "cpu-worker",
                        "gpu-worker",
                        "sc-upstream",
                        "image-parser",
                    )
                },
            )

    def test_rejects_noncanonical_repository_names(self) -> None:
        digest = f"sha256:{'b' * 64}"
        digests = {
            component: digest
            for component in (
                "api",
                "web",
                "cpu-worker",
                "gpu-worker",
                "sc-upstream",
                "image-parser",
            )
        }
        for repository in ("web-training-platform", "TeePoy/platform", "owner/"):
            with (
                self.subTest(repository=repository),
                self.assertRaisesRegex(ValueError, "lowercase owner/name"),
            ):
                render_release_image_env(
                    registry="ghcr.io",
                    repository=repository,
                    digests=digests,
                )

    def test_writes_to_existing_absolute_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "release-images.env"
            digest = f"sha256:{'c' * 64}"

            write_release_image_env(
                output=output,
                registry="ghcr.io",
                repository="teepoy/web-training-platform",
                digests={
                    component: digest
                    for component in (
                        "api",
                        "web",
                        "cpu-worker",
                        "gpu-worker",
                        "sc-upstream",
                        "image-parser",
                    )
                },
            )

            self.assertTrue(output.is_file())
            self.assertEqual(output.stat().st_mode & 0o777, 0o644)
            validate_release_image_env(
                content=output.read_text(encoding="utf-8"),
                registry="ghcr.io",
                repository="teepoy/web-training-platform",
            )

    def test_rejects_incomplete_existing_manifest(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing release image entries"):
            validate_release_image_env(
                content=(
                    "FINETUNE_API_IMAGE="
                    f"ghcr.io/teepoy/web-training-platform-api@sha256:{'d' * 64}\n"
                ),
                registry="ghcr.io",
                repository="teepoy/web-training-platform",
            )


if __name__ == "__main__":
    unittest.main()
