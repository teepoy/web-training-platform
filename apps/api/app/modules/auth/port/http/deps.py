from __future__ import annotations
# pyright: reportMissingImports=false, reportMissingModuleSource=false

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from jose import JWTError
from sqlalchemy import select

from app.core.config import load_config
from app.modules.auth.app.services.auth_service import (
    decode_access_token,
    verify_personal_access_token,
)
from app.modules.auth.app.services.dev_auth_context import (
    DevAuthContext,
    orm_to_organization,
    orm_to_user,
)
from app.modules.auth.domain.repository import AuthRepository
from app.shared.api.schemas import Organization, User
from app.shared.db.registry import (
    OrgMembershipORM,
    OrganizationORM,
    PersonalAccessTokenORM,
    UserORM,
)
from app.shared.db.session import AppDatabaseSessionFactory
from app.shared.injection import resolve


logger = logging.getLogger(__name__)


def get_repository(request: Request) -> AuthRepository:
    return resolve(request, AuthRepository)


def get_session_factory(
    request: Request,
) -> AppDatabaseSessionFactory:
    return resolve(request, AppDatabaseSessionFactory)


SessionFactory = Annotated[AppDatabaseSessionFactory, Depends(get_session_factory)]


def _get_session_factory(request: Request | None = None):
    if request is not None:
        return resolve(request, AppDatabaseSessionFactory)
    from app.core.config import load_config
    from app.shared.db.session import create_engine, create_session_factory

    cfg = load_config()
    return AppDatabaseSessionFactory(
        create_session_factory(
            create_engine(db_url=str(cfg.db.url), echo=bool(cfg.db.echo))
        )
    )


def _auth_enabled() -> bool:
    cfg = load_config()
    return bool(getattr(cfg.auth, "enabled", True))


async def _maybe_await(value: object) -> object:
    if hasattr(value, "__await__"):
        return await value  # type: ignore[misc]
    return value


async def _record_daily_jwt_login_seen(request: Request, user_id: str) -> None:
    """Best-effort once-per-UTC-day JWT user log for Loki analysis."""
    if not user_id:
        return
    try:
        app_context = getattr(request.app.state, "app_context", None)
        shared = getattr(app_context, "shared", None)
        publisher = getattr(shared, "redis_event_publisher", None)
        redis_client = getattr(publisher, "_redis", None)
        if redis_client is None:
            return

        now = datetime.now(UTC)
        login_date = now.date().isoformat()
        key = f"finetune:auth:jwt-login-seen:{login_date}:{user_id}"
        created = await _maybe_await(
            redis_client.set(
                key,
                "1",
                ex=int(timedelta(days=2).total_seconds()),
                nx=True,
            )
        )
        if created:
            logger.info(
                "jwt user observed for login day",
                extra={
                    "event": "auth.user_login",
                    "user_id": user_id,
                    "auth_method": "jwt",
                    "login_date_utc": login_date,
                },
            )
    except Exception:
        logger.debug("failed to record daily JWT login event", exc_info=True)


def _initialized_dev_auth_context(request: Request) -> DevAuthContext:
    context = getattr(request.app.state, "dev_auth_context", None)
    if not isinstance(context, DevAuthContext):
        raise RuntimeError(
            "Dev auth context was not initialized during application startup"
        )
    return context


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
    await _record_daily_jwt_login_seen(request, user_orm.id)
    return orm_to_user(user_orm)


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
    return orm_to_user(user_orm)


async def get_current_user(request: Request) -> User:
    """Extract and validate Bearer JWT, ``?token=`` query param, or ``ftp_`` PAT.

    Priority:
    1. ``Authorization: Bearer <token>`` header
    2. ``?token=`` query parameter (for EventSource / SSE clients)
    3. If the resolved token starts with ``ftp_``, treat as a Personal Access Token.
    """
    if not _auth_enabled():
        return _initialized_dev_auth_context(request).user

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
        dev_org = _initialized_dev_auth_context(request).organization
        org_id_header = request.headers.get("X-Organization-ID")
        if not org_id_header or org_id_header == dev_org.id:
            return dev_org

        session_factory = _get_session_factory(request)
        async with session_factory() as session:
            org_result = await session.execute(
                select(OrganizationORM).where(OrganizationORM.id == org_id_header)
            )
            org_orm = org_result.scalar_one_or_none()
        if org_orm is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        return orm_to_organization(org_orm)

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
            return orm_to_organization(org_orm)

        if len(memberships) == 1:
            org_result = await session.execute(
                select(OrganizationORM).where(
                    OrganizationORM.id == memberships[0].org_id
                )
            )
            org_orm = org_result.scalar_one_or_none()
            if org_orm is None:
                raise HTTPException(status_code=404, detail="Organization not found")
        return orm_to_organization(org_orm)

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
