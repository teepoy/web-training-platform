"""Compatibility shims for ML runtime service protocols."""

from __future__ import annotations

from importlib import import_module

_contracts = import_module("platform_runtime.contracts")

ArtifactStorage = _contracts.ArtifactStorage
EmbeddingClient = _contracts.EmbeddingClient
LlmClient = _contracts.LlmClient

__all__ = ["ArtifactStorage", "EmbeddingClient", "LlmClient"]
