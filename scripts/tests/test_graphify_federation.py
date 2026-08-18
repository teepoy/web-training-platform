from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from graphify_federation import (  # noqa: E402
    FederationError,
    _corpus_hash,
    _merge_extractions,
    _resolve_context_names,
    _suppress_noise,
    _validate_required_paths,
    context_graph_path,
    select_context_files,
    validate_manifest,
)


def _manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "graphify_version": "0.8.34",
        "root_context": "architecture-contracts",
        "output_dir": "graphify-out/contexts",
        "semantic_overlay": "semantic.json",
        "bridge_overlay": "bridges.json",
        "global_excludes": ["**/generated/**", "**/__pycache__/**"],
        "base_excludes": ["**/tests/**", "**/*.spec.ts"],
        "contexts": [
            {
                "name": "architecture-contracts",
                "description": "contracts",
                "roots": ["src"],
                "max_source_files": 10,
                "max_nodes": 100,
                "overlays": {"tests": {"roots": ["src/tests"]}},
            },
            {
                "name": "data-resources",
                "description": "data",
                "roots": ["data"],
                "max_source_files": 10,
                "max_nodes": 100,
            },
        ],
    }


class GraphifyFederationTest(unittest.TestCase):
    def test_selects_base_code_and_keeps_tests_as_explicit_overlay(self) -> None:
        manifest = _manifest()
        context = manifest["contexts"][0]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src" / "tests").mkdir(parents=True)
            (root / "src" / "generated").mkdir(parents=True)
            (root / "data").mkdir()
            (root / "src" / "service.py").write_text("def run(): pass\n")
            (root / "src" / "view.vue").write_text("<template />\n")
            (root / "src" / "tests" / "test_service.py").write_text(
                "def test_run(): pass\n"
            )
            (root / "src" / "generated" / "client.ts").write_text(
                "export const client = true\n"
            )

            base_files, base_count = select_context_files(
                manifest, context, project_root=root
            )
            overlay_files, overlay_base_count = select_context_files(
                manifest, context, project_root=root, overlays=["tests"]
            )

        self.assertEqual([path.name for path in base_files], ["service.py", "view.vue"])
        self.assertEqual(base_count, 2)
        self.assertEqual(
            [path.name for path in overlay_files],
            ["service.py", "test_service.py", "view.vue"],
        )
        self.assertEqual(overlay_base_count, 2)

    def test_rejects_unknown_overlay_instead_of_guessing(self) -> None:
        manifest = _manifest()
        context = manifest["contexts"][0]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "data").mkdir()
            (root / "src" / "service.py").write_text("def run(): pass\n")
            with self.assertRaisesRegex(FederationError, "does not define overlay"):
                select_context_files(
                    manifest, context, project_root=root, overlays=["migrations"]
                )

    def test_context_selection_is_explicit_and_deterministic(self) -> None:
        manifest = _manifest()

        self.assertEqual(
            _resolve_context_names(manifest, ["data-resources"]),
            ["data-resources"],
        )
        self.assertEqual(
            _resolve_context_names(manifest, ["all"]),
            ["architecture-contracts", "data-resources"],
        )
        with self.assertRaisesRegex(FederationError, "unknown context"):
            _resolve_context_names(manifest, ["missing"])

    def test_overlay_graph_has_separate_output_path(self) -> None:
        manifest = _manifest()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            base = context_graph_path(
                manifest, "architecture-contracts", project_root=root
            )
            overlay = context_graph_path(
                manifest,
                "architecture-contracts",
                project_root=root,
                overlays=["tests"],
            )

        self.assertEqual(
            base, root / "graphify-out/contexts/architecture-contracts/graph.json"
        )
        self.assertEqual(
            overlay,
            root
            / "graphify-out/contexts/architecture-contracts/overlays/tests/graph.json",
        )

    def test_semantic_and_bridge_overlays_keep_first_stable_node(self) -> None:
        merged = _merge_extractions(
            {
                "nodes": [
                    {
                        "id": "contract",
                        "label": "AST contract",
                        "file_type": "code",
                        "source_file": "contract.py",
                    }
                ],
                "edges": [],
            },
            {
                "nodes": [
                    {
                        "id": "contract",
                        "label": "duplicate",
                        "file_type": "concept",
                        "source_file": "contract.md",
                    },
                    {
                        "id": "consumer",
                        "label": "Consumer",
                        "file_type": "concept",
                        "source_file": "contract.md",
                    },
                ],
                "edges": [
                    {
                        "source": "contract",
                        "target": "consumer",
                        "relation": "used_by",
                        "confidence": "EXTRACTED",
                        "source_file": "contract.md",
                    }
                ],
            },
        )

        self.assertEqual(
            [node["id"] for node in merged["nodes"]], ["contract", "consumer"]
        )
        self.assertEqual(merged["nodes"][0]["label"], "AST contract")
        self.assertEqual(len(merged["edges"]), 1)

    def test_explicit_noise_labels_remove_nodes_and_incident_edges(self) -> None:
        extraction = {
            "nodes": [
                {"id": "base", "label": "BaseModel"},
                {"id": "dataset", "label": "Dataset"},
            ],
            "edges": [
                {"source": "dataset", "target": "base"},
                {"source": "dataset", "target": "dataset"},
            ],
            "hyperedges": [{"id": "types", "nodes": ["base", "dataset", "other"]}],
        }

        cleaned = _suppress_noise(extraction, ["BaseModel"])

        self.assertEqual([node["id"] for node in cleaned["nodes"]], ["dataset"])
        self.assertEqual(cleaned["edges"], [{"source": "dataset", "target": "dataset"}])
        self.assertEqual(cleaned["hyperedges"][0]["nodes"], ["dataset", "other"])

    def test_manifest_requires_named_root_context(self) -> None:
        manifest = _manifest()
        manifest["root_context"] = "missing"

        with self.assertRaisesRegex(FederationError, "unknown root_context"):
            validate_manifest(manifest)

    def test_required_paths_are_checked_in_edge_direction(self) -> None:
        manifest = _manifest()
        manifest["required_directed_paths"] = [
            {
                "name": "a to c",
                "context": "architecture-contracts",
                "nodes": ["a", "b", "c"],
            }
        ]
        graph = {
            "nodes": [{"id": node} for node in ("a", "b", "c")],
            "links": [
                {"source": "a", "target": "b"},
                {"source": "c", "target": "b"},
            ],
        }

        with self.assertRaisesRegex(FederationError, "b->c"):
            _validate_required_paths(manifest, {"architecture-contracts": graph})

    def test_corpus_hash_changes_with_content_not_argument_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "a.py"
            second = root / "b.py"
            first.write_text("a = 1\n")
            second.write_text("b = 2\n")

            initial = _corpus_hash([first, second], project_root=root)
            reordered = _corpus_hash([second, first], project_root=root)
            second.write_text("b = 3\n")
            changed = _corpus_hash([first, second], project_root=root)

        self.assertEqual(initial, reordered)
        self.assertNotEqual(initial, changed)

    def test_repository_manifest_is_valid_json(self) -> None:
        manifest_path = SCRIPTS_DIR.parent / "graphify" / "federation.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        validate_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
