"""One monitoring pass: check endpoints, update state, send transition alerts."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol

from .alerts import acknowledge, evaluate
from .models import CheckResult, Endpoint
from .notifiers import Notifier
from .state import EndpointState, StateStore

log = logging.getLogger(__name__)


class Checker(Protocol):
    def check_all(self, endpoints: Sequence[Endpoint]) -> list[CheckResult]: ...


class MonitorService:
    def __init__(
        self,
        endpoints: Sequence[Endpoint],
        checker: Checker,
        store: StateStore,
        notifier: Notifier,
        alert_threshold: int = 1,
    ) -> None:
        self.endpoints = list(endpoints)
        self.checker = checker
        self.store = store
        self.notifier = notifier
        self.alert_threshold = alert_threshold

    def run_once(self) -> list[CheckResult]:
        previous = self.store.load()
        results = self.checker.check_all(self.endpoints)
        # Endpoints removed from config drop out of state here.
        states: dict[str, EndpointState] = {}

        for result in results:
            name = result.endpoint.name
            decision = evaluate(previous.get(name, EndpointState()), result, self.alert_threshold)
            states[name] = decision.state
            log.info(
                "%-30s %-4s http=%s time=%ss%s",
                name,
                result.status.value.upper(),
                result.http_status,
                result.response_time,
                f" error={result.error}" if result.error else "",
            )
            if decision.alert is None:
                continue
            try:
                self.notifier.notify(decision.alert)
            except Exception:
                log.exception("Failed to send %s alert for %s; will retry next run", decision.alert.kind.value, name)
                continue
            states[name] = acknowledge(decision.state, decision.alert)
            # Persist immediately so a crash later in this run can't cause a duplicate email.
            self.store.save({**previous, **states})

        self.store.save(states)
        return results
