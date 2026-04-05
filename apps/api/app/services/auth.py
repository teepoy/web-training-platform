from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import cast

import bcrypt
from jose import JWTError, jwt  # noqa: F401 — re-exported for callers

from app.core.config import load_config
from app.db.models import PersonalAccessTokenORM

_cfg = load_config()
JWT_SECRET_KEY: str = cast(str, os.environ.get("JWT_SECRET_KEY") or str(_cfg.auth.jwt_secret_key))
JWT_ALGORITHM: str = _cfg.auth.jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES: int = _cfg.auth.access_token_expire_minutes


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta if expires_delta is not None else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


def create_personal_access_token(user_id: str, name: str) -> tuple[str, PersonalAccessTokenORM]:
    token = f"ftp_{secrets.token_hex(32)}"
    token_hash = bcrypt.hashpw(token.encode(), bcrypt.gensalt()).decode()
    token_obj = PersonalAccessTokenORM(
        user_id=user_id,
        name=name,
        token_hash=token_hash,
        token_prefix=token[:8],
    )
    return token, token_obj


def verify_personal_access_token(token: str, token_hash: str) -> bool:
    return bcrypt.checkpw(token.encode(), token_hash.encode())


class AuthService:
    def hash_password(self, plain: str) -> str:
        return hash_password(plain)

    def verify_password(self, plain: str, hashed: str) -> bool:
        return verify_password(plain, hashed)

    def create_access_token(self, data: dict, expires_delta: timedelta | None = None) -> str:
        return create_access_token(data, expires_delta)

    def decode_access_token(self, token: str) -> dict:
        return decode_access_token(token)
