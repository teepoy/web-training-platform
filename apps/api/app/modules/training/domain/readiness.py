from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TrainingReadinessReport:
    dataset_id: str
    missing_image_policy: str
    annotated_samples: int
    readable_samples: int
    runtime_resolvable_samples: int
    unusable_samples: int
    skipped_samples: int
    label_counts: dict[str, int] = field(default_factory=dict)
    failure_reasons: tuple[str, ...] = ()

    @property
    def usable_samples(self) -> int:
        return self.readable_samples + self.runtime_resolvable_samples

    @property
    def active_labels(self) -> list[str]:
        return sorted(label for label, count in self.label_counts.items() if count > 0)

    @property
    def ready(self) -> bool:
        return not self.failure_reasons

    def as_http_detail(self) -> dict[str, object]:
        return {
            "code": "dataset_training_readiness_failed",
            "dataset_id": self.dataset_id,
            "missing_image_policy": self.missing_image_policy,
            "annotated_samples": self.annotated_samples,
            "readable_samples": self.readable_samples,
            "runtime_resolvable_samples": self.runtime_resolvable_samples,
            "usable_samples": self.usable_samples,
            "unusable_samples": self.unusable_samples,
            "skipped_samples": self.skipped_samples,
            "active_labels": self.active_labels,
            "label_counts": self.label_counts,
            "reasons": list(self.failure_reasons),
        }
