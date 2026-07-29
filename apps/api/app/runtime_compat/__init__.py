"""Temporary in-repository runtime compatibility code.

Control-plane startup and registration modules must never import this package.
Only Prefect flow entrypoints may cross this boundary, and only after a job has
selected an explicit executable binding.
"""

from __future__ import annotations
