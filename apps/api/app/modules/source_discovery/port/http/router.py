from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException

from app.modules.auth.port.http.deps import (
    get_current_org,
    get_current_user,
    require_admin,
)
from app.modules.source_discovery.domain.errors import (
    SourceDiscoveryConflictError,
    SourceDiscoveryError,
    SourceDiscoveryNotFoundError,
    SourceDiscoveryValidationError,
)
from app.modules.source_discovery.port.http.deps import SourceDiscoveryServiceDep
from app.modules.source_discovery.port.http.schemas import (
    BackfillPreviewRequest,
    BackfillPreviewResponse,
    BackfillRangeRequest,
    CreateImportProfileRequest,
    CreateMembershipRuleRequest,
    CreateMembershipRuleVersionRequest,
    CreateScAutomationPartitionRequest,
    CreateSourceConnectorRequest,
    DiscoveryRunResponse,
    ImportProfileVersionResponse,
    MembershipRuleResponse,
    MembershipSuppressionResponse,
    RunLiveDiscoveryRequest,
    ScAutomationPartitionResponse,
    SourceConnectorResponse,
    SourceProviderDescriptorResponse,
    SuppressSourceMemberRequest,
)
from app.shared.api.schemas import Organization, User


connectors_router = APIRouter(
    prefix="/api/v1/source-connectors", tags=["source-discovery"]
)
collections_router = APIRouter(
    prefix="/api/v1/dataset-collections", tags=["source-discovery"]
)
runs_router = APIRouter(prefix="/api/v1/discovery-runs", tags=["source-discovery"])


def _http_error(exc: SourceDiscoveryError) -> HTTPException:
    if isinstance(exc, SourceDiscoveryNotFoundError):
        status = 404
    elif isinstance(exc, SourceDiscoveryConflictError):
        status = 409
    elif isinstance(exc, SourceDiscoveryValidationError):
        status = 422
    else:
        status = 500
    return HTTPException(
        status_code=status, detail={"code": exc.code, "detail": str(exc)}
    )


@connectors_router.get(
    "/providers", response_model=list[SourceProviderDescriptorResponse]
)
async def list_source_providers(
    service: SourceDiscoveryServiceDep,
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[SourceProviderDescriptorResponse]:
    del current_user
    return [
        SourceProviderDescriptorResponse.from_domain(item)
        for item in service.list_provider_descriptors()
    ]


@connectors_router.post("", response_model=SourceConnectorResponse)
async def create_source_connector(
    payload: CreateSourceConnectorRequest,
    service: SourceDiscoveryServiceDep,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    _: Annotated[None, Depends(require_admin)],
) -> SourceConnectorResponse:
    try:
        connector = await service.create_connector(
            org_id=org.id,
            actor_id=current_user.id,
            provider_id=payload.provider_id,
            name=payload.name,
            config=cast(dict[str, object], payload.config),
        )
    except SourceDiscoveryError as exc:
        raise _http_error(exc) from exc
    return SourceConnectorResponse.from_domain(connector)


@connectors_router.get("", response_model=list[SourceConnectorResponse])
async def list_source_connectors(
    service: SourceDiscoveryServiceDep,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
) -> list[SourceConnectorResponse]:
    del current_user
    return [
        SourceConnectorResponse.from_domain(item)
        for item in await service.list_connectors(org.id)
    ]


@connectors_router.post(
    "/{connector_id}/import-profiles",
    response_model=ImportProfileVersionResponse,
)
async def create_import_profile(
    connector_id: str,
    payload: CreateImportProfileRequest,
    service: SourceDiscoveryServiceDep,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
    _: Annotated[None, Depends(require_admin)],
) -> ImportProfileVersionResponse:
    try:
        profile = await service.create_import_profile(
            org_id=org.id,
            actor_id=current_user.id,
            connector_id=connector_id,
            name=payload.name,
            settings=cast(dict[str, object], payload.settings),
        )
    except SourceDiscoveryError as exc:
        raise _http_error(exc) from exc
    return ImportProfileVersionResponse.from_domain(profile)


@connectors_router.get(
    "/{connector_id}/import-profiles",
    response_model=list[ImportProfileVersionResponse],
)
async def list_import_profiles(
    connector_id: str,
    service: SourceDiscoveryServiceDep,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
) -> list[ImportProfileVersionResponse]:
    del current_user
    try:
        profiles = await service.list_import_profiles(connector_id, org.id)
    except SourceDiscoveryError as exc:
        raise _http_error(exc) from exc
    return [ImportProfileVersionResponse.from_domain(item) for item in profiles]


@collections_router.post(
    "/{collection_id}/membership-rules", response_model=MembershipRuleResponse
)
async def create_membership_rule(
    collection_id: str,
    payload: CreateMembershipRuleRequest,
    service: SourceDiscoveryServiceDep,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
) -> MembershipRuleResponse:
    try:
        rule, version = await service.create_rule(
            collection_id=collection_id,
            org_id=org.id,
            actor_id=current_user.id,
            name=payload.name,
            connector_id=payload.connector_id,
            import_profile_version_id=payload.import_profile_version_id,
            condition=payload.condition.to_domain(),
        )
    except SourceDiscoveryError as exc:
        raise _http_error(exc) from exc
    return MembershipRuleResponse.from_domain(rule, version)


@collections_router.get(
    "/{collection_id}/membership-rules", response_model=list[MembershipRuleResponse]
)
async def list_membership_rules(
    collection_id: str,
    service: SourceDiscoveryServiceDep,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
) -> list[MembershipRuleResponse]:
    del current_user
    try:
        rules = await service.list_rules(collection_id, org.id)
    except SourceDiscoveryError as exc:
        raise _http_error(exc) from exc
    return [
        MembershipRuleResponse.from_domain(rule, version) for rule, version in rules
    ]


@collections_router.post(
    "/{collection_id}/sc-automation-partitions",
    response_model=ScAutomationPartitionResponse,
)
async def create_sc_automation_partition(
    collection_id: str,
    payload: CreateScAutomationPartitionRequest,
    service: SourceDiscoveryServiceDep,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
) -> ScAutomationPartitionResponse:
    try:
        _, _, partition = await service.create_sc_partition(
            collection_id=collection_id,
            org_id=org.id,
            actor_id=current_user.id,
            name=payload.name,
            connector_id=payload.connector_id,
            import_profile_version_id=payload.import_profile_version_id,
            layer_id=payload.layer_id,
            device=payload.device,
        )
    except SourceDiscoveryError as exc:
        raise _http_error(exc) from exc
    return ScAutomationPartitionResponse.from_domain(partition)


@collections_router.get(
    "/{collection_id}/sc-automation-partitions",
    response_model=list[ScAutomationPartitionResponse],
)
async def list_sc_automation_partitions(
    collection_id: str,
    service: SourceDiscoveryServiceDep,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
) -> list[ScAutomationPartitionResponse]:
    del current_user
    try:
        partitions = await service.list_sc_partitions(collection_id, org.id)
    except SourceDiscoveryError as exc:
        raise _http_error(exc) from exc
    return [ScAutomationPartitionResponse.from_domain(item) for item in partitions]


@collections_router.post(
    "/{collection_id}/membership-rules/{rule_id}/versions",
    response_model=MembershipRuleResponse,
)
async def create_membership_rule_version(
    collection_id: str,
    rule_id: str,
    payload: CreateMembershipRuleVersionRequest,
    service: SourceDiscoveryServiceDep,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
) -> MembershipRuleResponse:
    try:
        rule, version = await service.create_rule_version(
            collection_id=collection_id,
            rule_id=rule_id,
            org_id=org.id,
            actor_id=current_user.id,
            connector_id=payload.connector_id,
            import_profile_version_id=payload.import_profile_version_id,
            condition=payload.condition.to_domain(),
        )
    except SourceDiscoveryError as exc:
        raise _http_error(exc) from exc
    return MembershipRuleResponse.from_domain(rule, version)


@collections_router.post(
    "/{collection_id}/membership-rules/{rule_id}/runs",
    response_model=DiscoveryRunResponse,
)
async def run_membership_discovery(
    collection_id: str,
    rule_id: str,
    payload: RunLiveDiscoveryRequest,
    service: SourceDiscoveryServiceDep,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
) -> DiscoveryRunResponse:
    try:
        result = await service.run_live(
            collection_id=collection_id,
            rule_id=rule_id,
            org_id=org.id,
            actor_id=current_user.id,
            as_of_utc=payload.as_of_utc,
        )
    except SourceDiscoveryError as exc:
        raise _http_error(exc) from exc
    return DiscoveryRunResponse.from_domain(result)


@collections_router.post(
    "/{collection_id}/membership-rules/{rule_id}/backfill-preview",
    response_model=BackfillPreviewResponse,
)
async def preview_membership_backfill(
    collection_id: str,
    rule_id: str,
    payload: BackfillPreviewRequest,
    service: SourceDiscoveryServiceDep,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
) -> BackfillPreviewResponse:
    del current_user
    try:
        result = await service.preview_backfill(
            collection_id=collection_id,
            rule_id=rule_id,
            org_id=org.id,
            start_utc=payload.start_utc,
            end_utc=payload.end_utc,
            timezone_name=payload.timezone,
            representative_limit=payload.representative_limit,
        )
    except SourceDiscoveryError as exc:
        raise _http_error(exc) from exc
    return BackfillPreviewResponse.from_domain(result)


@collections_router.post(
    "/{collection_id}/membership-rules/{rule_id}/backfills",
    response_model=DiscoveryRunResponse,
)
async def run_membership_backfill(
    collection_id: str,
    rule_id: str,
    payload: BackfillRangeRequest,
    service: SourceDiscoveryServiceDep,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
) -> DiscoveryRunResponse:
    try:
        result = await service.run_backfill(
            collection_id=collection_id,
            rule_id=rule_id,
            org_id=org.id,
            actor_id=current_user.id,
            start_utc=payload.start_utc,
            end_utc=payload.end_utc,
            timezone_name=payload.timezone,
        )
    except SourceDiscoveryError as exc:
        raise _http_error(exc) from exc
    return DiscoveryRunResponse.from_domain(result)


@runs_router.get("/{run_id}", response_model=DiscoveryRunResponse)
async def get_discovery_run(
    run_id: str,
    service: SourceDiscoveryServiceDep,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
) -> DiscoveryRunResponse:
    del current_user
    try:
        result = await service.get_run(run_id, org.id)
    except SourceDiscoveryError as exc:
        raise _http_error(exc) from exc
    return DiscoveryRunResponse.from_domain(result)


@runs_router.post("/{run_id}/retry-failed", response_model=DiscoveryRunResponse)
async def retry_failed_discovery_items(
    run_id: str,
    service: SourceDiscoveryServiceDep,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
) -> DiscoveryRunResponse:
    try:
        result = await service.retry_failed(
            run_id=run_id,
            org_id=org.id,
            actor_id=current_user.id,
        )
    except SourceDiscoveryError as exc:
        raise _http_error(exc) from exc
    return DiscoveryRunResponse.from_domain(result)


@collections_router.post(
    "/{collection_id}/membership-suppressions",
    response_model=MembershipSuppressionResponse,
)
async def suppress_source_member(
    collection_id: str,
    payload: SuppressSourceMemberRequest,
    service: SourceDiscoveryServiceDep,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
) -> MembershipSuppressionResponse:
    try:
        suppression = await service.suppress_source_member(
            collection_id=collection_id,
            connector_id=payload.connector_id,
            source_record_key=payload.source_record_key,
            org_id=org.id,
            actor_id=current_user.id,
            expected_definition_version=payload.expected_definition_version,
            reason=payload.reason,
        )
    except SourceDiscoveryError as exc:
        raise _http_error(exc) from exc
    return MembershipSuppressionResponse.from_domain(suppression)


@collections_router.delete(
    "/{collection_id}/membership-suppressions/{suppression_id}",
    response_model=MembershipSuppressionResponse,
)
async def clear_membership_suppression(
    collection_id: str,
    suppression_id: str,
    service: SourceDiscoveryServiceDep,
    current_user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_org)],
) -> MembershipSuppressionResponse:
    try:
        suppression = await service.clear_suppression(
            collection_id=collection_id,
            suppression_id=suppression_id,
            org_id=org.id,
            actor_id=current_user.id,
        )
    except SourceDiscoveryError as exc:
        raise _http_error(exc) from exc
    return MembershipSuppressionResponse.from_domain(suppression)
