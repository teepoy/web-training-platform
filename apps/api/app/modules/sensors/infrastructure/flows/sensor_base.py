from __future__ import annotations

import os

PLATFORM_API_URL = os.environ.get("PLATFORM_API_URL", "http://localhost:8000")
SENSOR_EVENTS_URL = f"{PLATFORM_API_URL}/api/v1/sensors/events"
