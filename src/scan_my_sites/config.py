"""Settings loaded from environment variables (see .env.example)."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import Endpoint


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    zepto_url: str
    zepto_token: str
    zepto_from_email: str
    zepto_from_name: str
    alert_recipients: tuple[str, ...]
    alert_threshold: int = 1
    check_interval_seconds: int = 300
    request_timeout: float = 10.0
    max_workers: int = 10
    endpoints_file: Path = Path("config/endpoints.json")
    state_file: Path = Path("data/state.json")
    display_timezone: ZoneInfo = ZoneInfo("UTC")
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None, *, require_email: bool = True) -> Settings:
        env = os.environ if env is None else env

        def get(key: str, default: str = "") -> str:
            return env.get(key, default).strip().strip('"').strip("'")

        missing = [
            key
            for key in ("ZEPTO_URL", "ZEPTO_TOKEN", "ZEPTO_FROM_EMAIL", "ALERT_RECIPIENTS")
            if require_email and not get(key)
        ]
        if missing:
            raise ConfigError(f"Missing required settings: {', '.join(missing)}")

        tz_name = get("DISPLAY_TIMEZONE", "UTC")
        try:
            tz = ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise ConfigError(f"Unknown DISPLAY_TIMEZONE {tz_name!r}") from None

        return cls(
            zepto_url=get("ZEPTO_URL"),
            zepto_token=get("ZEPTO_TOKEN"),
            zepto_from_email=get("ZEPTO_FROM_EMAIL"),
            zepto_from_name=get("ZEPTO_FROM_NAME", "Scan My Sites"),
            alert_recipients=tuple(a.strip() for a in get("ALERT_RECIPIENTS").split(",") if a.strip()),
            alert_threshold=_int(get, "ALERT_THRESHOLD", 1, minimum=1),
            check_interval_seconds=_int(get, "CHECK_INTERVAL_SECONDS", 300, minimum=10),
            request_timeout=float(get("REQUEST_TIMEOUT_SECONDS", "10")),
            max_workers=_int(get, "MAX_WORKERS", 10, minimum=1),
            endpoints_file=Path(get("ENDPOINTS_FILE", "config/endpoints.json")),
            state_file=Path(get("STATE_FILE", "data/state.json")),
            display_timezone=tz,
            log_level=get("LOG_LEVEL", "INFO").upper(),
        )


def load_endpoints(path: Path) -> list[Endpoint]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"Endpoints file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from None
    if not isinstance(raw, list):
        raise ConfigError(f"{path} must contain a JSON list of endpoints")
    return parse_endpoints(raw)


def parse_endpoints(raw: list[Mapping[str, object]]) -> list[Endpoint]:
    endpoints = []
    for i, item in enumerate(raw):
        if item.get("enabled", True) is False:
            continue
        try:
            endpoints.append(Endpoint.from_dict(item))
        except (ValueError, TypeError) as exc:
            raise ConfigError(f"Endpoint #{i + 1}: {exc}") from None

    names = [e.name for e in endpoints]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ConfigError(f"Endpoint names must be unique; duplicated: {', '.join(dupes)}")
    return endpoints


def _int(get: Callable[[str, str], str], key: str, default: int, *, minimum: int) -> int:
    raw = get(key, str(default))
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from None
    if value < minimum:
        raise ConfigError(f"{key} must be >= {minimum}, got {value}")
    return value
