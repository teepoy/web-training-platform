from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter


def validate_cron_expression(value: str) -> str:
    if len(value.strip().split()) != 5 or not croniter.is_valid(value):
        raise ValueError(
            "cron must use exactly five fields: minute hour day month weekday"
        )
    return value


def validate_iana_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError("invalid IANA timezone") from exc
    return value
