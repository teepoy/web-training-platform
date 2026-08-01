from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ScDataScope:
    kind: Literal["inspection", "dataset"]
    identity: str
    org_id: str

    @classmethod
    def inspection(
        cls, *, inspection_time: str, wafer_key: int, org_id: str
    ) -> ScDataScope:
        return cls(
            kind="inspection",
            identity=f"{inspection_time}/{wafer_key}",
            org_id=org_id,
        )

    @classmethod
    def dataset(cls, *, dataset_id: str, org_id: str) -> ScDataScope:
        return cls(kind="dataset", identity=dataset_id, org_id=org_id)

    @property
    def public_name(self) -> str:
        return f"{self.kind}:{self.identity}"

    @property
    def cache_name(self) -> str:
        return f"org:{self.org_id}:{self.public_name}"
