from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

RuntimeDeploymentOwner = Literal["local_compat", "external"]
RuntimeResourceProfile = Literal["cpu", "gpu"]
MissingImagePolicy = Literal["fail", "skip"]


@dataclass(frozen=True)
class RuntimeDeploymentRoute:
    catalog_id: str
    deployment: str
    input_contract: str
    output_contract: str
    resource_profile: RuntimeResourceProfile
    owner: RuntimeDeploymentOwner
    algo_id: str | None = None
    algo_version: str | None = None
    code_version: str | None = None
    missing_image_policy: MissingImagePolicy | None = None

    @classmethod
    def from_mapping(
        cls,
        catalog_id: str,
        raw: Any,
        *,
        section: str,
    ) -> RuntimeDeploymentRoute:
        if not isinstance(raw, dict):
            raise RuntimeError(
                f"runtime_routing.{section}.{catalog_id} must be a mapping"
            )
        required = (
            "deployment",
            "input_contract",
            "output_contract",
            "resource_profile",
            "owner",
        )
        missing = [field for field in required if not str(raw.get(field, ""))]
        if missing:
            raise RuntimeError(
                "Missing runtime routing fields for "
                f"runtime_routing.{section}.{catalog_id}: {', '.join(missing)}"
            )
        owner = str(raw["owner"])
        if owner not in {"local_compat", "external"}:
            raise RuntimeError(
                f"runtime_routing.{section}.{catalog_id}.owner must be "
                "'local_compat' or 'external'"
            )
        resource_profile = str(raw["resource_profile"])
        if resource_profile not in {"cpu", "gpu"}:
            raise RuntimeError(
                f"runtime_routing.{section}.{catalog_id}.resource_profile must be "
                "'cpu' or 'gpu'"
            )
        missing_image_policy_raw = raw.get("missing_image_policy")
        if missing_image_policy_raw is not None and str(
            missing_image_policy_raw
        ) not in {"fail", "skip"}:
            raise RuntimeError(
                f"runtime_routing.{section}.{catalog_id}.missing_image_policy "
                "must be 'fail' or 'skip'"
            )
        return cls(
            catalog_id=catalog_id,
            deployment=str(raw["deployment"]),
            input_contract=str(raw["input_contract"]),
            output_contract=str(raw["output_contract"]),
            resource_profile=cast(RuntimeResourceProfile, resource_profile),
            owner=cast(RuntimeDeploymentOwner, owner),
            algo_id=str(raw["algo_id"]) if raw.get("algo_id") is not None else None,
            algo_version=(
                str(raw["algo_version"])
                if raw.get("algo_version") is not None
                else None
            ),
            code_version=(
                str(raw["code_version"])
                if raw.get("code_version") is not None
                else None
            ),
            missing_image_policy=cast(
                MissingImagePolicy | None,
                (
                    str(missing_image_policy_raw)
                    if missing_image_policy_raw is not None
                    else None
                ),
            ),
        )

    def to_parameters(self) -> dict[str, Any]:
        return {
            "catalog_id": self.catalog_id,
            "input_contract": self.input_contract,
            "output_contract": self.output_contract,
            "resource_profile": self.resource_profile,
            "owner": self.owner,
            "algo_id": self.algo_id,
            "algo_version": self.algo_version,
            "code_version": self.code_version,
            "missing_image_policy": self.missing_image_policy,
        }
