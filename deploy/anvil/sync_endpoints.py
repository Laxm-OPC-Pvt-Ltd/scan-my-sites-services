"""Push config/endpoints.json into the Anvil app's `endpoints` Data Table over Uplink.

    pip install anvil-uplink
    python deploy/anvil/sync_endpoints.py            # add/update rows
    python deploy/anvil/sync_endpoints.py --prune    # also delete rows not in the file
    python deploy/anvil/sync_endpoints.py --dry-run  # show changes only

Requires ANVIL_UPLINK_KEY (Server Uplink key) in .env or the environment.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from scan_my_sites.models import Endpoint  # noqa: E402

COLUMNS = ("url", "type", "expected_status", "notify", "enabled")


def to_rows(raw: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Validate config entries and convert them to Data Table row values, keyed by name."""
    rows: dict[str, dict[str, Any]] = {}
    for item in raw:
        ep = Endpoint.from_dict(item)
        if ep.name in rows:
            raise ValueError(f"Duplicate endpoint name {ep.name!r}")
        rows[ep.name] = {
            "url": ep.url,
            "type": ep.type,
            "expected_status": ep.expected_status,
            "notify": ", ".join(ep.notify),
            "enabled": item.get("enabled", True) is not False,
        }
    return rows


def plan(desired: dict[str, dict[str, Any]], existing: dict[str, dict[str, Any]], prune: bool) -> list[tuple[str, str]]:
    """Return [(action, name)] where action is add, update or delete."""
    actions = []
    for name, values in desired.items():
        if name not in existing:
            actions.append(("add", name))
        elif any(existing[name].get(col) != values[col] for col in COLUMNS):
            actions.append(("update", name))
    if prune:
        actions += [("delete", name) for name in existing if name not in desired]
    return actions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", type=Path, default=ROOT / "config" / "endpoints.json")
    parser.add_argument("--prune", action="store_true", help="delete table rows missing from the file")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    key = os.environ.get("ANVIL_UPLINK_KEY", "").strip().strip('"')
    if not key:
        print("ANVIL_UPLINK_KEY is not set (Anvil IDE -> Uplink -> Enable server Uplink)", file=sys.stderr)
        return 2

    desired = to_rows(json.loads(args.file.read_text(encoding="utf-8")))

    import anvil.server
    from anvil.tables import app_tables

    anvil.server.connect(key, quiet=True)
    try:
        table_rows = {row["name"]: row for row in app_tables.endpoints.search()}
        existing = {name: {col: row[col] for col in COLUMNS} for name, row in table_rows.items()}
        actions = plan(desired, existing, args.prune)
        for action, name in actions:
            print(f"{action:6} {name}")
            if args.dry_run:
                continue
            if action == "add":
                app_tables.endpoints.add_row(name=name, **desired[name])
            elif action == "update":
                table_rows[name].update(**desired[name])
            else:
                table_rows[name].delete()
        print(f"{len(actions)} change(s){' (dry run)' if args.dry_run else ''}; {len(desired)} endpoint(s) in file")
    finally:
        anvil.server.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
