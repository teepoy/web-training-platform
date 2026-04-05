"""FastAPI auth dependencies."""
from __future__ import annotations

from fastapi import HTTPException, Request
from jose import JWTError
from sqlalchemy import select

from app.core.config import load_config
from app.db.models import OrgMembershipORM, OrganizationORM, PersonalAccessTokenORM, UserORM
from app.db.session import create_engine, create_session_factory
from app.domain.models import Organization, User
from app.services.auth import decode_access_token, verify_personal_access_token

# ---------------------------------------------------------------------------
# Lazy module-level engine + session factory (avoids per-request engine churn)
# ---------------------------------------------------------------------------

_session_factory = None


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        cfg = load_config()
        engine = create_engine(str(cfg.db.url))
        _session_factory = create_session_factory(engine)
    return _session_factory


# ---------------------------------------------------------------------------
# ORM → domain model helpers
# ---------------------------------------------------------------------------


def _orm_to_user(orm: UserORM) -> User:
    return User(
        id=orm.id,
        email=orm.email,
        name=orm.name,
        is_superadmin=orm.is_superadmin,
        is_active=orm.is_active,
        created_at=orm.created_at,
    )


def _orm_to_org(orm: OrganizationORM) -> Organization:
    return Organization(
        id=orm.id,
        name=orm.name,
        slug=orm.slug,
        created_at=orm.created_at,
    )


# ---------------------------------------------------------------------------
# Internal token verifiers
# ---------------------------------------------------------------------------


async def _verify_jwt(token: str) -> User:
    try:
        payload = decode_access_token(token)
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    session_factory = _get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(UserORM).where(UserORM.id == user_id))
        user_orm = result.scalar_one_or_none()

    if user_orm is None or not user_orm.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return _orm_to_user(user_orm)


async def _verify_pat(token: str) -> User:
    token_prefix = token[:8]
    session_factory = _get_session_factory()

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


# ---------------------------------------------------------------------------
# Public dependencies
# ---------------------------------------------------------------------------


async def get_current_user(request: Request) -> User:
    """Extract and validate Bearer JWT, ``?token=`` query param, or ``ftp_`` PAT.

    Priority:
    1. ``Authorization: Bearer <token>`` header
    2. ``?token=`` query parameter (for EventSource / SSE clients)
    3. If the resolved token starts with ``ftp_``, treat as a Personal Access Token.
    """
    token: str | None = None

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    elif "token" in request.query_params:
        token = request.query_params["token"]

    if token is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if token.startswith("ftp_"):
        return await _verify_pat(token)

    return await _verify_jwt(token)


async def get_current_org(
    request: Request,
    current_user: User | None = None,
) -> Organization:
    """Resolve the request's organization context.

    Resolution order:

    1. ``X-Organization-ID`` request header — validate membership (superadmin bypasses).
    2. Auto-select when the user belongs to exactly one org.
    3. Return 400 (ambiguous) if the user has multiple orgs and no header.
    4. Return 400 (no org) if the user has zero orgs and no header.
    """
    if current_user is None:
        current_user = await get_current_user(request)

    session_factory = _get_session_factory()
    org_id_header = request.headers.get("X-Organization-ID")

    async with session_factory() as session:
        # Load all memberships for this user
        result = await session.execute(
            select(OrgMembershipORM).where(OrgMembershipORM.user_id == current_user.id)
        )
        memberships = result.scalars().all()

        if org_id_header:
            # Validate membership unless superadmin
            if not current_user.is_superadmin:
                member_org_ids = {m.org_id for m in memberships}
                if org_id_header not in member_org_ids:
                    raise HTTPException(
                        status_code=403,
                        detail="Not a member of the requested organization",
                    )

            org_result = await session.execute(
                select(OrganizationORM).where(OrganizationORM.id == org_id_header)
            )
            org_orm = org_result.scalar_one_or_none()
            if org_orm is None:
                raise HTTPException(status_code=404, detail="Organization not found")
            return _orm_to_org(org_orm)

        # No header — try auto-selection
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

        # Zero or multiple orgs without a header
        raise HTTPException(
            status_code=400,
            detail="X-Organization-ID header required",
        )


async def require_admin(
    request: Request,
    current_user: User | None = None,
    org: Organization | None = None,
) -> None:
    """Raise 403 if the current user is not an admin (or superadmin) of *org*."""
    if current_user is None:
        current_user = await get_current_user(request)

    if current_user.is_superadmin:
        return

    if org is None:
        org = await get_current_org(request, current_user)

    session_factory = _get_session_factory()
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
    """Raise 403 if the current user is not a superadmin."""
    if current_user is None and request is not None:
        current_user = await get_current_user(request)
    if not (current_user and current_user.is_superadmin):
        raise HTTPException(status_code=403, detail="Superadmin access required")
