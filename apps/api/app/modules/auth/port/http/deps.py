from __future__ import annotations
# pyright: reportMissingImports=false, reportMissingModuleSource=false

from fastapi import Depends, HTTPException, Request
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from typing import Annotated

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import load_config
from app.shared.api.schemas import Organization, User
from app.shared.db.sql_repository import SqlRepository
from app.modules.auth.app.services.auth_service import (
    decode_access_token,
    verify_personal_access_token,
)
from app.shared.db.registry import (
    OrgMembershipORM,
    OrganizationORM,
    PersonalAccessTokenORM,
    UserORM,
)


def get_repository(request: Request) -> SqlRepository:
    return SqlRepository(
        session_factory=request.app.state.app_context.shared.session_factory
    )


def get_session_factory(
    request: Request,
) -> async_sessionmaker[AsyncSession]:
    return request.app.state.app_context.shared.session_factory


SessionFactory = Annotated[
    async_sessionmaker[AsyncSession], Depends(get_session_factory)
]

_DEV_USER_ID = "00000000-0000-0000-0000-000000000002"
_DEV_ORG_ID = "00000000-0000-0000-0000-000000000001"
_DEV_ORG_SLUG = "dev-no-auth"
_DEV_USER_EMAIL = "seed@example.com"
_DEV_USER_NAME = "Seed Admin"
_DEV_USER_PASSWORD = "seed1234"


def _get_session_factory(request: Request | None = None):
    if request is not None:
        return request.app.state.app_context.shared.session_factory
    from app.core.config import load_config
    from app.shared.db.session import create_engine, create_session_factory

    cfg = load_config()
    return create_session_factory(
        create_engine(db_url=str(cfg.db.url), echo=bool(cfg.db.echo))
    )


def _auth_enabled() -> bool:
    cfg = load_config()
    return bool(getattr(cfg.auth, "enabled", True))


def _orm_to_user(orm: UserORM) -> User:
    return User(
        id=orm.id,
        email=orm.email,
        name=orm.name,
        is_superadmin=orm.is_superadmin,
        is_active=orm.is_active,
        created_at=orm.created_at,
        oauth_provider=orm.oauth_provider,
        oauth_provider_id=orm.oauth_provider_id,
    )


def _orm_to_org(orm: OrganizationORM) -> Organization:
    return Organization(
        id=orm.id,
        name=orm.name,
        slug=orm.slug,
        created_at=orm.created_at,
    )


async def _seed_dev_user_in_session(
    session: AsyncSession,
) -> tuple[UserORM, OrganizationORM]:
    """Create or update the dev user, org and membership in an active session.

    Caller is responsible for committing / rolling back.
    """
    from app.modules.auth.app.services.auth_service import hash_password

    org_result = await session.execute(
        select(OrganizationORM).where(OrganizationORM.id == _DEV_ORG_ID)
    )
    org_orm = org_result.scalar_one_or_none()
    if org_orm is None:
        org_orm = OrganizationORM(
            id=_DEV_ORG_ID,
            name="Dev No Auth",
            slug=_DEV_ORG_SLUG,
        )
        session.add(org_orm)

    # Look up by email first to avoid unique constraint violations
    # when another code path (e.g. seedmaker) has already created a
    # user with the seed email but a different ID.
    user_result = await session.execute(
        select(UserORM).where(UserORM.email == _DEV_USER_EMAIL)
    )
    user_orm = user_result.scalar_one_or_none()

    if user_orm is not None:
        # User already exists with seed email — ensure correct attributes
        user_orm.name = _DEV_USER_NAME
        user_orm.is_superadmin = True
        user_orm.is_active = True
        actual_user_id = user_orm.id
    else:
        # No user with seed email — try by dev ID
        user_result = await session.execute(
            select(UserORM).where(UserORM.id == _DEV_USER_ID)
        )
        user_orm = user_result.scalar_one_or_none()
        if user_orm is None:
            user_orm = UserORM(
                id=_DEV_USER_ID,
                email=_DEV_USER_EMAIL,
                name=_DEV_USER_NAME,
                hashed_password=hash_password(_DEV_USER_PASSWORD),
                is_superadmin=True,
                is_active=True,
            )
            session.add(user_orm)
        else:
            # User exists with dev ID but different email — only update
            # non-conflicting attributes (do NOT change email)
            user_orm.name = _DEV_USER_NAME
            user_orm.is_superadmin = True
            user_orm.is_active = True
        actual_user_id = user_orm.id

    membership_result = await session.execute(
        select(OrgMembershipORM).where(
            OrgMembershipORM.user_id == actual_user_id,
            OrgMembershipORM.org_id == _DEV_ORG_ID,
        )
    )
    membership = membership_result.scalar_one_or_none()
    if membership is None:
        session.add(
            OrgMembershipORM(
                user_id=actual_user_id,
                org_id=_DEV_ORG_ID,
                role="admin",
            )
        )
    else:
        membership.role = "admin"

    return user_orm, org_orm


async def _ensure_dev_auth_context(request: Request) -> tuple[User, Organization]:
    session_factory = _get_session_factory(request)
    async with session_factory() as session:
        try:
            user_orm, org_orm = await _seed_dev_user_in_session(session)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            # Race with another request — retry once with a fresh session
            return await _ensure_dev_auth_context_retry(request)

    return _orm_to_user(user_orm), _orm_to_org(org_orm)


async def _ensure_dev_auth_context_retry(request: Request) -> tuple[User, Organization]:
    session_factory = _get_session_factory(request)
    async with session_factory() as session:
        try:
            user_orm, org_orm = await _seed_dev_user_in_session(session)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            # Data was committed by a concurrent request — fall through to read
            return await _read_dev_auth_context(request)

    return _orm_to_user(user_orm), _orm_to_org(org_orm)


async def _read_dev_auth_context(request: Request) -> tuple[User, Organization]:
    session_factory = _get_session_factory(request)
    async with session_factory() as session:
        org_result = await session.execute(
            select(OrganizationORM).where(OrganizationORM.id == _DEV_ORG_ID)
        )
        org_orm = org_result.scalar_one()
        user_result = await session.execute(
            select(UserORM).where(UserORM.id == _DEV_USER_ID)
        )
        user_orm = user_result.scalar_one()
    return _orm_to_user(user_orm), _orm_to_org(org_orm)


async def seed_dev_auth_context(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Seed the dev user, org and membership at app startup.

    Call this during lifespan when ``auth_enabled`` is ``False`` so the
    dev user is available before the first request arrives.
    """
    async with session_factory() as session:
        try:
            await _seed_dev_user_in_session(session)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            # Race with another request — data is already present


async def _verify_jwt(token: str, request: Request) -> User:
    try:
        payload = decode_access_token(token)
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    session_factory = _get_session_factory(request)
    async with session_factory() as session:
        result = await session.execute(select(UserORM).where(UserORM.id == user_id))
        user_orm = result.scalar_one_or_none()

    if user_orm is None or not user_orm.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return _orm_to_user(user_orm)


async def _verify_pat(token: str, request: Request) -> User:
    token_prefix = token[:8]
    session_factory = _get_session_factory(request)

    async with session_factory() as session:
        result = await session.execute(
            select(PersonalAccessTokenORM).where(
                PersonalAccessTokenORM.token_prefix == token_prefix
            )
        )
        pat_candidates = result.scalars().all()

    matched_user_id: str | None = None
    for pat in pat_candidates:
        if verify_personal_access_token(token, pat.token_hash):
            matched_user_id = pat.user_id
            break

    if matched_user_id is None:
        raise HTTPException(status_code=401, detail="Invalid personal access token")

    async with session_factory() as session:
        result = await session.execute(
            select(UserORM).where(UserORM.id == matched_user_id)
        )
        user_orm = result.scalar_one_or_none()

    if user_orm is None or not user_orm.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return _orm_to_user(user_orm)


async def get_current_user(request: Request) -> User:
    """Extract and validate Bearer JWT, ``?token=`` query param, or ``ftp_`` PAT.

    Priority:
    1. ``Authorization: Bearer <token>`` header
    2. ``?token=`` query parameter (for EventSource / SSE clients)
    3. If the resolved token starts with ``ftp_``, treat as a Personal Access Token.
    """
    if not _auth_enabled():
        dev_user, _ = await _ensure_dev_auth_context(request)
        return dev_user

    token: str | None = None

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    elif "token" in request.query_params:
        token = request.query_params["token"]

    if token is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if token.startswith("ftp_"):
        return await _verify_pat(token, request)

    return await _verify_jwt(token, request)


async def get_current_org(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> Organization:
    """Resolve the request's organization context.

    Resolution order:

    1. ``X-Organization-ID`` request header — validate membership (superadmin bypasses).
    2. ``?org_id=`` query parameter for browser-native image/EventSource requests.
    3. Auto-select when the user belongs to exactly one org.
    4. Return 400 (ambiguous) if the user has multiple orgs and no context.
    5. Return 400 (no org) if the user has zero orgs and no context.
    """
    if not _auth_enabled():
        _, dev_org = await _ensure_dev_auth_context(request)
        org_id_header = request.headers.get("X-Organization-ID")
        if not org_id_header:
            return dev_org

        session_factory = _get_session_factory(request)
        async with session_factory() as session:
            org_result = await session.execute(
                select(OrganizationORM).where(OrganizationORM.id == org_id_header)
            )
            org_orm = org_result.scalar_one_or_none()
        if org_orm is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        return _orm_to_org(org_orm)

    session_factory = _get_session_factory(request)
    org_id = request.headers.get("X-Organization-ID") or request.query_params.get(
        "org_id"
    )

    async with session_factory() as session:
        result = await session.execute(
            select(OrgMembershipORM).where(OrgMembershipORM.user_id == current_user.id)
        )
        memberships = result.scalars().all()

        if org_id:
            if not current_user.is_superadmin:
                member_org_ids = {m.org_id for m in memberships}
                if org_id not in member_org_ids:
                    raise HTTPException(
                        status_code=403,
                        detail="Not a member of the requested organization",
                    )

            org_result = await session.execute(
                select(OrganizationORM).where(OrganizationORM.id == org_id)
            )
            org_orm = org_result.scalar_one_or_none()
            if org_orm is None:
                raise HTTPException(status_code=404, detail="Organization not found")
            return _orm_to_org(org_orm)

        if len(memberships) == 1:
            org_result = await session.execute(
                select(OrganizationORM).where(
                    OrganizationORM.id == memberships[0].org_id
                )
            )
            org_orm = org_result.scalar_one_or_none()
            if org_orm is None:
                raise HTTPException(status_code=404, detail="Organization not found")
            return _orm_to_org(org_orm)

        raise HTTPException(
            status_code=400,
            detail="X-Organization-ID header or org_id query parameter required",
        )


async def require_admin(
    request: Request,
    current_user: User | None = None,
    org: Organization | None = None,
) -> None:
    if current_user is None:
        current_user = await get_current_user(request)

    if current_user.is_superadmin:
        return

    if org is None:
        org = await get_current_org(request, current_user)

    session_factory = _get_session_factory(request)
    async with session_factory() as session:
        result = await session.execute(
            select(OrgMembershipORM).where(
                OrgMembershipORM.user_id == current_user.id,
                OrgMembershipORM.org_id == org.id,
            )
        )
        membership = result.scalar_one_or_none()

    if membership is None or membership.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


async def require_superadmin(
    request: Request | None = None,
    current_user: User | None = None,
) -> None:
    if current_user is None and request is not None:
        current_user = await get_current_user(request)
    if not (current_user and current_user.is_superadmin):
        raise HTTPException(status_code=403, detail="Superadmin access required")
