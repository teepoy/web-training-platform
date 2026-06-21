from __future__ import annotations

from typing import Any

import click


@click.group(name="deployments")
def deployments_group() -> None:
    """Manage Prefect deployments."""


@deployments_group.command(name="apply")
@click.option(
    "--pool",
    type=click.Choice(["default-cpu", "default-gpu", "all"]),
    default="all",
    help="Target worker pool(s) to register deployments for.",
)
def apply(pool: str) -> None:
    """Register Prefect deployments from flow modules."""
    # ── Lazy imports: torch / heavy modules must not load at CLI startup ──
    from app.modules.datasets.adapter.flows.drain_dataset import drain_dataset
    from app.modules.embedding.flows.embed import embed_flow
    from app.modules.prediction.flows.predict_job import predict_job_flow
    from app.modules.sensors.adapter.flows.dataset_size_sensor import (
        dataset_size_sensor,
    )
    from app.modules.sensors.adapter.flows.timer_sensor import timer_sensor
    from app.modules.training.flows.train_job import train_job_flow
    from app.modules.training.flows.train_predict import train_and_predict_flow

    flows: dict[str, dict[str, Any]] = {
        "default-gpu": {
            "training-train-job": train_job_flow,
            "training-train-and-predict": train_and_predict_flow,
            "prediction-predict-job": predict_job_flow,
            "embedding-embed": embed_flow,
        },
        "default-cpu": {
            "timer-sensor": timer_sensor,
            "dataset-size-sensor": dataset_size_sensor,
            "drain-dataset": drain_dataset,
        },
    }

    pools = list(flows.keys()) if pool == "all" else [pool]

    for pool_name in pools:
        pool_flows = flows[pool_name]
        for dep_name, flow_fn in pool_flows.items():
            click.echo(f"Registering {dep_name} → {pool_name}")
            flow_fn.to_deployment(name=dep_name, work_pool_name=pool_name)

    click.echo(
        "Registration complete. Run `prefect deploy` or start workers "
        "to pick up deployments."
    )
