"""Persistent per-endpoint state. This is what prevents duplicate alert emails across runs."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from .models import Status

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class EndpointState:
    status: Status = Status.UNKNOWN
    consecutive_failures: int = 0
    # True once a DOWN email was delivered and until the RECOVERED email is delivered.
    alert_open: bool = False
    down_since: datetime | None = None
    last_checked: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "consecutive_failures": self.consecutive_failures,
            "alert_open": self.alert_open,
            "down_since": _dt_to_str(self.down_since),
            "last_checked": _dt_to_str(self.last_checked),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EndpointState:
        return cls(
            status=Status(data.get("status", Status.UNKNOWN.value)),
            consecutive_failures=int(data.get("consecutive_failures", 0)),
            alert_open=bool(data.get("alert_open", False)),
            down_since=_str_to_dt(data.get("down_since")),
            last_checked=_str_to_dt(data.get("last_checked")),
        )


class StateStore(Protocol):
    def load(self) -> dict[str, EndpointState]: ...

    def save(self, states: dict[str, EndpointState]) -> None: ...


class MemoryStateStore:
    """In-process store, used for tests and --dry-run."""

    def __init__(self, states: dict[str, EndpointState] | None = None) -> None:
        self.states: dict[str, EndpointState] = dict(states or {})

    def load(self) -> dict[str, EndpointState]:
        return dict(self.states)

    def save(self, states: dict[str, EndpointState]) -> None:
        self.states = dict(states)


class JsonStateStore:
    """Stores state in a JSON file, written atomically so a crash never leaves it half-written."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, EndpointState]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return {name: EndpointState.from_dict(data) for name, data in raw.items()}
        except (OSError, ValueError, TypeError) as exc:
            # Starting fresh is safer than crashing the monitor; worst case is one repeat alert.
            log.error("Could not read state file %s (%s); starting with empty state", self.path, exc)
            return {}

    def save(self, states: dict[str, EndpointState]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({n: s.to_dict() for n, s in sorted(states.items())}, indent=2)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".state-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def _dt_to_str(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _str_to_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
