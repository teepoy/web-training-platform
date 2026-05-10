from __future__ import annotations

# Backward-compat shim: re-exports all public symbols from seed_maker
from seed_maker.utils import (
    api_request,
    wait_for_api_ready,
    DEFAULT_COMPOSE_FILE,
    DEFAULT_SEED_EMAIL,
    DEFAULT_SEED_PASSWORD,
    DEFAULT_SEED_NAME,
    DEFAULT_ORG_NAME,
    DEFAULT_ORG_SLUG,
)
from seed_maker.auth import (
    register_seed_user,
    login_seed_user,
    promote_superadmin,
    resolve_or_create_org,
)

__all__ = [
    "api_request",
    "wait_for_api_ready",
    "DEFAULT_COMPOSE_FILE",
    "DEFAULT_SEED_EMAIL",
    "DEFAULT_SEED_PASSWORD",
    "DEFAULT_SEED_NAME",
    "DEFAULT_ORG_NAME",
    "DEFAULT_ORG_SLUG",
    "register_seed_user",
    "login_seed_user",
    "promote_superadmin",
    "resolve_or_create_org",
]
