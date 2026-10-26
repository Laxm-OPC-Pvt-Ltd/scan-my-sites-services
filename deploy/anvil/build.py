"""Copy the monitor's server code into a local git clone of your Anvil app.

    python deploy/anvil/build.py C:/path/to/your-anvil-app-clone

Then commit and push inside the clone; Anvil picks up the change immediately.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = ROOT / "src" / "scan_my_sites"
SERVER_CODE_SRC = Path(__file__).resolve().parent / "server_code"
# CLI-only modules depend on python-dotenv and are not needed inside Anvil.
EXCLUDE = shutil.ignore_patterns("cli.py", "__main__.py", "__pycache__", "*.pyc")


def build(target: Path) -> list[Path]:
    if not (target / "anvil.yaml").is_file():
        raise SystemExit(f"{target} is not an Anvil app clone (no anvil.yaml found)")

    server_code = target / "server_code"
    server_code.mkdir(exist_ok=True)
    written = []

    package_dst = server_code / "scan_my_sites"
    if package_dst.exists():
        shutil.rmtree(package_dst)  # owned entirely by this build
    shutil.copytree(PACKAGE_SRC, package_dst, ignore=EXCLUDE)
    written.append(package_dst)

    for module in SERVER_CODE_SRC.glob("*.py"):
        dst = server_code / module.name
        shutil.copy2(module, dst)
        written.append(dst)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", type=Path, help="path to your local clone of the Anvil app")
    args = parser.parse_args(argv)

    for path in build(args.target.resolve()):
        print(f"wrote {path}")
    print("\nNext: cd into the clone, then  git add -A && git commit -m 'Update site monitor' && git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
