# Online Finetune Platform Docs

This documentation is organized for site navigation as well as repo browsing.

## Sections

- **Architecture**: system topology, runtime ownership, and major subsystem design notes
- **Guides**: operational walkthroughs, extension guides, and how-to documentation
- **Reference**: API and data format reference material
- **Protocols**: UI and agent interaction contracts
- **Observability**: metrics conventions and operational runbook
- **Archived**: extracted or completed features kept for historical context

## Start Here

- Read [Architecture Overview](architecture/overview.md) for the platform shape.
- Read [Schedule Execution](architecture/schedule-execution.md) for recurring-job targets,
  Prefect deployment identity, time semantics, and organization isolation.
- Read [Dataset Summary, Collection Stack, and Dynamic Collection](architecture/dataset-summary-and-collections.md)
  for the proposed multi-dataset classify, training, prediction, and refresh model.
- Read [Extension Guide](guides/extension-guide.md) for the extension model and widget system.
- Read [Production Docker Compose Deployment](guides/production-compose-deployment.md)
  for deployment, backup, release, and rollback procedures.
- Read [API Endpoints](reference/api-endpoints.md) for backend surface details.
