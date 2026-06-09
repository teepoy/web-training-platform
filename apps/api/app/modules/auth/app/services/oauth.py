from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from jose import jwt, JWTError

from app.core.config import load_config
from app.shared.db.registry import UserORM
from app.modules.auth.app.services.auth_service import (
    create_access_token,
    decode_access_token,
)

_OAUTH_STATE_EXPIRE_MINUTES = 5


def generate_oauth_state() -> str:
    return secrets.token_hex(16)


def build_authorize_url(provider_config: dict, state: str, redirect_uri: str) -> str:
    params = {
        "client_id": provider_config["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(provider_config.get("scopes", [])),
        "state": state,
    }
    return f"{provider_config['authorize_url']}?{urlencode(params)}"


async def exchange_code_for_token(
    provider_config: dict, code: str, redirect_uri: str
) -> str:
    payload = {
        "client_id": provider_config["client_id"],
        "client_secret": provider_config["client_secret"],
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    headers = {"Accept": "application/json"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            provider_config["token_url"],
            data=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        access_token: str = data["access_token"]
        return access_token


def _decode_jwt_access_token(access_token: str, mapping: dict | None = None) -> dict:
    """Decode a JWT access token without signature verification.

    Used when the OAuth provider does not publish a userinfo endpoint.
    """
    mapping = mapping or {}
    try:
        payload = jwt.decode(
            access_token,
            "",
            options={"verify_signature": False, "verify_exp": True},
        )
    except JWTError as e:
        raise ValueError(f"Failed to decode JWT access token: {e}")

    email_field = mapping.get("email", "email")
    name_field = mapping.get("name", "name")
    id_field = mapping.get("provider_id", "sub")

    email = payload.get(email_field, "")
    provider_id = str(payload.get(id_field, ""))
    name = payload.get(name_field, "")

    if not email or not provider_id:
        raise ValueError(
            f"JWT missing required claims: need '{email_field}' and '{id_field}'"
        )

    return {"email": email, "name": name, "provider_id": provider_id}


async def fetch_user_info(provider_config: dict, access_token: str) -> dict:
    if not provider_config.get("userinfo_url"):
        # No userinfo endpoint — decode access token as JWT
        if "." not in access_token:
            raise ValueError(
                "OAuth provider has no userinfo_url and access token is not a JWT"
            )
        return _decode_jwt_access_token(
            access_token, provider_config.get("user_mapping")
        )

    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(provider_config["userinfo_url"], headers=headers)
        resp.raise_for_status()
        data = resp.json()

    provider_id_key = "sub" if "sub" in data else "id"
    provider_id = str(data.get(provider_id_key, ""))

    email = data.get("email", "")
    name = data.get("name", data.get("login", ""))

    if not email and "user_emails_url" in provider_config:
        async with httpx.AsyncClient() as client:
            emails_resp = await client.get(
                provider_config["user_emails_url"], headers=headers
            )
            emails_resp.raise_for_status()
            emails = emails_resp.json()
            primary = next(
                (e for e in emails if e.get("primary")), emails[0] if emails else {}
            )
            email = primary.get("email", "")

    return {"email": email, "name": name, "provider_id": provider_id}


def get_oauth_provider_config(provider: str) -> dict | None:
    cfg = load_config()
    providers = cfg.oauth.providers
    return dict(providers.get(provider, {})) if provider in providers else None


def create_oauth_state_token(user_info: dict) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=_OAUTH_STATE_EXPIRE_MINUTES)
    payload = {
        "email": user_info["email"],
        "name": user_info["name"],
        "provider": user_info["provider"],
        "provider_id": user_info["provider_id"],
        "exp": expire,
    }
    return create_access_token(payload)


def decode_oauth_state_token(token: str) -> dict:
    return decode_access_token(token)


async def register_oauth_user(
    repo,
    email: str,
    name: str,
    oauth_provider: str,
    oauth_provider_id: str,
) -> UserORM:
    user_orm = UserORM(
        email=email,
        name=name,
        oauth_provider=oauth_provider,
        oauth_provider_id=oauth_provider_id,
        hashed_password=None,
    )
    return await repo.create_user(user_orm)
