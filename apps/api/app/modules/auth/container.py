from __future__ import annotations

from dataclasses import dataclass

from injector import Module, inject, provider, singleton

from app.modules.auth.adapter.repositories.repository import AuthSqlRepository
from app.modules.auth.domain.repository import AuthRepository
from app.shared.db.session import AppDatabaseSessionFactory
from app.shared.context import SharedInfra


@dataclass
class AuthContext:
    auth_repository: AuthRepository


def init_auth(shared: SharedInfra) -> AuthContext:
    return AuthContext(
        auth_repository=AuthSqlRepository(
            session_factory=shared.session_factory.sessionmaker
        )
    )


class AuthModule(Module):
    @inject
    @provider
    @singleton
    def provide_auth_context(
        self, session_factory: AppDatabaseSessionFactory
    ) -> AuthContext:
        return AuthContext(
            auth_repository=AuthSqlRepository(
                session_factory=session_factory.sessionmaker
            )
        )

    @provider
    @singleton
    def provide_auth_repository(self, context: AuthContext) -> AuthRepository:
        return context.auth_repository
