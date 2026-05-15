from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.deps import get_current_user, require_superadmin
from app.api.schemas import (
    AddMemberRequest,
    CreateOrgRequest,
    CreateTokenRequest,
    LoginRequest,
    LoginResponse,
    MemberResponse,
    MembershipResponse,
    OrgResponse,
    RegisterRequest,
    TokenCreatedResponse,
    TokenResponse,
    UserResponse,
    UserWithOrgsResponse,
)
from app.container import Container
from app.db.models import OrgMembershipORM, OrganizationORM, UserORM
from app.domain.models import User
from app.repositories.sql_repository import SqlRepository
from app.services.auth import (
    create_access_token,
    create_personal_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/v1", tags=["auth"])


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


@router.post("/auth/register", response_model=UserResponse, status_code=201)
@inject
async def register(
    payload: RegisterRequest,
    repo: Annotated[SqlRepository, Depends(Provide[Container.repository])],
) -> UserResponse:
    existing = await repo.get_user_by_email(payload.email)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already registered")
    hashed = hash_password(payload.password)
    user_orm = UserORM(
        email=payload.email,
        name=payload.name,
        hashed_password=hashed,
    )
    user_orm = await repo.create_user(user_orm)
    return UserResponse(
        id=user_orm.id,
        email=user_orm.email,
        name=user_orm.name,
        is_superadmin=user_orm.is_superadmin,
        created_at=user_orm.created_at,
    )


@router.post("/auth/login", response_model=LoginResponse)
@inject
async def login(
    payload: LoginRequest,
    repo: Annotated[SqlRepository, Depends(Provide[Container.repository])],
) -> LoginResponse:
    user_orm = await repo.get_user_by_email(payload.email)
    if user_orm is None or not user_orm.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(payload.password, user_orm.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": user_orm.id})
    user_resp = UserResponse(
        id=user_orm.id,
        email=user_orm.email,
        name=user_orm.name,
        is_superadmin=user_orm.is_superadmin,
        created_at=user_orm.created_at,
    )
    return LoginResponse(access_token=token, user=user_resp)


@router.get("/auth/me", response_model=UserWithOrgsResponse)
@inject
async def auth_me(
    repo: Annotated[SqlRepository, Depends(Provide[Container.repository])],
    current_user: User = Depends(get_current_user),
) -> UserWithOrgsResponse:
    memberships = await repo.get_user_orgs(current_user.id)
    orgs = [
        MembershipResponse(
            org_id=org.id,
            org_name=org.name,
            org_slug=org.slug,
            role=membership.role,
        )
        for membership, org in memberships
    ]
    return UserWithOrgsResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        is_superadmin=current_user.is_superadmin,
        created_at=current_user.created_at,
        organizations=orgs,
    )


# ---------------------------------------------------------------------------
# PAT endpoints
# ---------------------------------------------------------------------------


@router.post("/auth/tokens", response_model=TokenCreatedResponse, status_code=201)
@inject
async def create_token(
    payload: CreateTokenRequest,
    repo: Annotated[SqlRepository, Depends(Provide[Container.repository])],
    current_user: User = Depends(get_current_user),
) -> TokenCreatedResponse:
    plaintext, pat_orm = create_personal_access_token(current_user.id, payload.name)
    pat_orm = await repo.create_pat(pat_orm)
    return TokenCreatedResponse(
        id=pat_orm.id,
        name=pat_orm.name,
        token=plaintext,
        created_at=pat_orm.created_at,
    )


@router.get("/auth/tokens", response_model=list[TokenResponse])
@inject
async def list_tokens(
    repo: Annotated[SqlRepository, Depends(Provide[Container.repository])],
    current_user: User = Depends(get_current_user),
) -> list[TokenResponse]:
    pats = await repo.list_personal_access_tokens(current_user.id)
    return [
        TokenResponse(
            id=pat.id,
            name=pat.name,
            token_prefix=pat.token_prefix,
            created_at=pat.created_at,
        )
        for pat in pats
    ]


@router.delete("/auth/tokens/{token_id}", status_code=204)
@inject
async def delete_token(
    token_id: str,
    repo: Annotated[SqlRepository, Depends(Provide[Container.repository])],
    current_user: User = Depends(get_current_user),
) -> Response:
    deleted = await repo.delete_personal_access_token(token_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Token not found")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Org management endpoints
# ---------------------------------------------------------------------------


@router.post("/organizations", response_model=OrgResponse, status_code=201)
@inject
async def create_organization(
    payload: CreateOrgRequest,
    repo: Annotated[SqlRepository, Depends(Provide[Container.repository])],
    current_user: User = Depends(get_current_user),
) -> OrgResponse:
    await require_superadmin(current_user=current_user)
    slug = payload.slug if payload.slug else payload.name.lower().replace(" ", "-")
    existing = await repo.get_organization_by_slug(slug)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Organization slug already exists")
    org_orm = OrganizationORM(name=payload.name, slug=slug)
    org_orm = await repo.create_organization(org_orm)
    membership = OrgMembershipORM(
        user_id=current_user.id, org_id=org_orm.id, role="admin"
    )
    await repo.add_org_member(membership)
    return OrgResponse(
        id=org_orm.id,
        name=org_orm.name,
        slug=org_orm.slug,
        created_at=org_orm.created_at,
    )


@router.get("/organizations", response_model=list[OrgResponse])
@inject
async def list_organizations(
    repo: Annotated[SqlRepository, Depends(Provide[Container.repository])],
    current_user: User = Depends(get_current_user),
) -> list[OrgResponse]:
    if current_user.is_superadmin:
        orgs = await repo.list_all_organizations()
        return [
            OrgResponse(id=o.id, name=o.name, slug=o.slug, created_at=o.created_at)
            for o in orgs
        ]
    memberships = await repo.get_user_orgs(current_user.id)
    return [
        OrgResponse(id=org.id, name=org.name, slug=org.slug, created_at=org.created_at)
        for _, org in memberships
    ]


@router.post(
    "/organizations/{org_id}/members",
    response_model=MemberResponse,
    status_code=201,
)
@inject
async def add_org_member(
    org_id: str,
    payload: AddMemberRequest,
    repo: Annotated[SqlRepository, Depends(Provide[Container.repository])],
    current_user: User = Depends(get_current_user),
) -> MemberResponse:
    org = await repo.get_organization(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if not current_user.is_superadmin:
        caller_membership = await repo.get_org_membership(org_id, current_user.id)
        if caller_membership is None or caller_membership.role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
    target_user = await repo.get_user(payload.user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    existing_membership = await repo.get_org_membership(org_id, payload.user_id)
    if existing_membership is not None:
        raise HTTPException(status_code=409, detail="User is already a member")
    membership = OrgMembershipORM(
        user_id=payload.user_id, org_id=org_id, role=payload.role
    )
    membership = await repo.add_org_member(membership)
    return MemberResponse(
        id=membership.id,
        user_id=target_user.id,
        user_email=target_user.email,
        user_name=target_user.name,
        role=membership.role,
        created_at=membership.created_at,
    )


@router.get("/organizations/{org_id}/members", response_model=list[MemberResponse])
@inject
async def list_org_members(
    org_id: str,
    repo: Annotated[SqlRepository, Depends(Provide[Container.repository])],
    current_user: User = Depends(get_current_user),
) -> list[MemberResponse]:
    org = await repo.get_organization(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if not current_user.is_superadmin:
        caller_membership = await repo.get_org_membership(org_id, current_user.id)
        if caller_membership is None or caller_membership.role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
    members = await repo.get_org_members(org_id)
    return [
        MemberResponse(
            id=membership.id,
            user_id=user.id,
            user_email=user.email,
            user_name=user.name,
            role=membership.role,
            created_at=membership.created_at,
        )
        for membership, user in members
    ]


@router.delete("/organizations/{org_id}/members/{user_id}", status_code=204)
@inject
async def remove_org_member(
    org_id: str,
    user_id: str,
    repo: Annotated[SqlRepository, Depends(Provide[Container.repository])],
    current_user: User = Depends(get_current_user),
) -> Response:
    org = await repo.get_organization(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if not current_user.is_superadmin:
        caller_membership = await repo.get_org_membership(org_id, current_user.id)
        if caller_membership is None or caller_membership.role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
    removed = await repo.remove_org_member(org_id, user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Member not found")
    return Response(status_code=204)
