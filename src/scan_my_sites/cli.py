"""Command-line entry point: `scan-my-sites {check,run,test-email}`."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from collections.abc import Sequence

from dotenv import load_dotenv

from .checker import HttpChecker
from .config import ConfigError, Settings, load_endpoints
from .models import Status
from .notifiers import EmailNotifier, LogNotifier, Notifier, ZeptoMailClient, ZeptoMailError
from .service import MonitorService
from .state import JsonStateStore, MemoryStateStore, StateStore

log = logging.getLogger("scan_my_sites")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scan-my-sites", description="Website/API uptime monitor")
    parser.add_argument("--env-file", default=".env", help="path to .env file (default: .env)")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (("check", "run one check pass and exit"), ("run", "check forever on an interval")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--dry-run", action="store_true", help="log alerts instead of emailing; state is not saved")

    p = sub.add_parser("test-email", help="send a test email via ZeptoMail")
    p.add_argument("--to", help="recipient (default: ALERT_RECIPIENTS)")

    args = parser.parse_args(argv)
    load_dotenv(args.env_file, override=False)

    try:
        dry_run = getattr(args, "dry_run", False)
        settings = Settings.from_env(require_email=not dry_run)
        logging.basicConfig(
            level=settings.log_level,
            format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        )
        if args.command == "test-email":
            return _test_email(settings, args.to)
        service = _build_service(settings, dry_run)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if args.command == "check":
        results = service.run_once()
        return 1 if any(r.status is Status.DOWN for r in results) else 0
    _run_forever(service, settings.check_interval_seconds)
    return 0


def _build_service(settings: Settings, dry_run: bool) -> MonitorService:
    endpoints = load_endpoints(settings.endpoints_file)
    file_store = JsonStateStore(settings.state_file)
    store: StateStore
    notifier: Notifier
    if dry_run:
        store = MemoryStateStore(file_store.load())
        notifier = LogNotifier(settings.display_timezone)
    else:
        store = file_store
        notifier = EmailNotifier(_zepto_client(settings), settings.alert_recipients, settings.display_timezone)
    log.info("Monitoring %d endpoint(s)%s", len(endpoints), " [dry-run]" if dry_run else "")
    return MonitorService(
        endpoints,
        HttpChecker(timeout=settings.request_timeout, max_workers=settings.max_workers),
        store,
        notifier,
        alert_threshold=settings.alert_threshold,
    )


def _zepto_client(settings: Settings) -> ZeptoMailClient:
    return ZeptoMailClient(
        settings.zepto_url, settings.zepto_token, settings.zepto_from_email, settings.zepto_from_name
    )


def _test_email(settings: Settings, to: str | None) -> int:
    recipients = [to] if to else list(settings.alert_recipients)
    try:
        _zepto_client(settings).send(
            recipients,
            "Scan My Sites: test email",
            "<p>ZeptoMail is configured correctly.</p>",
            "ZeptoMail is configured correctly.",
        )
    except ZeptoMailError as exc:
        log.error("%s", exc)
        return 1
    print(f"Test email sent to {', '.join(recipients)}")
    return 0


def _run_forever(service: MonitorService, interval: int) -> None:
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    log.info("Checking every %ds; press Ctrl+C to stop", interval)
    while not stop.is_set():
        started = time.monotonic()
        try:
            service.run_once()
        except Exception:
            log.exception("Check pass failed")
        stop.wait(max(0.0, interval - (time.monotonic() - started)))
    log.info("Stopped")


if __name__ == "__main__":
    sys.exit(main())
