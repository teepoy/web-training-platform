from __future__ import annotations

from collections import defaultdict

from app.domain.models import (
    Annotation,
    Dataset,
    PredictionEdit,
    PredictionResult,
    Sample,
    TrainingEvent,
    TrainingJob,
    TrainingPreset,
)


class InMemoryStore:
    def __init__(self) -> None:
        self.datasets: dict[str, Dataset] = {}
        self.samples: dict[str, Sample] = {}
        self.annotations: dict[str, Annotation] = {}
        self.presets: dict[str, TrainingPreset] = {}
        self.jobs: dict[str, TrainingJob] = {}
        self.predictions: dict[str, PredictionResult] = {}
        self.prediction_edits: dict[str, PredictionEdit] = {}
        self.job_events: dict[str, list[TrainingEvent]] = defaultdict(list)
        self.external_job_map: dict[str, str] = {}
        self.user_left_jobs: set[str] = set()


store = InMemoryStore()
