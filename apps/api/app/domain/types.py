from __future__ import annotations

from enum import Enum


class TaskType(str, Enum):
    CLASSIFICATION = "classification"


class DatasetType(str, Enum):
    IMAGE_CLASSIFICATION = "image_classification"


class ModelFramework(str, Enum):
    PYTORCH = "pytorch"


class ResultType(str, Enum):
    CLASS_PREDICTION = "class_prediction"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OrgRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"
