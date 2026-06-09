from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.shared.api.schemas import UserResponse


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class MembershipResponse(BaseModel):
    org_id: str
    org_name: str
    org_slug: str
    role: str


class UserWithOrgsResponse(BaseModel):
    id: str
    email: str
    name: str
    is_superadmin: bool
    created_at: datetime
    organizations: list[MembershipResponse] = Field(default_factory=list)


class LoginResponse(BaseModel):
    access_token: str
    user: UserResponse


class CreateOrgRequest(BaseModel):
    name: str
    slug: str = ""


class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    created_at: datetime


class AddMemberRequest(BaseModel):
    user_id: str
    role: str = "member"


class MemberResponse(BaseModel):
    id: str
    user_id: str
    user_email: str
    user_name: str
    role: str
    created_at: datetime


class CreateTokenRequest(BaseModel):
    name: str


class TokenResponse(BaseModel):
    id: str
    name: str
    token_prefix: str
    created_at: datetime


class TokenCreatedResponse(BaseModel):
    id: str
    name: str
    token: str
    created_at: datetime


class OAuthProviderInfo(BaseModel):
    id: str
    display_name: str
    enabled: bool


class OAuthRegisterRequest(BaseModel):
    state_token: str
    name: str
