from __future__ import annotations

import json

import typer

from ftsdk.client import FinetuneClient

app = typer.Typer(help="Finetune platform CLI")
jobs_app = typer.Typer(help="Training job operations")
datasets_app = typer.Typer(help="Dataset operations")
app.add_typer(jobs_app, name="jobs")
app.add_typer(datasets_app, name="datasets")


@jobs_app.command("ls")
def jobs_ls(base_url: str = "http://localhost:8000/api/v1") -> None:
    client = FinetuneClient(base_url=base_url)
    typer.echo(json.dumps(client.list_jobs(), indent=2))


@jobs_app.command("status")
def jobs_status(job_id: str, base_url: str = "http://localhost:8000/api/v1") -> None:
    client = FinetuneClient(base_url=base_url)
    typer.echo(json.dumps(client.get_job_status(job_id), indent=2))


@jobs_app.command("watch")
def jobs_watch(job_id: str, base_url: str = "http://localhost:8000/api/v1") -> None:
    import httpx

    with httpx.Client(timeout=None) as client:
        with client.stream("GET", f"{base_url}/training-jobs/{job_id}/events") as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    typer.echo(line[6:])


@datasets_app.command("ls")
def datasets_ls(base_url: str = "http://localhost:8000/api/v1") -> None:
    client = FinetuneClient(base_url=base_url)
    typer.echo(json.dumps(client.list_datasets(), indent=2))


if __name__ == "__main__":
    app()
