from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "anvil"))

import build  # noqa: E402
import sync_endpoints  # noqa: E402


def test_build_refuses_non_anvil_dir(tmp_path: Path):
    with pytest.raises(SystemExit, match="anvil.yaml"):
        build.build(tmp_path)


def test_build_copies_package_without_cli(tmp_path: Path):
    (tmp_path / "anvil.yaml").write_text("package_name: My_App\n")
    stale = tmp_path / "server_code" / "scan_my_sites" / "stale.py"
    stale.parent.mkdir(parents=True)
    stale.write_text("")

    build.build(tmp_path)

    pkg = tmp_path / "server_code" / "scan_my_sites"
    assert (tmp_path / "server_code" / "SiteMonitor.py").is_file()
    assert (pkg / "service.py").is_file() and (pkg / "notifiers" / "zeptomail.py").is_file()
    assert not (pkg / "cli.py").exists() and not (pkg / "__main__.py").exists()
    assert not stale.exists()
    # Anvil has no python-dotenv; nothing deployed may import it.
    assert not any("dotenv" in f.read_text(encoding="utf-8") for f in pkg.rglob("*.py"))


def test_sync_rows_and_plan():
    desired = sync_endpoints.to_rows(
        [
            {"name": "a", "url": "https://a.com", "notify": ["x@y.com", "z@y.com"]},
            {"name": "b", "url": "https://b.com", "expected_status": 204, "enabled": False},
        ]
    )
    assert desired["a"] == {
        "url": "https://a.com", "type": "website", "expected_status": 200, "notify": "x@y.com, z@y.com", "enabled": True
    }
    assert desired["b"]["enabled"] is False

    existing = {
        "a": dict(desired["a"]),
        "b": {**desired["b"], "expected_status": 200},
        "old": {"url": "https://old.com"},
    }
    assert sync_endpoints.plan(desired, existing, prune=False) == [("update", "b")]
    assert sync_endpoints.plan(desired, existing, prune=True) == [("update", "b"), ("delete", "old")]
    assert sync_endpoints.plan(desired, {}, prune=True) == [("add", "a"), ("add", "b")]


def test_sync_rejects_duplicates():
    with pytest.raises(ValueError, match="Duplicate"):
        sync_endpoints.to_rows([{"name": "a", "url": "https://a.com"}, {"name": "a", "url": "https://b.com"}])
