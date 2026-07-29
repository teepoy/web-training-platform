# System Design Diagram

```mermaid
graph TB
    subgraph ControlPlane["Control plane — apps/api"]
        API["FastAPI routes and application services"]
        Catalog["Capability catalog<br/>view + materializer + trainer + predictor metadata"]
        Routing["Runtime routing descriptors"]
        Persistence["Repositories and metadata database"]
        API --> Catalog
        API --> Routing
        API --> Persistence
    end

    subgraph DataPlane["Data plane"]
        Materializer["Materializer<br/>dataset storage → versioned view manifest"]
        Runtime["Runtime service or compatibility Prefect worker"]
        Trainer["Lazily loaded trainer executable"]
        Predictor["Lazily loaded predictor executable"]
        Runtime --> Trainer
        Runtime --> Predictor
    end

    subgraph External["Infrastructure"]
        Prefect["Prefect server and work pools"]
        ObjectStorage["Object storage"]
        Database["PostgreSQL"]
    end

    API -->|"submit by catalog id"| Prefect
    Prefect -->|"dispatch explicit route"| Runtime
    Catalog -->|"exact ViewContractRef"| Materializer
    Materializer -->|"manifest contract + schema version"| Runtime
    Persistence --> Database
    Materializer --> ObjectStorage
    Trainer --> ObjectStorage
    Predictor --> ObjectStorage
```

The catalog contains import-safe metadata only. Executable trainer and predictor
modules are imported at worker execution time, never during API startup.
`apps/api/app/runtime_compat/` is a transitional worker boundary; new production
ML implementations belong in an out-of-process runtime service and consume
versioned data-plane manifests.

See [Architecture Overview](overview.md),
[Runtime Registration Contract](runtime-registration-contract.md), and
[View Contract Foundation](view-contract-foundation.md).
