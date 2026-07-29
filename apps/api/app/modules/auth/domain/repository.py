from __future__ import annotations

from typing import Protocol

from app.shared.db.registry import (
    OrgMembershipORM,
    OrganizationORM,
    PersonalAccessTokenORM,
    UserORM,
)


class AuthRepository(Protocol):
    async def get_user_by_email(self, email: str) -> UserORM | None: ...

    async def get_user_by_oauth(
        self,
        provider: str,
        provider_id: str,
    ) -> UserORM | None: ...

    async def get_user(self, user_id: str) -> UserORM | None: ...

    async def create_user(self, user: UserORM) -> UserORM: ...

    async def create_pat(
        self, pat: PersonalAccessTokenORM
    ) -> PersonalAccessTokenORM: ...

    async def list_personal_access_tokens(
        self,
        user_id: str,
    ) -> list[PersonalAccessTokenORM]: ...

    async def delete_personal_access_token(
        self,
        token_id: str,
        user_id: str,
    ) -> bool: ...

    async def create_organization(self, org: OrganizationORM) -> OrganizationORM: ...

    async def get_organization(self, org_id: str) -> OrganizationORM | None: ...

    async def get_organization_by_slug(self, slug: str) -> OrganizationORM | None: ...

    async def list_all_organizations(self) -> list[OrganizationORM]: ...

    async def add_org_member(
        self, membership: OrgMembershipORM
    ) -> OrgMembershipORM: ...

    async def get_org_members(
        self,
        org_id: str,
    ) -> list[tuple[OrgMembershipORM, UserORM]]: ...

    async def get_org_membership(
        self,
        org_id: str,
        user_id: str,
    ) -> OrgMembershipORM | None: ...

    async def remove_org_member(self, org_id: str, user_id: str) -> bool: ...

    async def get_user_orgs(
        self,
        user_id: str,
    ) -> list[tuple[OrgMembershipORM, OrganizationORM]]: ...
