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
