# Composition Contract

Status: draft
Date: 2026-06-18

This contract defines how API modules are composed during the refactor. It supersedes older guidance that relied on ad-hoc dataclass contexts as the primary composition mechanism.

## Goals

- Use the `injector` library as the API composition mechanism.
- Make cross-module dependencies explicit and interface-only.
- Keep module internals private while still allowing large refactors to move storage, materializer, trainer, and predictor boundaries safely.
- Prevent runtime services from importing API internals.

## Scope

This applies to `apps/api` composition and API module-to-module dependencies.

It does not require root `services/*` runtime services to use the same injector container. Runtime services may have their own local composition, but they must depend on shared contracts and runtime/data-plane clients, not API internal classes.

## Terms

- **Interface** means a `typing.Protocol` or abstract contract exported from a module `port/local` or `domain` package.
- **Concrete** means an implementation class such as a service, repository, adapter, storage implementation, or client wrapper.
- **Owning module** means the module that defines and constructs a concrete implementation.
- **Consumer module** means a different module that needs a capability from the owning module.

## Core Rules

1. Cross-module injection must use interfaces only.

   A consumer module may request `DatasetStorageFactoryPort`, `DatasetReaderPort`, `PredictionWriterPort`, etc. It must not request `DatasetService`, `SqlRepository`, `ScDatasetAgg`, `SparseDatasetStorage`, or another module's concrete service class.

2. Concrete implementations are bound only by their owning module.

   The storage module binds storage implementations. The datasets module binds dataset services. The SC module binds SC services. Other modules consume only exported interfaces.

3. Module public surfaces are explicit.

   Each module that exposes local capabilities must provide a small `port/local` package containing the Protocols and provider tokens it allows other modules to depend on. Internal `app/services`, `adapter`, and repository classes are not public.

4. Constructors depend on interfaces at module boundaries.

   A service constructor may use concrete collaborators from the same module when that is purely internal. When the collaborator is owned by another module, the constructor type must be the exported Protocol.

5. No sibling context access.

   Code inside module A must not read `ctx.module_b.some_service`, `request.app.state.app_context.module_b`, or an injector binding for module B's concrete service. It should request the module B interface through constructor injection.

6. Routes stay thin.

   FastAPI dependencies may resolve an interface from the injector container, but route handlers must not perform composition, choose implementations, or instantiate services.

7. Runtime services stay outside API internals.

   Trainer/predictor/image-parser services under root `services/*` must not import `apps/api/app/modules/*` concrete services, repositories, ORM models, FastAPI dependencies, or `AppContext`. They communicate through runtime contracts, data-plane clients, manifests, and object-store refs.

## Injector Shape

Each API entrypoint composition root owns a single `Injector` instance for its
FastAPI process. Specialized entrypoints should install only the bindings their
routes use; for example, the SC data-provider process uses
`sc_data_provider_composition.py` instead of constructing the full HTTP API graph.

Recommended structure:

```python
from injector import Binder, Injector, Module, provider, singleton

class StorageModule(Module):
    def configure(self, binder: Binder) -> None:
        binder.bind(DatasetStorageFactoryPort, to=DatasetStorageFactory, scope=singleton)

class DatasetsModule(Module):
    @provider
    @singleton
    def provide_dataset_service(
        self,
        storage_factory: DatasetStorageFactoryPort,
        repo: DatasetRepositoryPort,
    ) -> DatasetService:
        return DatasetService(
            storage_factory=storage_factory,
            repository=repo,
        )
```

The exact file layout can evolve, but the public rule should remain stable:

- `composition.py` builds the full HTTP API injector; specialized entrypoint
  roots such as `sc_data_provider_composition.py` build their minimal injector.
- `app/modules/<module>/container.py` or `composition.py` may define that module's binder.
- `app/modules/<module>/port/local/` defines cross-module Protocols.
- `port/http/deps.py` resolves route dependencies from the injector.

## Binding Rules

- Bind interfaces to concrete implementations, not concrete-to-concrete chains across modules.
- Prefer singleton scope for stateless services, repositories, storage factories, and clients that are safe to share.
- Do not bind request-specific state as singleton. Auth, org context, request IDs, and transaction/session scopes remain request-scoped or explicit parameters.
- SQLAlchemy sessions must remain explicit session scopes; do not inject a live session as a global singleton.
- Do not use `Any`, global service locators, or module-level mutable singletons to bypass the contract.

## Public Port Naming

Use names that describe capabilities, not implementations.

Good:

- `DatasetStorageFactoryPort`
- `DatasetReaderPort`
- `PredictionWriterPort`
- `ScImageSourcePort`
- `MaterializerPort`

Avoid:

- `DatasetServicePort` when the consumer only needs one narrow capability.
- `SqlRepositoryPort` outside the owning persistence module.
- `SparseDatasetStoragePort` outside storage internals.

## Testing

- Unit tests should override interface bindings in a test injector.
- Integration tests may build the production injector with test profile bindings.
- Do not monkeypatch sibling module concrete services when an interface binding override would express the test better.
- Contract tests should exist for public ports that multiple modules consume.

## Migration Order

This contract should be implemented before broad module extraction.

Reason: storage extraction, materializer extraction, and runtime service boundaries all depend on clean cross-module interfaces. If concrete service classes remain injected across modules during those moves, the refactor will preserve the old coupling under new filenames.

Recommended sequence:

1. Establish injector composition and public local ports.
2. Convert cross-module constructor dependencies to Protocol interfaces.
3. Add test binding overrides for major ports.
4. Extract storage module.
5. Extract materializer/runtime data-plane boundaries.
6. Move trainer/predictor execution to runtime services.

## Explicit Non-Goals

- This contract does not decide the final trainer/predictor service discovery mechanism.
- This contract does not require all intra-module services to become Protocols.
- This contract does not expose API module internals as a runtime SDK.
