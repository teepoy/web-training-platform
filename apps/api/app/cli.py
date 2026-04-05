from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select  # type: ignore[import-not-found]

from app.core.config import load_config
from app.db.models import UserORM
from app.db.session import create_engine, create_session_factory
from app.services.auth import hash_password


async def _create_superadmin(email: str, password: str, name: str) -> None:
    cfg = load_config()
    engine = create_engine(str(cfg.db.url))
    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        result = await session.execute(select(UserORM).where(UserORM.email == email))
        user = result.scalar_one_or_none()
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
            user.is_superadmin = True
            user.is_active = True
            if password:
                user.hashed_password = hash_password(password)
        await session.commit()
        print(f"Superadmin created/updated: id={user.id}, email={user.email}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Platform CLI")
    subparsers = parser.add_subparsers(dest="command")

    sa = subparsers.add_parser("create-superadmin", help="Create or promote a superadmin user")
    sa.add_argument("--email", required=True)
    sa.add_argument("--password", required=True)
    sa.add_argument("--name", required=True)

    args = parser.parse_args()
    if args.command == "create-superadmin":
        asyncio.run(_create_superadmin(args.email, args.password, args.name))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
