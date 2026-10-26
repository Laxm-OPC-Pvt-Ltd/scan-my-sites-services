"""Alert state machine: emails go out only on transitions (UP -> DOWN, DOWN -> UP).

    check result | alert_open | failures >= threshold | action
    -------------+------------+-----------------------+-----------------------
    DOWN         | False      | yes                   | send DOWN
    DOWN         | False      | no                    | nothing (not confirmed yet)
    DOWN         | True       | -                     | nothing (already alerted)
    UP           | True       | -                     | send RECOVERED
    UP           | False      | -                     | nothing

`alert_open` only flips once the email is actually delivered (see `acknowledge`), so a
failed send is retried on the next check instead of being silently lost.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .models import Alert, AlertKind, CheckResult, Status
from .state import EndpointState


@dataclass(frozen=True)
class Decision:
    state: EndpointState
    alert: Alert | None


def evaluate(prev: EndpointState, result: CheckResult, threshold: int) -> Decision:
    if result.status is Status.UP:
        state = replace(
            prev,
            status=Status.UP,
            consecutive_failures=0,
            # Keep the outage start until the recovery email is delivered.
            down_since=prev.down_since if prev.alert_open else None,
            last_checked=result.checked_at,
        )
        alert = None
        if prev.alert_open:
            alert = Alert(AlertKind.RECOVERED, result, prev.down_since, prev.consecutive_failures)
        return Decision(state, alert)

    failures = prev.consecutive_failures + 1
    state = replace(
        prev,
        status=Status.DOWN,
        consecutive_failures=failures,
        down_since=prev.down_since or result.checked_at,
        last_checked=result.checked_at,
    )
    alert = None
    if not prev.alert_open and failures >= threshold:
        alert = Alert(AlertKind.DOWN, result, state.down_since, failures)
    return Decision(state, alert)


def acknowledge(state: EndpointState, alert: Alert) -> EndpointState:
    """Record that `alert` was delivered."""
    if alert.kind is AlertKind.DOWN:
        return replace(state, alert_open=True)
    return replace(state, alert_open=False, down_since=None)
