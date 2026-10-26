"""Alert delivery channels. A notifier raises on failure so the alert is retried next run."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import tzinfo
from typing import Protocol

from ..models import Alert
from . import templates
from .zeptomail import ZeptoMailClient, ZeptoMailError

__all__ = ["EmailNotifier", "LogNotifier", "Notifier", "ZeptoMailClient", "ZeptoMailError"]

log = logging.getLogger(__name__)


class Notifier(Protocol):
    def notify(self, alert: Alert) -> None: ...


class EmailNotifier:
    def __init__(self, client: ZeptoMailClient, default_recipients: Sequence[str], tz: tzinfo) -> None:
        self.client = client
        self.default_recipients = tuple(default_recipients)
        self.tz = tz

    def notify(self, alert: Alert) -> None:
        recipients = alert.result.endpoint.notify or self.default_recipients
        subject, html, text = templates.render(alert, self.tz)
        self.client.send(recipients, subject, html, text)


class LogNotifier:
    """Logs instead of sending; used by --dry-run."""

    def __init__(self, tz: tzinfo) -> None:
        self.tz = tz

    def notify(self, alert: Alert) -> None:
        subject, _, text = templates.render(alert, self.tz)
        log.warning("[dry-run] would email: %s\n%s", subject, text)
