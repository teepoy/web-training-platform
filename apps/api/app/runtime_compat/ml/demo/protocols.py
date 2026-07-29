"""Worker-only demo ML runtime service protocol re-exports."""

from __future__ import annotations

from app.shared.domain.runtime import ArtifactStorage, EmbeddingClient, LlmClient

__all__ = ["ArtifactStorage", "EmbeddingClient", "LlmClient"]
