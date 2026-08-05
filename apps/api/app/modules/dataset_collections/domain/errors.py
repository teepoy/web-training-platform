from __future__ import annotations


class DatasetCollectionNotFoundError(LookupError):
    pass


class DatasetCollectionPermissionError(PermissionError):
    pass


class DatasetCollectionConflictError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(detail)


class DatasetCollectionValidationError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(detail)
