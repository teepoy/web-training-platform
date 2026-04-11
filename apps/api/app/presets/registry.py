"""Preset registry — loads, validates, and caches preset YAML files.

Scans a directory tree for ``preset.yaml`` files at startup, parses each
into a :class:`PresetSpec`, and serves them as a read-only in-memory
registry.  The API exposes ``list`` and ``get`` from this registry instead
of querying the database.

Supports optional hot-reload via :meth:`reload` (config-only change path).
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import yaml

from app.presets.schema import PresetSpec

logger = logging.getLogger(__name__)


class PresetRegistryError(Exception):
    """Raised when a preset file fails validation."""


class PresetEntry:
    """Wrapper around a validated PresetSpec with file metadata."""

    __slots__ = ("spec", "file_path", "content_hash")

    def __init__(self, spec: PresetSpec, file_path: Path, content_hash: str) -> None:
        self.spec = spec
        self.file_path = file_path
        self.content_hash = content_hash


class PresetRegistry:
    """In-memory registry of engineer-managed presets.

    Parameters
    ----------
    presets_dir:
        Root directory to scan for ``preset.yaml`` files.
        Each preset should be in its own subdirectory:
        ``presets/<preset-id>/preset.yaml``.
    strict:
        When True (default), raise on invalid presets at startup.
        When False, log a warning and skip invalid presets.
    """

    def __init__(self, presets_dir: str | Path, *, strict: bool = True) -> None:
        self._root = Path(presets_dir)
        self._strict = strict
        self._presets: dict[str, PresetEntry] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> int:
        """Scan the preset directory, parse and validate all presets.

        Returns the number of successfully loaded presets.
        Raises :class:`PresetRegistryError` in strict mode on any failure.
        """
        self._presets.clear()

        if not self._root.is_dir():
            msg = f"Presets directory does not exist: {self._root}"
            if self._strict:
                raise PresetRegistryError(msg)
            logger.warning(msg)
            return 0

        loaded = 0
        for preset_file in sorted(self._root.rglob("preset.yaml")):
            try:
                entry = self._load_single(preset_file)
                if entry.spec.id in self._presets:
                    raise PresetRegistryError(
                        f"Duplicate preset id '{entry.spec.id}' in "
                        f"{preset_file} and {self._presets[entry.spec.id].file_path}"
                    )
                self._presets[entry.spec.id] = entry
                loaded += 1
                logger.info("Loaded preset '%s' (v%s) from %s", entry.spec.id, entry.spec.version, preset_file)
            except Exception as exc:
                if self._strict:
                    raise PresetRegistryError(f"Failed to load {preset_file}: {exc}") from exc
                logger.warning("Skipping invalid preset %s: %s", preset_file, exc)

        logger.info("Preset registry loaded: %d presets from %s", loaded, self._root)
        return loaded

    def reload(self) -> int:
        """Re-scan and reload all presets (for config-only hot-reload)."""
        return self.load()

    def list_presets(self, *, include_deprecated: bool = False) -> list[PresetSpec]:
        """Return all loaded presets.

        Parameters
        ----------
        include_deprecated:
            When False (default), presets with ``deprecated: true`` are excluded.
        """
        result = []
        for entry in self._presets.values():
            if not include_deprecated and entry.spec.deprecated:
                continue
            result.append(entry.spec)
        return result

    def get_preset(self, preset_id: str) -> PresetSpec | None:
        """Return a single preset by ID, or None if not found."""
        entry = self._presets.get(preset_id)
        return entry.spec if entry else None

    def get_preset_hash(self, preset_id: str) -> str | None:
        """Return the content hash of a preset file, or None if not found."""
        entry = self._presets.get(preset_id)
        return entry.content_hash if entry else None

    @property
    def count(self) -> int:
        return len(self._presets)

    # ------------------------------------------------------------------
    # Serialization helpers (for API responses)
    # ------------------------------------------------------------------

    def preset_to_api_dict(self, spec: PresetSpec) -> dict[str, Any]:
        """Convert a PresetSpec to the API response shape.

        This bridges the new file-backed preset format to the existing
        API response contract so the frontend doesn't break during migration.
        """
        return {
            "id": spec.id,
            "name": spec.name,
            "version": spec.version,
            "description": spec.description,
            "tags": spec.tags,
            "deprecated": spec.deprecated,
            "trainable": spec.trainable,
            "model": spec.model.model_dump(mode="json"),
            "train": spec.train.model_dump(mode="json"),
            "predict": spec.predict.model_dump(mode="json"),
            "test": spec.test.model_dump(mode="json") if spec.test else None,
            "convert": spec.convert.model_dump(mode="json") if spec.convert else None,
            "runtime": spec.runtime.model_dump(mode="json"),
            "compatibility": spec.compatibility.model_dump(mode="json"),
            # Legacy compat fields so old frontend/SDK still work
            "model_spec": {
                "framework": spec.model.framework,
                "base_model": spec.model.base_model,
            },
            "omegaconf_yaml": "",
            "dataloader_ref": spec.train.dataloader.ref if spec.train.dataloader else "",
            "org_id": None,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_single(self, preset_file: Path) -> PresetEntry:
        """Load and validate a single preset.yaml file."""
        raw_bytes = preset_file.read_bytes()
        content_hash = hashlib.sha256(raw_bytes).hexdigest()

        raw = yaml.safe_load(raw_bytes.decode("utf-8"))
        if not isinstance(raw, dict):
            raise PresetRegistryError(f"Expected a YAML mapping in {preset_file}")

        spec = PresetSpec(**raw)

        # Validate that directory name matches preset id (convention, not hard requirement)
        dir_name = preset_file.parent.name
        if dir_name != spec.id:
            logger.warning(
                "Preset directory name '%s' does not match preset id '%s' in %s",
                dir_name,
                spec.id,
                preset_file,
            )

        return PresetEntry(spec=spec, file_path=preset_file, content_hash=content_hash)
