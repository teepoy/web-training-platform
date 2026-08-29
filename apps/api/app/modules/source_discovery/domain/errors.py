from __future__ import annotations


class SourceDiscoveryError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(detail)


class SourceDiscoveryNotFoundError(SourceDiscoveryError):
    pass


class SourceDiscoveryConflictError(SourceDiscoveryError):
    pass


class SourceDiscoveryValidationError(SourceDiscoveryError):
    pass


class ActiveDiscoveryRunExistsError(RuntimeError):
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"membership rule already has active run {run_id}")
