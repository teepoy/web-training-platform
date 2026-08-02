from __future__ import annotations


class SamplingRuleError(ValueError):
    """Base error for invalid rules and populations."""


class InvalidSamplingRuleError(SamplingRuleError):
    """Raised when a rule cannot produce an unambiguous allocation."""


class InsufficientPopulationError(SamplingRuleError):
    """Raised when the requested sample exceeds the eligible population."""


class MissingFieldError(SamplingRuleError):
    """Raised when a configured group field is absent from a row."""
