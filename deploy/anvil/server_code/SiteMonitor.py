"""
Anvil (anvil.works) server module that runs scan_my_sites as a Scheduled Task.

Deployed by deploy/anvil/build.py, which copies this file and the scan_my_sites package
into your Anvil app's server_code/. See README "Deploying on Anvil".

Data Tables:
  endpoints          name, url, type (text) · expected_status (number) · notify (text, comma-separated) · enabled (bool)
  endpoint_state     name (text) · data (simple object)
  monitoring_history endpoint_name, url, endpoint_type, status, error_message (text)
                     http_status, response_time (number) · timestamp (datetime)
"""

from datetime import datetime, timedelta, timezone

import anvil.secrets
import anvil.server
import anvil.tables.query as q
from anvil.tables import app_tables, order_by

try:  # new-style Anvil apps import sibling server code relatively
    from .scan_my_sites.checker import HttpChecker
    from .scan_my_sites.config import ConfigError, Settings, parse_endpoints
    from .scan_my_sites.notifiers import EmailNotifier, ZeptoMailClient
    from .scan_my_sites.service import MonitorService
    from .scan_my_sites.state import EndpointState
except ImportError:
    from scan_my_sites.checker import HttpChecker
    from scan_my_sites.config import ConfigError, Settings, parse_endpoints
    from scan_my_sites.notifiers import EmailNotifier, ZeptoMailClient
    from scan_my_sites.service import MonitorService
    from scan_my_sites.state import EndpointState

SECRET_KEYS = (
    "ZEPTO_URL", "ZEPTO_TOKEN", "ZEPTO_FROM_EMAIL", "ZEPTO_FROM_NAME", "ALERT_RECIPIENTS",
    "ALERT_THRESHOLD", "DISPLAY_TIMEZONE", "REQUEST_TIMEOUT_SECONDS", "MAX_WORKERS",
)
HISTORY_RETENTION_DAYS = 30


class DataTableStateStore:
    """State in the `endpoint_state` table, one row per endpoint."""

    def load(self):
        return {row["name"]: EndpointState.from_dict(row["data"]) for row in app_tables.endpoint_state.search()}

    def save(self, states):
        rows = {row["name"]: row for row in app_tables.endpoint_state.search()}
        for name, row in rows.items():
            if name not in states:
                row.delete()
        for name, state in states.items():
            data = state.to_dict()
            if name in rows:
                if rows[name]["data"] != data:
                    rows[name]["data"] = data
            else:
                app_tables.endpoint_state.add_row(name=name, data=data)


def _settings():
    env = {}
    for key in SECRET_KEYS:
        try:
            value = anvil.secrets.get_secret(key)
        except Exception:  # secret not defined -> Settings default applies
            continue
        if value:
            env[key] = value
    return Settings.from_env(env)


def _endpoints():
    return parse_endpoints([dict(row) for row in app_tables.endpoints.search()])


def _require_trusted():
    caller = anvil.server.context.remote_caller
    if caller is not None and not caller.is_trusted:
        raise anvil.server.PermissionDenied("This function can only be called from server code or Uplink")


@anvil.server.background_task
def check_all_endpoints():
    """Schedule this every 5 minutes (Scheduled Tasks service)."""
    try:
        settings = _settings()
        endpoints = _endpoints()
    except ConfigError as exc:
        print(f"Configuration error: {exc}")
        raise

    client = ZeptoMailClient(
        settings.zepto_url, settings.zepto_token, settings.zepto_from_email, settings.zepto_from_name
    )
    service = MonitorService(
        endpoints,
        HttpChecker(timeout=settings.request_timeout, max_workers=settings.max_workers),
        DataTableStateStore(),
        EmailNotifier(client, settings.alert_recipients, settings.display_timezone),
        alert_threshold=settings.alert_threshold,
    )
    results = service.run_once()
    for r in results:
        app_tables.monitoring_history.add_row(
            endpoint_name=r.endpoint.name,
            url=r.endpoint.url,
            endpoint_type=r.endpoint.type,
            status=r.status.value,
            http_status=r.http_status,
            response_time=r.response_time,
            error_message=r.error,
            timestamp=r.checked_at,
        )
    down = [r.endpoint.name for r in results if r.status.value == "down"]
    print(f"Checked {len(results)} endpoint(s); down: {', '.join(down) or 'none'}")


@anvil.server.background_task
def prune_history():
    """Optional: schedule daily to keep monitoring_history small."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=HISTORY_RETENTION_DAYS)
    for row in app_tables.monitoring_history.search(timestamp=q.less_than(cutoff)):
        row.delete()


@anvil.server.callable
def get_current_status():
    states = DataTableStateStore().load()
    out = []
    for ep in _endpoints():
        state = states.get(ep.name)
        out.append({
            "name": ep.name,
            "url": ep.url,
            "type": ep.type,
            "status": state.status.value if state else "never_checked",
            "last_checked": state.last_checked if state else None,
            "down_since": state.down_since if state else None,
        })
    return out


@anvil.server.callable
def get_endpoint_history(endpoint_name, limit=100):
    rows = app_tables.monitoring_history.search(order_by("timestamp", ascending=False), endpoint_name=endpoint_name)
    return [
        {
            "timestamp": h["timestamp"],
            "status": h["status"],
            "http_status": h["http_status"],
            "response_time": h["response_time"],
            "error": h["error_message"],
        }
        for h in rows[:limit]
    ]


@anvil.server.callable
def run_manual_check():
    _require_trusted()
    task = anvil.server.launch_background_task("check_all_endpoints")
    return {"success": True, "task_id": task.get_id()}
