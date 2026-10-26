from __future__ import annotations

from pathlib import Path

from conftest import RecordingNotifier, ScriptedChecker

from scan_my_sites.models import AlertKind, Endpoint, Status
from scan_my_sites.service import MonitorService
from scan_my_sites.state import JsonStateStore, MemoryStateStore

UP, DOWN = Status.UP, Status.DOWN


def run(script: list[Status], endpoint: Endpoint, threshold: int = 1, notifier: RecordingNotifier | None = None):
    notifier = notifier or RecordingNotifier()
    service = MonitorService([endpoint], ScriptedChecker(script), MemoryStateStore(), notifier, threshold)
    for _ in script:
        service.run_once()
    return [a.kind for a in notifier.sent], service


def test_one_email_per_outage_and_one_on_recovery(endpoint):
    # 9:00 down (email), 9:05 down (no email), 9:10 down, 9:15 up (email), 9:20 up
    kinds, _ = run([DOWN, DOWN, DOWN, UP, UP], endpoint)
    assert kinds == [AlertKind.DOWN, AlertKind.RECOVERED]


def test_never_down_sends_nothing(endpoint):
    kinds, _ = run([UP, UP, UP], endpoint)
    assert kinds == []


def test_each_new_outage_alerts_again(endpoint):
    kinds, _ = run([DOWN, UP, DOWN, DOWN, UP], endpoint)
    assert kinds == [AlertKind.DOWN, AlertKind.RECOVERED, AlertKind.DOWN, AlertKind.RECOVERED]


def test_threshold_suppresses_blips(endpoint):
    kinds, _ = run([DOWN, UP, DOWN, DOWN, DOWN, UP], endpoint, threshold=2)
    # first blip (1 failure) is ignored and needs no recovery email
    assert kinds == [AlertKind.DOWN, AlertKind.RECOVERED]


def test_failed_send_is_retried_next_run_not_lost(endpoint):
    notifier = RecordingNotifier(fail_times=1)
    kinds, _ = run([DOWN, DOWN, DOWN], endpoint, notifier=notifier)
    assert kinds == [AlertKind.DOWN]


def test_recovery_email_reports_original_outage_start(endpoint):
    notifier = RecordingNotifier()
    run([DOWN, DOWN, UP], endpoint, notifier=notifier)
    down, recovered = notifier.sent
    assert recovered.down_since == down.down_since == down.result.checked_at
    assert recovered.consecutive_failures == 2


def test_state_survives_restart_no_duplicate(tmp_path: Path, endpoint):
    store_path = tmp_path / "state.json"
    notifier = RecordingNotifier()
    # Two separate service instances simulate a process restart between checks.
    for script in ([DOWN], [DOWN]):
        MonitorService([endpoint], ScriptedChecker(script), JsonStateStore(store_path), notifier).run_once()
    assert [a.kind for a in notifier.sent] == [AlertKind.DOWN]


def test_removed_endpoint_is_dropped_from_state(endpoint):
    store = MemoryStateStore()
    other = Endpoint("other", "https://other.example")
    MonitorService([endpoint, other], ScriptedChecker([UP]), store, RecordingNotifier()).run_once()
    MonitorService([endpoint], ScriptedChecker([UP]), store, RecordingNotifier()).run_once()
    assert set(store.states) == {"example.com"}
