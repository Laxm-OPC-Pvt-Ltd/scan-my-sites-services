"""HTTP health checks."""

from __future__ import annotations

import threading
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

from . import __version__
from .models import CheckResult, Endpoint, Status

USER_AGENT = f"ScanMySites/{__version__} (+uptime monitor)"


class HttpChecker:
    def __init__(self, timeout: float = 10.0, max_workers: int = 10) -> None:
        self.timeout = timeout
        self.max_workers = max_workers
        self._local = threading.local()  # one Session per worker thread

    def _session(self) -> requests.Session:
        session: requests.Session | None = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers["User-Agent"] = USER_AGENT
            self._local.session = session
        return session

    def check(self, endpoint: Endpoint) -> CheckResult:
        checked_at = datetime.now(timezone.utc)
        start = time.perf_counter()
        try:
            response = self._session().get(endpoint.url, timeout=self.timeout, allow_redirects=True)
            response.close()  # body is not needed
        except requests.exceptions.Timeout:
            return CheckResult(endpoint, Status.DOWN, checked_at, error="Request timed out")
        except requests.exceptions.SSLError as exc:
            return CheckResult(endpoint, Status.DOWN, checked_at, error=f"SSL error: {exc}")
        except requests.exceptions.ConnectionError:
            return CheckResult(endpoint, Status.DOWN, checked_at, error="Connection error")
        except requests.exceptions.RequestException as exc:
            return CheckResult(endpoint, Status.DOWN, checked_at, error=str(exc))

        elapsed = round(time.perf_counter() - start, 3)
        if response.status_code == endpoint.expected_status:
            return CheckResult(endpoint, Status.UP, checked_at, response.status_code, elapsed)
        return CheckResult(
            endpoint,
            Status.DOWN,
            checked_at,
            response.status_code,
            elapsed,
            error=f"Expected HTTP {endpoint.expected_status}, got {response.status_code}",
        )

    def check_all(self, endpoints: Sequence[Endpoint]) -> list[CheckResult]:
        if not endpoints:
            return []
        workers = min(self.max_workers, len(endpoints))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="check") as pool:
            return list(pool.map(self.check, endpoints))
