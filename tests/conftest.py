from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

import pytest

from scan_my_sites.models import Alert, CheckResult, Endpoint, Status

T0 = datetime(2026, 10, 26, 15, 30, tzinfo=timezone.utc)  # 9:00 PM IST


@pytest.fixture
def endpoint() -> Endpoint:
    return Endpoint(name="example.com", url="https://example.com")


def result(ep: Endpoint, status: Status, minutes: int = 0) -> CheckResult:
    return CheckResult(
        ep,
        status,
        T0 + timedelta(minutes=minutes),
        http_status=200 if status is Status.UP else 503,
        response_time=0.1,
        error=None if status is Status.UP else "Expected HTTP 200, got 503",
    )


class ScriptedChecker:
    """Returns pre-scripted statuses, one list entry per run."""

    def __init__(self, script: list[Status]) -> None:
        self.script = list(script)
        self.run = 0

    def check_all(self, endpoints: Sequence[Endpoint]) -> list[CheckResult]:
        status = self.script[self.run]
        out = [result(ep, status, minutes=5 * self.run) for ep in endpoints]
        self.run += 1
        return out


class RecordingNotifier:
    def __init__(self, fail_times: int = 0) -> None:
        self.sent: list[Alert] = []
        self.fail_times = fail_times

    def notify(self, alert: Alert) -> None:
        if self.fail_times:
            self.fail_times -= 1
            raise RuntimeError("smtp down")
        self.sent.append(alert)
