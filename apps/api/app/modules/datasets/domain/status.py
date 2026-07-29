from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

MINIMUM_ACTIVE_CLASSES_FOR_TRAINING = 2


class DatasetTrainDisabledReason(str, Enum):
    INSUFFICIENT_ACTIVE_CLASSES = "insufficient_active_classes"


@dataclass(frozen=True)
class DatasetStatus:
    allow_train: bool
    train_disabled_reason: DatasetTrainDisabledReason | None
    minimum_active_class_count: int
    active_class_count: int
    annotated_samples: int
    total_samples: int
