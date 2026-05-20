from __future__ import annotations

from enum import Enum


class TaskType(str, Enum):
    CLASSIFICATION = "classification"
    VQA = "vqa"
    DETECTION = "detection"


class DatasetStorageMode(str, Enum):
    DB_FULL = "db_full"
    FILE_SHARD_SPARSE = "file_shard_sparse"


class DatasetType(str, Enum):
    IMAGE_CLASSIFICATION = "image_classification"
    IMAGE_VQA = "image_vqa"
    IMAGE_DETECTION = "image_detection"


class ModelFramework(str, Enum):
    PYTORCH = "pytorch"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OrgRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"
