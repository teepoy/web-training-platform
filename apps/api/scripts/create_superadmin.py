from __future__ import annotations

import asyncio
import os

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import load_config
from app.modules.auth.app.services.auth_service import hash_password
from app.shared.db.registry import UserORM
from app.shared.db.session import create_engine, create_session_factory


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


async def create_superadmin() -> None:
    email = _required_environment("BOOTSTRAP_SUPERADMIN_EMAIL")
    password = _required_environment("BOOTSTRAP_SUPERADMIN_PASSWORD")
    name = _required_environment("BOOTSTRAP_SUPERADMIN_NAME")
    config = load_config()
    engine = create_engine(str(config.db.url), echo=bool(config.db.echo))
    session_factory = create_session_factory(engine)
    try:
        for attempt in range(2):
            async with session_factory() as session:
                user = (
                    await session.execute(select(UserORM).where(UserORM.email == email))
                ).scalar_one_or_none()
                if user is None:
                    user = UserORM(
                        email=email,
                        name=name,
                        hashed_password=hash_password(password),
                        is_superadmin=True,
                        is_active=True,
                    )
                    session.add(user)
                else:
                    user.name = name
                    user.hashed_password = hash_password(password)
                    user.is_superadmin = True
                    user.is_active = True
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    if attempt == 0:
                        continue
                    raise
                await session.refresh(user)
                print(
                    f"Superadmin created or updated: id={user.id}, email={user.email}"
                )
                return
        raise RuntimeError("Unable to converge superadmin state")
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(create_superadmin())


if __name__ == "__main__":
    main()
