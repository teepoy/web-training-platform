from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.app.services.auth_service import hash_password
from app.shared.api.schemas import Organization, User
from app.shared.db.registry import (
    OrgMembershipORM,
    OrganizationORM,
    UserORM,
)
from app.shared.db.session import AppDatabaseSessionFactory

_DEV_USER_ID = "00000000-0000-0000-0000-000000000002"
_DEV_ORG_ID = "00000000-0000-0000-0000-000000000001"
_DEV_ORG_SLUG = "dev-no-auth"
_DEV_USER_EMAIL = "seed@example.com"
_DEV_USER_NAME = "Seed Admin"
_DEV_USER_PASSWORD = "seed1234"


@dataclass(frozen=True, slots=True)
class DevAuthContext:
    user: User
    organization: Organization


def orm_to_user(orm: UserORM) -> User:
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


def orm_to_organization(orm: OrganizationORM) -> Organization:
    return Organization(
        id=orm.id,
        name=orm.name,
        slug=orm.slug,
        created_at=orm.created_at,
    )


async def _seed_dev_user_in_session(
    session: AsyncSession,
) -> tuple[UserORM, OrganizationORM]:
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

    user_result = await session.execute(
        select(UserORM).where(UserORM.email == _DEV_USER_EMAIL)
    )
    user_orm = user_result.scalar_one_or_none()
    if user_orm is not None:
        user_orm.name = _DEV_USER_NAME
        user_orm.is_superadmin = True
        user_orm.is_active = True
        actual_user_id = user_orm.id
    else:
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


async def _prepare_dev_auth_context_once(
    session_factory: AppDatabaseSessionFactory,
) -> DevAuthContext:
    async with session_factory() as session:
        try:
            user_orm, org_orm = await _seed_dev_user_in_session(session)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise

    return DevAuthContext(
        user=orm_to_user(user_orm),
        organization=orm_to_organization(org_orm),
    )


async def prepare_dev_auth_context(
    session_factory: AppDatabaseSessionFactory,
) -> DevAuthContext:
    """Persist the auth-disabled development identity during platform setup."""
    try:
        return await _prepare_dev_auth_context_once(session_factory)
    except IntegrityError:
        try:
            return await _prepare_dev_auth_context_once(session_factory)
        except IntegrityError:
            return await load_dev_auth_context(session_factory)


async def load_dev_auth_context(
    session_factory: AppDatabaseSessionFactory,
) -> DevAuthContext:
    """Load the prepared development identity without mutating the database."""
    async with session_factory() as session:
        org_result = await session.execute(
            select(OrganizationORM).where(OrganizationORM.id == _DEV_ORG_ID)
        )
        org_orm = org_result.scalar_one_or_none()
        user_result = await session.execute(
            select(UserORM).where(UserORM.email == _DEV_USER_EMAIL)
        )
        user_orm = user_result.scalar_one_or_none()
        if user_orm is None:
            user_result = await session.execute(
                select(UserORM).where(UserORM.id == _DEV_USER_ID)
            )
            user_orm = user_result.scalar_one_or_none()
        membership = None
        if user_orm is not None:
            membership_result = await session.execute(
                select(OrgMembershipORM).where(
                    OrgMembershipORM.user_id == user_orm.id,
                    OrgMembershipORM.org_id == _DEV_ORG_ID,
                )
            )
            membership = membership_result.scalar_one_or_none()

    if user_orm is None or org_orm is None or membership is None:
        raise RuntimeError(
            "Dev auth context is missing; run `make up-dev` to prepare the platform"
        )
    return DevAuthContext(
        user=orm_to_user(user_orm),
        organization=orm_to_organization(org_orm),
    )
