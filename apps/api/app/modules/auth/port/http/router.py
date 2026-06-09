from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.responses import RedirectResponse

from app.core.config import load_config
from app.shared.api.schemas import UserResponse
from app.shared.db.registry import OrgMembershipORM, OrganizationORM, UserORM
from app.shared.api.schemas import User
from app.modules.auth.port.http.deps import (
    get_current_user,
    require_superadmin,
)
from app.modules.auth.port.http.schemas import (
    AddMemberRequest,
    CreateOrgRequest,
    CreateTokenRequest,
    LoginRequest,
    LoginResponse,
    MemberResponse,
    MembershipResponse,
    OAuthProviderInfo,
    OAuthRegisterRequest,
    OrgResponse,
    RegisterRequest,
    TokenCreatedResponse,
    TokenResponse,
    UserWithOrgsResponse,
)
from app.modules.auth.app.services.auth_service import (
    create_access_token,
    create_personal_access_token,
    hash_password,
    verify_password,
)
from app.modules.auth.app.services.oauth import (
    build_authorize_url,
    create_oauth_state_token,
    decode_oauth_state_token,
    exchange_code_for_token,
    fetch_user_info,
    generate_oauth_state,
    get_oauth_provider_config,
    register_oauth_user,
)
from app.shared.db.sql_repository import SqlRepository
from app.modules.auth.port.http.deps import get_repository

router = APIRouter(prefix="/api/v1", tags=["auth"])

CurrentUser = Annotated[User, Depends(get_current_user)]
Repo = Annotated[SqlRepository, Depends(get_repository)]


@router.post("/auth/register", response_model=UserResponse, status_code=201)
async def register(
    payload: RegisterRequest,
    repo: Repo,
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
async def login(
    payload: LoginRequest,
    repo: Repo,
) -> LoginResponse:
    user_orm = await repo.get_user_by_email(payload.email)
    if user_orm is None or not user_orm.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user_orm.hashed_password is None or not verify_password(
        payload.password, user_orm.hashed_password
    ):
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
async def auth_me(
    repo: Repo,
    current_user: CurrentUser,
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


@router.post("/auth/tokens", response_model=TokenCreatedResponse, status_code=201)
async def create_token(
    payload: CreateTokenRequest,
    repo: Repo,
    current_user: CurrentUser,
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
async def list_tokens(
    repo: Repo,
    current_user: CurrentUser,
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
async def delete_token(
    token_id: str,
    repo: Repo,
    current_user: CurrentUser,
) -> Response:
    deleted = await repo.delete_personal_access_token(token_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Token not found")
    return Response(status_code=204)


@router.post(
    "/organizations",
    response_model=OrgResponse,
    status_code=201,
)
async def create_organization(
    payload: CreateOrgRequest,
    repo: Repo,
    current_user: CurrentUser,
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
async def list_organizations(
    repo: Repo,
    current_user: CurrentUser,
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
async def add_org_member(
    org_id: str,
    payload: AddMemberRequest,
    repo: Repo,
    current_user: CurrentUser,
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
async def list_org_members(
    org_id: str,
    repo: Repo,
    current_user: CurrentUser,
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
async def remove_org_member(
    org_id: str,
    user_id: str,
    repo: Repo,
    current_user: CurrentUser,
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


@router.get("/auth/oauth/providers", response_model=list[OAuthProviderInfo])
async def list_oauth_providers() -> list[OAuthProviderInfo]:
    cfg = load_config()
    if not bool(getattr(cfg.oauth, "enabled", False)):
        return []
    providers: list[OAuthProviderInfo] = []
    raw_providers: dict = cfg.oauth.providers
    for prov_id, prov_cfg in raw_providers.items():
        provider_enabled = bool(prov_cfg.get("enabled", False))
        client_id = str(prov_cfg.get("client_id", ""))
        if provider_enabled and client_id:
            providers.append(
                OAuthProviderInfo(
                    id=prov_id,
                    display_name=str(prov_cfg.get("display_name", prov_id)),
                    enabled=True,
                )
            )
    return providers


@router.get("/auth/oauth/{provider}")
async def oauth_authorize(provider: str, request: Request) -> RedirectResponse:
    prov_cfg = get_oauth_provider_config(provider)
    if not prov_cfg or not prov_cfg.get("enabled"):
        raise HTTPException(
            status_code=404, detail="OAuth provider not found or disabled"
        )
    if not prov_cfg.get("client_id"):
        raise HTTPException(status_code=400, detail="OAuth provider is misconfigured")

    state = f"{provider}:{generate_oauth_state()}"
    callback_url = f"{request.base_url}api/v1/auth/oauth/{provider}/callback"
    authorize_url = build_authorize_url(prov_cfg, state, callback_url)
    return RedirectResponse(url=authorize_url)


@router.get("/auth/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str,
    state: str,
    request: Request,
    repo: Repo,
) -> RedirectResponse:
    cfg = load_config()
    frontend_url = str(cfg.app.frontend_url)

    expected_prefix = f"{provider}:"
    if not state.startswith(expected_prefix):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    prov_cfg = get_oauth_provider_config(provider)
    if not prov_cfg:
        raise HTTPException(status_code=404, detail="OAuth provider not found")

    redirect_uri = f"{request.base_url}api/v1/auth/oauth/{provider}/callback"

    try:
        access_token = await exchange_code_for_token(prov_cfg, code, redirect_uri)
        user_info = await fetch_user_info(prov_cfg, access_token)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth exchange failed: {str(e)}")

    email = user_info.get("email", "")
    provider_id = user_info.get("provider_id", "")
    name = user_info.get("name", "")

    if not email or not provider_id:
        raise HTTPException(
            status_code=400, detail="OAuth provider did not return required user info"
        )

    existing_user = await repo.get_user_by_oauth(provider, provider_id)
    if existing_user is not None:
        login_token = create_access_token({"sub": existing_user.id})
        params = urlencode({"token": login_token})
        return RedirectResponse(url=f"{frontend_url}/auth/oauth/success?{params}")

    state_token = create_oauth_state_token(
        {
            "email": email,
            "name": name,
            "provider": provider,
            "provider_id": provider_id,
        }
    )
    params = urlencode({"state_token": state_token, "email": email, "name": name})
    return RedirectResponse(url=f"{frontend_url}/auth/oauth/register?{params}")


@router.post("/auth/oauth/register", response_model=LoginResponse)
async def oauth_register(
    payload: OAuthRegisterRequest,
    repo: Repo,
) -> LoginResponse:
    try:
        user_info = decode_oauth_state_token(payload.state_token)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid state token: {str(e)}")

    email = user_info.get("email", "")
    provider = user_info.get("provider", "")
    provider_id = user_info.get("provider_id", "")
    oauth_name = user_info.get("name", "")

    if not email or not provider or not provider_id:
        raise HTTPException(status_code=400, detail="Invalid state token payload")

    existing = await repo.get_user_by_oauth(provider, provider_id)
    if existing is not None:
        token = create_access_token({"sub": existing.id})
        user_resp = UserResponse(
            id=existing.id,
            email=existing.email,
            name=existing.name,
            is_superadmin=existing.is_superadmin,
            created_at=existing.created_at,
        )
        return LoginResponse(access_token=token, user=user_resp)

    email_user = await repo.get_user_by_email(email)
    if email_user is not None:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists. Please sign in with your password.",
        )

    user_orm = await register_oauth_user(
        repo,
        email=email,
        name=payload.name or oauth_name,
        oauth_provider=provider,
        oauth_provider_id=provider_id,
    )
    token = create_access_token({"sub": user_orm.id})
    user_resp = UserResponse(
        id=user_orm.id,
        email=user_orm.email,
        name=user_orm.name,
        is_superadmin=user_orm.is_superadmin,
        created_at=user_orm.created_at,
    )
    return LoginResponse(access_token=token, user=user_resp)
