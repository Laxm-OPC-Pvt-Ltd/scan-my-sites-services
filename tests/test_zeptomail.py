from __future__ import annotations

import json
from zoneinfo import ZoneInfo

import pytest
import responses

from conftest import result

from scan_my_sites.models import Alert, AlertKind, Status
from scan_my_sites.notifiers import EmailNotifier, ZeptoMailClient, ZeptoMailError
from scan_my_sites.notifiers.templates import render
from scan_my_sites.notifiers.zeptomail import normalize_api_url, normalize_token

URL = "https://api.zeptomail.in/v1.1/email"


@pytest.mark.parametrize(
    "raw",
    ["api.zeptomail.in/", "api.zeptomail.in", "https://api.zeptomail.in", "https://api.zeptomail.in/v1.1/email"],
)
def test_normalize_api_url(raw):
    assert normalize_api_url(raw) == URL


def test_normalize_token_adds_prefix_once():
    assert normalize_token("abc") == "Zoho-enczapikey abc"
    assert normalize_token('"Zoho-enczapikey abc"') == "Zoho-enczapikey abc"


@responses.activate
def test_send_posts_expected_payload():
    responses.post(URL, status=201, json={"data": [{"code": "EM_104", "message": "Email request received"}]})
    client = ZeptoMailClient("api.zeptomail.in/", "Zoho-enczapikey tok", "noreply@x.com", "Monitor")
    client.send(["a@x.com", "b@x.com"], "Subj", "<p>hi</p>", "hi")

    req = responses.calls[0].request
    assert req.headers["Authorization"] == "Zoho-enczapikey tok"
    body = json.loads(req.body)
    assert body["from"] == {"address": "noreply@x.com", "name": "Monitor"}
    assert body["to"] == [{"email_address": {"address": "a@x.com"}}, {"email_address": {"address": "b@x.com"}}]
    assert body["subject"] == "Subj"
    assert body["textbody"] == "hi"


@responses.activate
def test_send_raises_on_api_error():
    responses.post(URL, status=401, json={"error": {"code": "TM_102", "message": "Invalid API Token"}})
    client = ZeptoMailClient("api.zeptomail.in", "bad", "noreply@x.com")
    with pytest.raises(ZeptoMailError, match="401"):
        client.send(["a@x.com"], "s", "h")


@responses.activate
def test_endpoint_recipients_override_defaults(endpoint):
    from dataclasses import replace

    responses.post(URL, status=201, json={})
    ep = replace(endpoint, notify=("owner@site.com",))
    r = result(ep, Status.DOWN)
    client = ZeptoMailClient("api.zeptomail.in", "t", "noreply@x.com")
    EmailNotifier(client, ["default@x.com"], ZoneInfo("UTC")).notify(Alert(AlertKind.DOWN, r, r.checked_at, 1))
    body = json.loads(responses.calls[0].request.body)
    assert body["to"] == [{"email_address": {"address": "owner@site.com"}}]


def test_templates_escape_html_and_use_display_tz(endpoint):
    from dataclasses import replace

    ep = replace(endpoint, name="<b>evil</b>")
    r = result(ep, Status.DOWN)
    subject, html, text = render(Alert(AlertKind.DOWN, r, r.checked_at, 1), ZoneInfo("Asia/Kolkata"))
    assert subject.startswith("[DOWN]")
    assert "<b>evil</b>" not in html and "&lt;b&gt;evil&lt;/b&gt;" in html
    assert "09:00 PM IST" in text


def test_recovery_template_shows_downtime(endpoint):
    down = result(endpoint, Status.DOWN, 0)
    up = result(endpoint, Status.UP, 75)
    subject, _, text = render(Alert(AlertKind.RECOVERED, up, down.checked_at, 15), ZoneInfo("UTC"))
    assert subject.startswith("[UP]")
    assert "Downtime: 1h 15m" in text
