#!/usr/bin/env python3
"""Build and query bounded-context Graphify graphs for this monorepo."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "graphify" / "federation.json"

CODE_SUFFIXES = frozenset(
    {
        ".astro",
        ".bash",
        ".c",
        ".cc",
        ".cpp",
        ".cxx",
        ".go",
        ".h",
        ".hpp",
        ".java",
        ".js",
        ".json",
        ".jsx",
        ".mjs",
        ".py",
        ".rs",
        ".sh",
        ".sql",
        ".svelte",
        ".ts",
        ".tsx",
        ".vue",
    }
)


class FederationError(RuntimeError):
    """Raised when the Graphify federation contract is invalid."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FederationError(f"missing Graphify file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise FederationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise FederationError(f"expected a JSON object in {path}")
    return data


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = _read_json(path)
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != 1:
        raise FederationError("graphify/federation.json schema_version must be 1")
    if not isinstance(manifest.get("graphify_version"), str):
        raise FederationError("graphify_version must be an exact version string")
    contexts = manifest.get("contexts")
    if not isinstance(contexts, list) or not contexts:
        raise FederationError("contexts must be a non-empty list")

    seen: set[str] = set()
    for context in contexts:
        if not isinstance(context, dict):
            raise FederationError("every context must be an object")
        name = context.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9-]+", name):
            raise FederationError(f"invalid context name: {name!r}")
        if name in seen:
            raise FederationError(f"duplicate context name: {name}")
        seen.add(name)
        roots = context.get("roots", [])
        includes = context.get("include_globs", [])
        if not roots and not includes:
            raise FederationError(f"context {name} has no roots or include_globs")
        if not isinstance(context.get("max_source_files"), int):
            raise FederationError(f"context {name} must declare max_source_files")
        if not isinstance(context.get("max_nodes"), int):
            raise FederationError(f"context {name} must declare max_nodes")

    root_context = manifest.get("root_context")
    if root_context not in seen:
        raise FederationError(f"unknown root_context: {root_context!r}")
    for required in manifest.get("required_directed_paths", []):
        if not isinstance(required, dict) or not isinstance(required.get("name"), str):
            raise FederationError("every required_directed_path must have a name")
        if required.get("context") not in seen:
            raise FederationError(
                f"required path {required['name']!r} references an unknown context"
            )
        nodes = required.get("nodes")
        if (
            not isinstance(nodes, list)
            or len(nodes) < 2
            or not all(isinstance(node, str) and node for node in nodes)
        ):
            raise FederationError(
                f"required path {required['name']!r} must contain at least two node ids"
            )


def contexts_by_name(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {context["name"]: context for context in manifest["contexts"]}


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _collect_entry(
    project_root: Path,
    entry: str,
    *,
    exclude_patterns: Sequence[str],
) -> set[Path]:
    candidate = project_root / entry
    if not candidate.exists():
        raise FederationError(f"configured Graphify path does not exist: {entry}")
    paths = [candidate] if candidate.is_file() else candidate.rglob("*")
    selected: set[Path] = set()
    for path in paths:
        if not path.is_file() or path.suffix not in CODE_SUFFIXES:
            continue
        relative = path.relative_to(project_root).as_posix()
        if not _matches_any(relative, exclude_patterns):
            selected.add(path.resolve())
    return selected


def _collect_glob(
    project_root: Path,
    pattern: str,
    *,
    exclude_patterns: Sequence[str],
) -> set[Path]:
    selected: set[Path] = set()
    for path in project_root.glob(pattern):
        if not path.is_file() or path.suffix not in CODE_SUFFIXES:
            continue
        relative = path.relative_to(project_root).as_posix()
        if not _matches_any(relative, exclude_patterns):
            selected.add(path.resolve())
    return selected


def select_context_files(
    manifest: dict[str, Any],
    context: dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    overlays: Sequence[str] = (),
) -> tuple[list[Path], int]:
    global_excludes = tuple(manifest.get("global_excludes", []))
    base_excludes = global_excludes + tuple(manifest.get("base_excludes", []))
    selected: set[Path] = set()

    for root in context.get("roots", []):
        selected.update(
            _collect_entry(project_root, root, exclude_patterns=base_excludes)
        )
    for pattern in context.get("include_globs", []):
        selected.update(
            _collect_glob(project_root, pattern, exclude_patterns=base_excludes)
        )
    base_count = len(selected)

    configured_overlays = context.get("overlays", {})
    for overlay_name in overlays:
        overlay = configured_overlays.get(overlay_name)
        if overlay is None:
            raise FederationError(
                f"context {context['name']} does not define overlay {overlay_name!r}"
            )
        for root in overlay.get("roots", []):
            selected.update(
                _collect_entry(project_root, root, exclude_patterns=global_excludes)
            )
        for pattern in overlay.get("include_globs", []):
            selected.update(
                _collect_glob(project_root, pattern, exclude_patterns=global_excludes)
            )

    return sorted(selected), base_count


def context_graph_path(
    manifest: dict[str, Any],
    context_name: str,
    *,
    project_root: Path = PROJECT_ROOT,
    overlays: Sequence[str] = (),
) -> Path:
    context_dir = project_root / manifest["output_dir"] / context_name
    if overlays:
        overlay_key = "+".join(sorted(overlays))
        context_dir = context_dir / "overlays" / overlay_key
    return context_dir / "graph.json"


def _graphify_version_from_cli() -> str:
    executable = shutil.which("graphify")
    if executable is None:
        raise FederationError(
            "graphify is not installed; install the pinned graphifyy version first"
        )
    result = subprocess.run(
        [executable, "--version"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    match = re.search(r"graphify\s+([0-9]+(?:\.[0-9]+){2})", result.stdout)
    if match is None:
        raise FederationError("unable to determine installed graphify version")
    return match.group(1)


def _assert_graphify_version(manifest: dict[str, Any]) -> None:
    expected = manifest["graphify_version"]
    actual = _graphify_version_from_cli()
    if actual != expected:
        raise FederationError(
            f"graphify version mismatch: expected {expected}, installed {actual}"
        )


def _ensure_graphify_python() -> None:
    try:
        import graphify  # noqa: F401

        return
    except ImportError:
        pass

    executable = shutil.which("graphify")
    if executable is None:
        raise FederationError("graphify executable is not available on PATH")
    first_line = Path(executable).read_text(encoding="utf-8").splitlines()[0]
    if not first_line.startswith("#!"):
        raise FederationError("graphify launcher does not declare its Python runtime")
    interpreter = first_line.removeprefix("#!").strip()
    if not Path(interpreter).is_file():
        raise FederationError(f"graphify Python runtime does not exist: {interpreter}")
    os.execv(interpreter, [interpreter, str(Path(__file__).resolve()), *sys.argv[1:]])


def _merge_extractions(*extractions: dict[str, Any]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    hyperedges: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()
    input_tokens = 0
    output_tokens = 0

    for extraction in extractions:
        for node in extraction.get("nodes", []):
            node_id = node.get("id")
            if node_id not in seen_nodes:
                seen_nodes.add(node_id)
                nodes.append(node)
        edges.extend(extraction.get("edges", extraction.get("links", [])))
        hyperedges.extend(extraction.get("hyperedges", []))
        input_tokens += int(extraction.get("input_tokens", 0))
        output_tokens += int(extraction.get("output_tokens", 0))

    return {
        "nodes": nodes,
        "edges": edges,
        "hyperedges": hyperedges,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def _suppress_noise(
    extraction: dict[str, Any], labels: Sequence[str]
) -> dict[str, Any]:
    suppressed_labels = set(labels)
    suppressed_ids = {
        node["id"]
        for node in extraction.get("nodes", [])
        if node.get("label") in suppressed_labels
    }
    if not suppressed_ids:
        return extraction
    cleaned = dict(extraction)
    cleaned["nodes"] = [
        node
        for node in extraction.get("nodes", [])
        if node.get("id") not in suppressed_ids
    ]
    cleaned["edges"] = [
        edge
        for edge in extraction.get("edges", extraction.get("links", []))
        if edge.get("source") not in suppressed_ids
        and edge.get("target") not in suppressed_ids
    ]
    hyperedges: list[dict[str, Any]] = []
    for hyperedge in extraction.get("hyperedges", []):
        filtered = [
            node_id
            for node_id in hyperedge.get("nodes", [])
            if node_id not in suppressed_ids
        ]
        if len(filtered) >= 2:
            hyperedges.append({**hyperedge, "nodes": filtered})
    cleaned["hyperedges"] = hyperedges
    return cleaned


def _git_head(project_root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        capture_output=True,
        check=False,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _manifest_hash(manifest_path: Path) -> str:
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def _corpus_hash(files: Sequence[Path], *, project_root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(path.resolve() for path in files):
        relative = path.relative_to(project_root.resolve()).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _context_hash_inputs(
    manifest: dict[str, Any],
    context: dict[str, Any],
    files: Sequence[Path],
    *,
    project_root: Path,
) -> list[Path]:
    inputs = list(files)
    if context["name"] == manifest["root_context"]:
        inputs.extend(
            [
                project_root / manifest["semantic_overlay"],
                project_root / manifest["bridge_overlay"],
            ]
        )
    return inputs


def _write_context_report(
    output_dir: Path,
    *,
    context: dict[str, Any],
    files: Sequence[Path],
    overlays: Sequence[str],
    node_count: int,
    edge_count: int,
    community_count: int,
    commit: str | None,
) -> None:
    lines = [
        f"# Graphify: {context['name']}",
        "",
        context["description"],
        "",
        f"- Source files: {len(files)}",
        f"- Nodes: {node_count}",
        f"- Directed edges: {edge_count}",
        f"- Communities: {community_count}",
        f"- Overlays: {', '.join(overlays) if overlays else 'none'}",
        f"- Built from commit: `{commit or 'unknown'}`",
        "",
        "Use `make graphify-query CONTEXT={0} QUESTION='...'` to query this graph.".format(
            context["name"]
        ),
        "",
    ]
    (output_dir / "GRAPH_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def _annotate_graph_file(
    graph_path: Path,
    *,
    context: dict[str, Any],
    overlays: Sequence[str],
    manifest_path: Path,
    corpus_inputs: Sequence[Path],
) -> None:
    graph = _read_json(graph_path)
    metadata = graph.setdefault("graph", {})
    metadata.update(
        {
            "federation_context": context["name"],
            "federation_description": context["description"],
            "federation_overlays": list(overlays),
            "federation_manifest_sha256": _manifest_hash(manifest_path),
            "federation_corpus_sha256": _corpus_hash(
                corpus_inputs, project_root=PROJECT_ROOT
            ),
        }
    )
    graph_path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")


def _publish_root_graph(
    context_output: Path,
    *,
    project_root: Path,
    graphify_python: str,
) -> None:
    from graphify.export import backup_if_protected

    root_output = project_root / "graphify-out"
    root_output.mkdir(parents=True, exist_ok=True)
    backup_if_protected(root_output)
    for filename in (
        "graph.json",
        "graph.html",
        "GRAPH_REPORT.md",
        ".graphify_labels.json",
        ".graphify_analysis.json",
    ):
        source = context_output / filename
        if source.exists():
            shutil.copy2(source, root_output / filename)
    (root_output / ".graphify_python").write_text(graphify_python, encoding="utf-8")
    (root_output / ".graphify_root").write_text(str(project_root), encoding="utf-8")


def _write_federation_index(
    manifest: dict[str, Any],
    *,
    project_root: Path,
) -> None:
    records: list[dict[str, Any]] = []
    for context in manifest["contexts"]:
        graph_path = context_graph_path(
            manifest, context["name"], project_root=project_root
        )
        if not graph_path.exists():
            continue
        graph = _read_json(graph_path)
        records.append(
            {
                "name": context["name"],
                "description": context["description"],
                "graph": graph_path.relative_to(project_root).as_posix(),
                "nodes": len(graph.get("nodes", [])),
                "edges": len(graph.get("links", graph.get("edges", []))),
                "built_at_commit": graph.get("built_at_commit"),
                "aliases": context.get("aliases", []),
            }
        )
    index = {
        "schema_version": 1,
        "root_context": manifest["root_context"],
        "contexts": records,
    }
    output = project_root / "graphify-out" / "federation-index.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")


def build_context(
    manifest: dict[str, Any],
    context: dict[str, Any],
    *,
    manifest_path: Path,
    project_root: Path = PROJECT_ROOT,
    overlays: Sequence[str] = (),
    max_workers: int | None = None,
    no_cluster: bool = False,
) -> tuple[int, int]:
    from graphify.build import build_from_json
    from graphify.cluster import cluster
    from graphify.export import to_html, to_json
    from graphify.extract import extract

    files, base_count = select_context_files(
        manifest, context, project_root=project_root, overlays=overlays
    )
    max_source_files = context["max_source_files"]
    if base_count > max_source_files:
        raise FederationError(
            f"context {context['name']} selects {base_count} base files; "
            f"explicit limit is {max_source_files}"
        )
    if not files:
        raise FederationError(f"context {context['name']} selected no code files")

    extraction = extract(
        list(files),
        cache_root=project_root,
        parallel=max_workers != 1,
        max_workers=max_workers,
    )
    if context["name"] == manifest["root_context"]:
        semantic = _read_json(project_root / manifest["semantic_overlay"])
        bridges = _read_json(project_root / manifest["bridge_overlay"])
        extraction = _merge_extractions(extraction, semantic, bridges)
    extraction = _suppress_noise(extraction, manifest.get("noise_labels", []))

    graph = build_from_json(extraction, directed=True, root=project_root)
    if graph.number_of_nodes() == 0:
        raise FederationError(f"context {context['name']} produced an empty graph")
    max_nodes = context["max_nodes"]
    if graph.number_of_nodes() > max_nodes:
        raise FederationError(
            f"context {context['name']} produced {graph.number_of_nodes()} nodes; "
            f"explicit limit is {max_nodes}"
        )

    communities = {0: list(graph.nodes())} if no_cluster else cluster(graph)
    output_dir = context_graph_path(
        manifest, context["name"], project_root=project_root, overlays=overlays
    ).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    graph_path = output_dir / "graph.json"
    commit = _git_head(project_root)
    written = to_json(
        graph,
        communities,
        str(graph_path),
        force=True,
        built_at_commit=commit,
    )
    if not written:
        raise FederationError(f"Graphify refused to write {graph_path}")
    labels = {str(key): f"Community {key}" for key in communities}
    (output_dir / ".graphify_labels.json").write_text(
        json.dumps(labels, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / ".graphify_analysis.json").write_text(
        json.dumps(
            {
                "context": context["name"],
                "communities": {str(key): value for key, value in communities.items()},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    to_html(
        graph,
        communities,
        str(output_dir / "graph.html"),
        community_labels={key: f"Community {key}" for key in communities},
        node_limit=max_nodes,
    )
    _annotate_graph_file(
        graph_path,
        context=context,
        overlays=overlays,
        manifest_path=manifest_path,
        corpus_inputs=_context_hash_inputs(
            manifest, context, files, project_root=project_root
        ),
    )
    _write_context_report(
        output_dir,
        context=context,
        files=files,
        overlays=overlays,
        node_count=graph.number_of_nodes(),
        edge_count=graph.number_of_edges(),
        community_count=len(communities),
        commit=commit,
    )
    if context["name"] == manifest["root_context"] and not overlays:
        _publish_root_graph(
            output_dir,
            project_root=project_root,
            graphify_python=sys.executable,
        )
    return graph.number_of_nodes(), graph.number_of_edges()


def _resolve_context_names(
    manifest: dict[str, Any], requested: Sequence[str]
) -> list[str]:
    available = contexts_by_name(manifest)
    if not requested or requested == ["all"]:
        return list(available)
    unknown = sorted(set(requested) - set(available))
    if unknown:
        raise FederationError(f"unknown context(s): {', '.join(unknown)}")
    if "all" in requested:
        raise FederationError("context 'all' cannot be combined with named contexts")
    return list(dict.fromkeys(requested))


def command_build(args: argparse.Namespace) -> None:
    manifest_path = args.manifest.resolve()
    manifest = load_manifest(manifest_path)
    _assert_graphify_version(manifest)
    _ensure_graphify_python()
    installed = importlib.metadata.version("graphifyy")
    if installed != manifest["graphify_version"]:
        raise FederationError(
            f"graphify runtime mismatch: expected {manifest['graphify_version']}, "
            f"loaded {installed}"
        )

    contexts = contexts_by_name(manifest)
    names = _resolve_context_names(manifest, args.context)
    for name in names:
        nodes, edges = build_context(
            manifest,
            contexts[name],
            manifest_path=manifest_path,
            overlays=args.overlay,
            max_workers=args.max_workers,
            no_cluster=args.no_cluster,
        )
        print(f"{name}: {nodes} nodes, {edges} directed edges")
    _write_federation_index(manifest, project_root=PROJECT_ROOT)


def command_list(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.manifest)
    contexts = contexts_by_name(manifest)
    names = _resolve_context_names(manifest, args.context)
    for name in names:
        context = contexts[name]
        files, base_count = select_context_files(
            manifest, context, overlays=args.overlay
        )
        suffix = f" (+{len(files) - base_count} overlay)" if args.overlay else ""
        print(f"{name}: {base_count} base files{suffix}")
        if args.files:
            for path in files:
                print(f"  {path.relative_to(PROJECT_ROOT).as_posix()}")


def _validate_overlay(path: Path, *, project_root: Path = PROJECT_ROOT) -> None:
    data = _read_json(path)
    node_ids = {
        node.get("id") for node in data.get("nodes", []) if isinstance(node, dict)
    }
    if None in node_ids:
        raise FederationError(f"overlay contains a node without an id: {path}")
    for edge in data.get("edges", []):
        if edge.get("source") not in node_ids or edge.get("target") not in node_ids:
            raise FederationError(f"overlay edge has a dangling endpoint: {path}")
    for hyperedge in data.get("hyperedges", []):
        missing = sorted(set(hyperedge.get("nodes", [])) - node_ids)
        if missing:
            raise FederationError(
                f"overlay hyperedge has dangling nodes in {path}: {', '.join(missing)}"
            )
    for item in [
        *data.get("nodes", []),
        *data.get("edges", []),
        *data.get("hyperedges", []),
    ]:
        source_file = item.get("source_file")
        if source_file and not (project_root / source_file).is_file():
            raise FederationError(
                f"overlay references a missing source file {source_file!r}: {path}"
            )


def _validate_built_graph_file(
    manifest: dict[str, Any],
    context: dict[str, Any],
    graph_path: Path,
    *,
    expected_manifest_hash: str,
) -> dict[str, Any]:
    graph = _read_json(graph_path)
    if graph.get("directed") is not True:
        raise FederationError(f"graph is not directed: {graph_path}")
    node_count = len(graph.get("nodes", []))
    if node_count > context["max_nodes"]:
        raise FederationError(
            f"graph {context['name']} exceeds max_nodes: {node_count}"
        )
    metadata = graph.get("graph", {})
    if metadata.get("federation_context") != context["name"]:
        raise FederationError(f"graph metadata mismatch: {graph_path}")
    if metadata.get("federation_manifest_sha256") != expected_manifest_hash:
        raise FederationError(
            f"graph was built from a different manifest: {graph_path}"
        )
    overlays = metadata.get("federation_overlays", [])
    _validate_requested_overlays(context, overlays)
    files, _ = select_context_files(manifest, context, overlays=overlays)
    hash_inputs = _context_hash_inputs(
        manifest, context, files, project_root=PROJECT_ROOT
    )
    expected_corpus_hash = _corpus_hash(hash_inputs, project_root=PROJECT_ROOT)
    if metadata.get("federation_corpus_sha256") != expected_corpus_hash:
        raise FederationError(f"graph corpus is stale: {graph_path}")
    return graph


def _check_built_graphs(
    manifest: dict[str, Any], *, manifest_path: Path = DEFAULT_MANIFEST
) -> None:
    graphs: dict[str, dict[str, Any]] = {}
    expected_manifest_hash = _manifest_hash(manifest_path)
    for context in manifest["contexts"]:
        graph_path = context_graph_path(manifest, context["name"])
        graph = _validate_built_graph_file(
            manifest,
            context,
            graph_path,
            expected_manifest_hash=expected_manifest_hash,
        )
        graphs[context["name"]] = graph
        overlay_root = graph_path.parent / "overlays"
        if overlay_root.exists():
            for overlay_graph_path in sorted(overlay_root.glob("*/graph.json")):
                _validate_built_graph_file(
                    manifest,
                    context,
                    overlay_graph_path,
                    expected_manifest_hash=expected_manifest_hash,
                )

    root_graph = _read_json(PROJECT_ROOT / "graphify-out" / "graph.json")
    root_name = root_graph.get("graph", {}).get("federation_context")
    if root_name != manifest["root_context"]:
        raise FederationError("root graph.json is not the architecture-contracts graph")
    root_metadata = root_graph.get("graph", {})
    base_metadata = graphs[manifest["root_context"]].get("graph", {})
    if root_metadata.get("federation_corpus_sha256") != base_metadata.get(
        "federation_corpus_sha256"
    ):
        raise FederationError("root graph.json does not match the base contract graph")

    _validate_required_paths(manifest, graphs)


def _validate_required_paths(
    manifest: dict[str, Any], graphs: dict[str, dict[str, Any]]
) -> None:
    for required in manifest.get("required_directed_paths", []):
        context_name = required["context"]
        graph = graphs.get(context_name)
        if graph is None:
            raise FederationError(
                f"required path {required['name']!r} references an unbuilt context"
            )
        node_ids = {node["id"] for node in graph.get("nodes", [])}
        links = graph.get("links", graph.get("edges", []))
        directed_edges = {(edge["source"], edge["target"]) for edge in links}
        required_nodes = required["nodes"]
        missing_nodes = [node for node in required_nodes if node not in node_ids]
        if missing_nodes:
            raise FederationError(
                f"required path {required['name']!r} is missing nodes: "
                f"{', '.join(missing_nodes)}"
            )
        missing_edges = [
            f"{source}->{target}"
            for source, target in zip(required_nodes, required_nodes[1:])
            if (source, target) not in directed_edges
        ]
        if missing_edges:
            raise FederationError(
                f"required directed path {required['name']!r} is broken: "
                f"{', '.join(missing_edges)}"
            )


def command_check(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.manifest)
    _assert_graphify_version(manifest)
    _validate_overlay(PROJECT_ROOT / manifest["semantic_overlay"])
    _validate_overlay(PROJECT_ROOT / manifest["bridge_overlay"])
    for context in manifest["contexts"]:
        files, base_count = select_context_files(manifest, context)
        if not files:
            raise FederationError(f"context {context['name']} selects no files")
        if base_count > context["max_source_files"]:
            raise FederationError(
                f"context {context['name']} selects {base_count} files; "
                f"limit is {context['max_source_files']}"
            )
        print(f"{context['name']}: {base_count} source files")
    if args.graphs:
        _check_built_graphs(manifest, manifest_path=args.manifest.resolve())
        print("built graphs: valid")


def command_route(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.manifest)
    question = args.question.casefold()
    scores: list[tuple[int, str]] = []
    for context in manifest["contexts"]:
        score = sum(
            len(alias)
            for alias in context.get("aliases", [])
            if alias.casefold() in question
        )
        if score:
            scores.append((score, context["name"]))
    if not scores:
        print(manifest["root_context"])
        return
    scores.sort(key=lambda item: (-item[0], item[1]))
    for _, name in scores:
        print(name)


def _run_graphify_with_graph(arguments: Sequence[str], graph_path: Path) -> None:
    if not graph_path.exists():
        raise FederationError(
            f"graph has not been built: {graph_path}; run graphify-build first"
        )
    executable = shutil.which("graphify")
    if executable is None:
        raise FederationError("graphify executable is not available on PATH")
    result = subprocess.run(
        [executable, *arguments, "--graph", str(graph_path)],
        cwd=PROJECT_ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise FederationError(
            f"graphify command failed with exit code {result.returncode}"
        )


def command_query(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.manifest)
    contexts = contexts_by_name(manifest)
    if args.context not in contexts:
        raise FederationError(f"unknown context: {args.context}")
    _validate_requested_overlays(contexts[args.context], args.overlay)
    _run_graphify_with_graph(
        ["query", args.question, "--budget", str(args.budget)],
        context_graph_path(manifest, args.context, overlays=args.overlay),
    )


def command_path(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.manifest)
    contexts = contexts_by_name(manifest)
    if args.context not in contexts:
        raise FederationError(f"unknown context: {args.context}")
    _validate_requested_overlays(contexts[args.context], args.overlay)
    _run_graphify_with_graph(
        ["path", args.source, args.target],
        context_graph_path(manifest, args.context, overlays=args.overlay),
    )


def _validate_requested_overlays(
    context: dict[str, Any], overlays: Sequence[str]
) -> None:
    configured = context.get("overlays", {})
    unknown = sorted(set(overlays) - set(configured))
    if unknown:
        raise FederationError(
            f"context {context['name']} does not define overlay(s): "
            f"{', '.join(unknown)}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and query the repository's federated Graphify graphs."
    )
    parser.add_argument(
        "--manifest", type=Path, default=DEFAULT_MANIFEST, help=argparse.SUPPRESS
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List contexts and selected files")
    list_parser.add_argument("--context", action="append", default=[])
    list_parser.add_argument("--overlay", action="append", default=[])
    list_parser.add_argument("--files", action="store_true")
    list_parser.set_defaults(handler=command_list)

    check_parser = subparsers.add_parser(
        "check", help="Validate the federation contract"
    )
    check_parser.add_argument("--graphs", action="store_true")
    check_parser.set_defaults(handler=command_check)

    build_parser_command = subparsers.add_parser(
        "build", help="Build one or all bounded-context graphs"
    )
    build_parser_command.add_argument("--context", action="append", default=[])
    build_parser_command.add_argument("--overlay", action="append", default=[])
    build_parser_command.add_argument("--max-workers", type=int)
    build_parser_command.add_argument("--no-cluster", action="store_true")
    build_parser_command.set_defaults(handler=command_build)

    route_parser = subparsers.add_parser(
        "route", help="Recommend explicit contexts for a question"
    )
    route_parser.add_argument("question")
    route_parser.set_defaults(handler=command_route)

    query_parser = subparsers.add_parser("query", help="Query one context graph")
    query_parser.add_argument("--context", required=True)
    query_parser.add_argument("--overlay", action="append", default=[])
    query_parser.add_argument("--budget", type=int, default=2000)
    query_parser.add_argument("question")
    query_parser.set_defaults(handler=command_query)

    path_parser = subparsers.add_parser("path", help="Find a path in one context graph")
    path_parser.add_argument("--context", required=True)
    path_parser.add_argument("--overlay", action="append", default=[])
    path_parser.add_argument("source")
    path_parser.add_argument("target")
    path_parser.set_defaults(handler=command_path)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.handler(args)
    except FederationError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
