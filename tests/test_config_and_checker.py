from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests
import responses

from scan_my_sites.checker import HttpChecker
from scan_my_sites.config import ConfigError, Settings, load_endpoints
from scan_my_sites.models import Endpoint, Status

BASE_ENV = {
    "ZEPTO_URL": "api.zeptomail.in/",
    "ZEPTO_TOKEN": '"Zoho-enczapikey abc"',
    "ZEPTO_FROM_EMAIL": "noreply@x.com",
    "ALERT_RECIPIENTS": "a@x.com, b@x.com ,",
}


def test_settings_from_env_parses_and_defaults():
    s = Settings.from_env(BASE_ENV)
    assert s.alert_recipients == ("a@x.com", "b@x.com")
    assert s.zepto_token == "Zoho-enczapikey abc"
    assert s.alert_threshold == 1
    assert s.check_interval_seconds == 300


def test_settings_reports_missing_keys():
    with pytest.raises(ConfigError, match="ZEPTO_TOKEN, ALERT_RECIPIENTS"):
        Settings.from_env({"ZEPTO_URL": "x", "ZEPTO_FROM_EMAIL": "y"})


def test_settings_dry_run_needs_no_email_config():
    assert Settings.from_env({}, require_email=False).alert_recipients == ()


@pytest.mark.parametrize(("key", "value"), [("ALERT_THRESHOLD", "0"), ("CHECK_INTERVAL_SECONDS", "abc")])
def test_settings_rejects_bad_ints(key, value):
    with pytest.raises(ConfigError, match=key):
        Settings.from_env({**BASE_ENV, key: value})


def test_load_endpoints_skips_disabled_and_rejects_duplicates(tmp_path: Path):
    path = tmp_path / "e.json"
    path.write_text(
        json.dumps(
            [
                {"name": "a", "url": "https://a.com", "notify": "x@y.com, z@y.com"},
                {"name": "b", "url": "https://b.com", "enabled": False},
            ]
        )
    )
    (ep,) = load_endpoints(path)
    assert ep.notify == ("x@y.com", "z@y.com")

    path.write_text(json.dumps([{"name": "a", "url": "https://a.com"}, {"name": "a", "url": "https://b.com"}]))
    with pytest.raises(ConfigError, match="unique"):
        load_endpoints(path)


def test_load_endpoints_rejects_bad_url(tmp_path: Path):
    path = tmp_path / "e.json"
    path.write_text(json.dumps([{"name": "a", "url": "a.com"}]))
    with pytest.raises(ConfigError, match="http"):
        load_endpoints(path)


@responses.activate
def test_checker_statuses():
    responses.get("https://up.test/", status=200)
    responses.get("https://wrong.test/", status=500)
    responses.get("https://timeout.test/", body=requests.exceptions.ConnectTimeout())
    responses.get("https://refused.test/", body=requests.exceptions.ConnectionError())
    eps = [Endpoint(n, f"https://{n}.test/") for n in ("up", "wrong", "timeout", "refused")]

    up, wrong, timeout, refused = HttpChecker(timeout=1).check_all(eps)
    assert up.status is Status.UP and up.http_status == 200
    assert wrong.status is Status.DOWN and "got 500" in (wrong.error or "")
    assert timeout.status is Status.DOWN and timeout.error == "Request timed out"
    assert refused.status is Status.DOWN and refused.error == "Connection error"
