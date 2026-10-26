"""Minimal client for the Zoho ZeptoMail send-email API.

Docs: https://www.zoho.com/zeptomail/help/api/email-sending.html
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

API_PATH = "/v1.1/email"
TOKEN_PREFIX = "Zoho-enczapikey"


class ZeptoMailError(RuntimeError):
    pass


def normalize_api_url(url: str) -> str:
    """Accepts 'api.zeptomail.in/', 'https://api.zeptomail.in' or a full endpoint URL."""
    url = url.strip().strip('"').rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    if not url.endswith(API_PATH):
        url = f"{url}{API_PATH}"
    return url


def normalize_token(token: str) -> str:
    token = token.strip().strip('"')
    return token if token.startswith(TOKEN_PREFIX) else f"{TOKEN_PREFIX} {token}"


class ZeptoMailClient:
    def __init__(
        self,
        api_url: str,
        token: str,
        from_email: str,
        from_name: str = "",
        timeout: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        self.api_url = normalize_api_url(api_url)
        self.from_email = from_email
        self.from_name = from_name
        self.timeout = timeout
        self._session = session or _retrying_session()
        self._session.headers.update(
            {
                "Authorization": normalize_token(token),
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def send(self, to: Sequence[str], subject: str, html: str, text: str | None = None) -> None:
        if not to:
            raise ZeptoMailError("No recipients given")
        payload: dict[str, Any] = {
            "from": {"address": self.from_email, "name": self.from_name},
            "to": [{"email_address": {"address": addr}} for addr in to],
            "subject": subject,
            "htmlbody": html,
        }
        if text:
            payload["textbody"] = text

        try:
            response = self._session.post(self.api_url, json=payload, timeout=self.timeout)
        except requests.exceptions.RequestException as exc:
            raise ZeptoMailError(f"ZeptoMail request failed: {exc}") from exc

        if not response.ok:
            raise ZeptoMailError(f"ZeptoMail returned HTTP {response.status_code}: {response.text[:500]}")
        log.info("ZeptoMail accepted email %r for %d recipient(s)", subject, len(to))


def _retrying_session() -> requests.Session:
    # Retry only rate limits and gateway errors, where the email was not accepted.
    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=(429, 502, 503, 504),
        allowed_methods=frozenset({"POST"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session
