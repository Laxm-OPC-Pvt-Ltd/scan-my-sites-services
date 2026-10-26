# Scan My Sites Services

A Python service that monitors websites and APIs and sends email alerts through
[Zoho ZeptoMail](https://www.zoho.com/zeptomail/) when a site **goes down** and again when it **comes back up**.

## How alerting works

Each endpoint's state is persisted (`data/state.json`), so alerts are sent only on transitions, never repeatedly.
They also survive restarts.

| Time    | Check result | Email                                     |
|---------|--------------|-------------------------------------------|
| 9:00 PM | DOWN         | **DOWN alert sent**                       |
| 9:05 PM | DOWN         | none (already alerted)                    |
| 9:10 PM | DOWN         | none                                      |
| 9:15 PM | UP           | **RECOVERED alert sent** (downtime: 15m)  |
| 9:20 PM | UP           | none                                      |

- `ALERT_THRESHOLD=N` waits for N consecutive failures before alerting (use 2–3 to ignore one-off blips).
  A blip that never reached the threshold gets no recovery email.
- If ZeptoMail is unreachable, the alert is **not** marked as sent and is retried on the next check.
- Run only one monitor instance per state file.

## Project structure

```
├── src/scan_my_sites/
│   ├── cli.py            # `scan-my-sites check | run | test-email`
│   ├── config.py         # Settings from environment / .env
│   ├── models.py         # Endpoint, CheckResult, Alert, Status
│   ├── checker.py        # Concurrent HTTP checks
│   ├── alerts.py         # Transition state machine (dedup logic)
│   ├── state.py          # Persistent state stores
│   ├── service.py        # One monitoring pass
│   └── notifiers/        # ZeptoMail client + email templates
├── config/endpoints.json # Sites to monitor
├── deploy/anvil/         # anvil.works server module, build + endpoint sync scripts
├── tests/
├── .env.example          # All settings, documented
├── CLAUDE.md             # Context for Claude Code
└── pyproject.toml        # Packaging, pytest, ruff, mypy config
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -e ".[dev]"
copy .env.example .env          # then fill in ZEPTO_TOKEN and ALERT_RECIPIENTS
```

Edit `config/endpoints.json`:

```json
[
  { "name": "Main site", "url": "https://example.com" },
  { "name": "API", "url": "https://api.example.com/health", "type": "api",
    "expected_status": 200, "notify": ["api-team@example.com"], "enabled": true }
]
```

`notify` (optional) overrides `ALERT_RECIPIENTS` for that endpoint. `name` must be unique.

## Usage

```bash
scan-my-sites test-email --to you@example.com   # verify ZeptoMail credentials
scan-my-sites check --dry-run                   # one pass, log alerts instead of emailing
scan-my-sites check                             # one pass (exit code 1 if anything is down) — for cron/Task Scheduler
scan-my-sites run                               # loop every CHECK_INTERVAL_SECONDS
```

(`python -m scan_my_sites ...` works too.)

## Configuration

| Variable                  | Default                 | Description                                                 |
|---------------------------|-------------------------|-------------------------------------------------------------|
| `ZEPTO_URL`               | —                       | API host, e.g. `api.zeptomail.in` (`/v1.1/email` is added)  |
| `ZEPTO_TOKEN`             | —                       | Send Mail token (`Zoho-enczapikey ...`)                     |
| `ZEPTO_FROM_EMAIL`        | —                       | Verified sender address                                     |
| `ZEPTO_FROM_NAME`         | `Scan My Sites`         | Sender display name                                         |
| `ALERT_RECIPIENTS`        | —                       | Comma-separated default recipients                          |
| `ALERT_THRESHOLD`         | `1`                     | Consecutive failures before a DOWN alert                    |
| `DISPLAY_TIMEZONE`        | `UTC`                   | IANA timezone for timestamps in emails                      |
| `CHECK_INTERVAL_SECONDS`  | `300`                   | Interval for `run`                                          |
| `REQUEST_TIMEOUT_SECONDS` | `10`                    | Per-request timeout                                         |
| `MAX_WORKERS`             | `10`                    | Concurrent checks                                           |
| `ENDPOINTS_FILE`          | `config/endpoints.json` | Endpoints list                                              |
| `STATE_FILE`              | `data/state.json`       | Alert state (don't delete it, or the next outage alert may repeat) |
| `LOG_LEVEL`               | `INFO`                  | Logging level                                               |

Real environment variables take precedence over `.env`.

## Development

```bash
python -m pytest          # tests (HTTP is mocked with `responses`)
python -m ruff check .    # lint
python -m ruff format .   # format
python -m mypy            # strict type check
```

## Deploying on Anvil

The same monitoring logic runs inside an [anvil.works](https://anvil.works) app as a Scheduled Task.
`deploy/anvil/build.py` copies it into a git clone of your Anvil app, and `deploy/anvil/sync_endpoints.py`
loads your sites into the app's `endpoints` table. Requires the Hobby plan or higher (for Scheduled Tasks).

### 1. Create the app and clone it

1. In Anvil, create a new **Blank App**. In **Settings → Python version**, choose **Python 3.10** (Full Python, not Basic).
2. Open **Version History → Clone with Git** and clone it locally, e.g. `C:\Development\anvil\site-monitor`.

### 2. Add services and Data Tables

In the Anvil IDE, add the **Data Tables**, **Secrets** and **Scheduled Tasks** services. Then create these tables
(server access: *Full*; client access: *No access*):

| Table                | Columns                                                                                                   |
|----------------------|-----------------------------------------------------------------------------------------------------------|
| `endpoints`          | `name` text · `url` text · `type` text · `expected_status` number · `notify` text · `enabled` true/false |
| `endpoint_state`     | `name` text · `data` simple object                                                                        |
| `monitoring_history` | `endpoint_name` text · `url` text · `endpoint_type` text · `status` text · `http_status` number · `response_time` number · `error_message` text · `timestamp` date and time |

Column names must match exactly.

### 3. Add App Secrets

In **App Secrets**, create these with the same values as your `.env`:

- Required: `ZEPTO_URL`, `ZEPTO_TOKEN`, `ZEPTO_FROM_EMAIL`, `ALERT_RECIPIENTS`
- Optional: `ZEPTO_FROM_NAME`, `ALERT_THRESHOLD`, `DISPLAY_TIMEZONE`, `REQUEST_TIMEOUT_SECONDS`, `MAX_WORKERS`

### 4. Deploy the code

```bash
python deploy/anvil/build.py C:/Development/anvil/site-monitor
```

Then commit and push inside the clone:

```bash
git -C C:/Development/anvil/site-monitor add -A
```

```bash
git -C C:/Development/anvil/site-monitor commit -m "Deploy site monitor"
```

```bash
git -C C:/Development/anvil/site-monitor push
```

Re-run these three steps whenever you change the monitor code.

### 5. Add your sites

List every site/API in `config/endpoints.json` (same format as above), then push them to Anvil over Uplink:

1. In the Anvil IDE, open **Uplink → Enable the Anvil Server Uplink** and put the key in `.env` as `ANVIL_UPLINK_KEY`.
2. Install the client and sync:

```bash
pip install -e ".[anvil]"
```

```bash
python deploy/anvil/sync_endpoints.py --dry-run
```

```bash
python deploy/anvil/sync_endpoints.py --prune
```

`--prune` deletes table rows that are no longer in the file. You can also add/edit rows directly in the
`endpoints` table in the Anvil IDE; set `enabled` to false to pause a site without losing its history.

### 6. Schedule and publish

1. **Scheduled Tasks → Add task**: `check_all_endpoints`, every 5 minutes.
2. Optional: `prune_history`, every day (keeps 30 days of `monitoring_history`).
3. **Publish** the app — Scheduled Tasks only run in the published version.

To test without waiting for the schedule, call `anvil.server.call("run_manual_check")` from an Uplink
script (connected with `ANVIL_UPLINK_KEY`), then check **App Logs** and the `endpoint_state` table.

### Notes

- Alert state lives in `endpoint_state`; deleting a row there can cause one repeat alert for that site.
- `get_current_status` and `get_endpoint_history` are client-callable (for a future status page);
  `run_manual_check` only accepts trusted callers (server code / Uplink).
- Anvil Scheduled Tasks run in UTC; email timestamps use `DISPLAY_TIMEZONE`.

## License

MIT
