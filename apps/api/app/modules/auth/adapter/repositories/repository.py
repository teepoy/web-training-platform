from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.db.registry import (
    OrgMembershipORM,
    OrganizationORM,
    PersonalAccessTokenORM,
    UserORM,
)


class AuthSqlRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def get_user_by_email(self, email: str) -> UserORM | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(UserORM).where(UserORM.email == email)
            )
            row = result.scalar_one_or_none()
            if row is not None:
                session.expunge(row)
            return row

    async def get_user_by_oauth(
        self, provider: str, provider_id: str
    ) -> UserORM | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(UserORM).where(
                    UserORM.oauth_provider == provider,
                    UserORM.oauth_provider_id == provider_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is not None:
                session.expunge(row)
            return row

    async def get_user(self, user_id: str) -> UserORM | None:
        async with self.session_factory() as session:
            row = await session.get(UserORM, user_id)
            if row is not None:
                session.expunge(row)
            return row

    async def create_user(self, user: UserORM) -> UserORM:
        async with self.session_factory() as session:
            session.add(user)
            await session.flush()
            await session.refresh(user)
            session.expunge(user)
            await session.commit()
            return user

    async def create_pat(self, pat: PersonalAccessTokenORM) -> PersonalAccessTokenORM:
        async with self.session_factory() as session:
            session.add(pat)
            await session.flush()
            await session.refresh(pat)
            session.expunge(pat)
            await session.commit()
            return pat

    async def list_personal_access_tokens(
        self, user_id: str
    ) -> list[PersonalAccessTokenORM]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(PersonalAccessTokenORM)
                .where(PersonalAccessTokenORM.user_id == user_id)
                .order_by(PersonalAccessTokenORM.created_at.desc())
            )
            rows = result.scalars().all()
            for row in rows:
                session.expunge(row)
            return list(rows)

    async def delete_personal_access_token(self, token_id: str, user_id: str) -> bool:
        async with self.session_factory() as session:
            row = await session.get(PersonalAccessTokenORM, token_id)
            if row is None or row.user_id != user_id:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def create_organization(self, org: OrganizationORM) -> OrganizationORM:
        async with self.session_factory() as session:
            session.add(org)
            await session.flush()
            await session.refresh(org)
            session.expunge(org)
            await session.commit()
            return org

    async def get_organization(self, org_id: str) -> OrganizationORM | None:
        async with self.session_factory() as session:
            row = await session.get(OrganizationORM, org_id)
            if row is not None:
                session.expunge(row)
            return row

    async def get_organization_by_slug(self, slug: str) -> OrganizationORM | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(OrganizationORM).where(OrganizationORM.slug == slug)
            )
            row = result.scalar_one_or_none()
            if row is not None:
                session.expunge(row)
            return row

    async def list_all_organizations(self) -> list[OrganizationORM]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(OrganizationORM).order_by(OrganizationORM.created_at.desc())
            )
            rows = result.scalars().all()
            for row in rows:
                session.expunge(row)
            return list(rows)

    async def add_org_member(self, membership: OrgMembershipORM) -> OrgMembershipORM:
        async with self.session_factory() as session:
            session.add(membership)
            await session.flush()
            await session.refresh(membership)
            session.expunge(membership)
            await session.commit()
            return membership

    async def get_org_members(
        self, org_id: str
    ) -> list[tuple[OrgMembershipORM, UserORM]]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(OrgMembershipORM, UserORM)
                .join(UserORM, OrgMembershipORM.user_id == UserORM.id)
                .where(OrgMembershipORM.org_id == org_id)
                .order_by(OrgMembershipORM.created_at.asc())
            )
            out: list[tuple[OrgMembershipORM, UserORM]] = []
            for membership, user in result.all():
                session.expunge(membership)
                session.expunge(user)
                out.append((membership, user))
            return out

    async def get_org_membership(
        self, org_id: str, user_id: str
    ) -> OrgMembershipORM | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(OrgMembershipORM).where(
                    OrgMembershipORM.org_id == org_id,
                    OrgMembershipORM.user_id == user_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is not None:
                session.expunge(row)
            return row

    async def remove_org_member(self, org_id: str, user_id: str) -> bool:
        async with self.session_factory() as session:
            result = await session.execute(
                select(OrgMembershipORM).where(
                    OrgMembershipORM.org_id == org_id,
                    OrgMembershipORM.user_id == user_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def get_user_orgs(
        self, user_id: str
    ) -> list[tuple[OrgMembershipORM, OrganizationORM]]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(OrgMembershipORM, OrganizationORM)
                .join(OrganizationORM, OrgMembershipORM.org_id == OrganizationORM.id)
                .where(OrgMembershipORM.user_id == user_id)
                .order_by(OrgMembershipORM.created_at.asc())
            )
            out: list[tuple[OrgMembershipORM, OrganizationORM]] = []
            for membership, org in result.all():
                session.expunge(membership)
                session.expunge(org)
                out.append((membership, org))
            return out
