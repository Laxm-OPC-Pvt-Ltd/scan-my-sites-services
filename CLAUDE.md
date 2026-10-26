# Scan My Sites Services

Uptime monitor for websites/APIs. Emails via Zoho ZeptoMail **only on transitions** (DOWN once, UP once).

## Commands
- Install: `pip install -e ".[dev]"`
- Test: `python -m pytest`
- Lint/format: `python -m ruff check . --fix && python -m ruff format .`
- Types: `python -m mypy`
- Run once without emailing: `python -m scan_my_sites check --dry-run`
- Run forever: `python -m scan_my_sites run` · verify email: `python -m scan_my_sites test-email --to you@x.com`

## Layout (src/scan_my_sites/)
- `alerts.py` — pure state machine deciding when to email. **Dedup logic lives here; change it with tests.**
- `service.py` — one pass: check → evaluate → notify → `acknowledge` → save state.
- `state.py` — `EndpointState` + stores (`JsonStateStore` at `STATE_FILE`, `MemoryStateStore`).
- `checker.py` — concurrent HTTP checks. `notifiers/` — ZeptoMail client + email templates.
- `config.py` — `Settings.from_env` (all config is env vars, see `.env.example`); endpoints in `config/endpoints.json`.
- `deploy/anvil/` — anvil.works deploy: `server_code/SiteMonitor.py` (Data Table state store + scheduled task), `build.py` (copies package minus `cli.py` into an Anvil clone), `sync_endpoints.py` (Uplink upsert of `config/endpoints.json`).
- Code under `src/` that Anvil runs must not import python-dotenv or other non-Anvil deps (only `cli.py` may).

## Rules
- `alert_open` flips only after a successful send, so failed emails retry; never mark sent before delivery.
- Endpoint `name` is the state key; keep names unique and stable.
- Datetimes are timezone-aware UTC internally; convert only for display (`DISPLAY_TIMEZONE`).
- New settings: add to `Settings`, `.env.example`, and README table together.
- Never read or print `.env` or tokens; use `.env.example` for key names.
- Tests use `responses` to mock HTTP — no real network calls in tests.
