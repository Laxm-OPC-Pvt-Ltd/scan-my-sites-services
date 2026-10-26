"""Domain models shared across the service."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class Status(str, Enum):
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"


class AlertKind(str, Enum):
    DOWN = "down"
    RECOVERED = "recovered"


@dataclass(frozen=True)
class Endpoint:
    """A website or API to monitor. `name` must be unique; it keys the stored state."""

    name: str
    url: str
    type: str = "website"
    expected_status: int = 200
    notify: tuple[str, ...] = ()  # per-endpoint recipients; falls back to ALERT_RECIPIENTS

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Endpoint:
        try:
            name = str(data["name"]).strip()
            url = str(data["url"]).strip()
        except KeyError as exc:
            raise ValueError(f"Endpoint is missing required field {exc}") from None
        if not name or not url:
            raise ValueError("Endpoint 'name' and 'url' must be non-empty")
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"Endpoint {name!r} url must start with http:// or https://")

        notify = data.get("notify") or ()
        if isinstance(notify, str):
            notify = notify.split(",")
        return cls(
            name=name,
            url=url,
            type=str(data.get("type", "website")),
            expected_status=int(data.get("expected_status", 200)),
            notify=tuple(addr.strip() for addr in notify if addr and addr.strip()),
        )


@dataclass(frozen=True)
class CheckResult:
    endpoint: Endpoint
    status: Status
    checked_at: datetime
    http_status: int | None = None
    response_time: float | None = None  # seconds
    error: str | None = None


@dataclass(frozen=True)
class Alert:
    kind: AlertKind
    result: CheckResult
    down_since: datetime | None
    consecutive_failures: int
