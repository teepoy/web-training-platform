from __future__ import annotations

from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class DevComposeWorkflowTests(unittest.TestCase):
    def test_up_dev_rebuilds_changed_application_images(self) -> None:
        docker_makefile = (REPOSITORY_ROOT / "make" / "docker.mk").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "docker compose -f $(COMPOSE_DEV) up -d --build $(ARGS)",
            docker_makefile,
        )


if __name__ == "__main__":
    unittest.main()
