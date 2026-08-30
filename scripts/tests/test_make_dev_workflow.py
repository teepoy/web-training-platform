from __future__ import annotations

from pathlib import Path
import re
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class DevComposeWorkflowTests(unittest.TestCase):
    def test_up_dev_rebuilds_changed_application_images(self) -> None:
        docker_makefile = (REPOSITORY_ROOT / "make" / "docker.mk").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "docker compose -f $(COMPOSE_DEV) up -d --build postgres minio redis "
            "label-studio prefect-server sc-upstream image-parser",
            docker_makefile,
        )
        dependency_start = (
            "docker compose -f $(COMPOSE_DEV) up -d --build postgres minio redis"
        )
        parser_restart = "docker compose -f $(COMPOSE_DEV) restart image-parser"
        platform_prepare = (
            "docker compose -f $(COMPOSE_DEV) --profile ops run --rm prepare-platform"
        )
        self.assertIn(parser_restart, docker_makefile)
        self.assertLess(
            docker_makefile.index(dependency_start),
            docker_makefile.index(parser_restart),
        )
        self.assertLess(
            docker_makefile.index(parser_restart),
            docker_makefile.index(platform_prepare),
        )
        self.assertIn(
            "docker compose -f $(COMPOSE_DEV) up -d --build $(ARGS)",
            docker_makefile,
        )

    def test_up_dev_converges_the_development_superadmin(self) -> None:
        root_makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
        docker_makefile = (REPOSITORY_ROOT / "make" / "docker.mk").read_text(
            encoding="utf-8"
        )

        self.assertRegex(
            root_makefile,
            re.compile(
                r"^DEV_SUPERADMIN_EMAIL\s+\?=\s+seed@example\.com$", re.MULTILINE
            ),
        )
        self.assertRegex(
            root_makefile,
            re.compile(r"^DEV_SUPERADMIN_PASSWORD\s+\?=\s+seed1234$", re.MULTILINE),
        )
        self.assertRegex(
            root_makefile,
            re.compile(
                r"^DEV_SUPERADMIN_NAME\s+\?=\s+Development Admin$", re.MULTILINE
            ),
        )

        prepare = (
            "docker compose -f $(COMPOSE_DEV) --profile ops run --rm prepare-platform"
        )
        bootstrap = "$(MAKE) create-superadmin"
        self.assertIn(bootstrap, docker_makefile)
        self.assertLess(
            docker_makefile.index(prepare), docker_makefile.index(bootstrap)
        )
        self.assertIn("EMAIL='$(DEV_SUPERADMIN_EMAIL)'", docker_makefile)
        self.assertIn("PASSWORD='$(DEV_SUPERADMIN_PASSWORD)'", docker_makefile)
        self.assertIn("NAME='$(DEV_SUPERADMIN_NAME)'", docker_makefile)


if __name__ == "__main__":
    unittest.main()
