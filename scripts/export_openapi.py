"""Write each service's OpenAPI spec to contracts/openapi/<service>.json.

    uv run python scripts/export_openapi.py          # regenerate
    uv run python scripts/export_openapi.py --check  # CI: fail if a committed spec is out of date

Services that do not have a spec file yet (still the bare skeleton) are skipped; a service gets one
the first time it is exported with --write-new.
"""

import argparse
import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "contracts" / "openapi"

# Importing an app must not need real infrastructure or secrets.
os.environ.setdefault("EVENTS_ENABLED", "false")
os.environ.setdefault("OTP_DEV_MODE", "true")


def render(service: str) -> str:
    module = importlib.import_module(f"{service}_service.main")
    return json.dumps(module.app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    parser.add_argument("--write-new", action="store_true", help="also create specs that do not exist")
    args = parser.parse_args()

    services = sorted(p.name for p in (ROOT / "services").iterdir() if p.is_dir())
    stale = []
    for service in services:
        target = OUT / f"{service}.json"
        if not target.exists() and not args.write_new:
            continue
        text = render(service)
        if args.check:
            if not target.exists() or target.read_text(encoding="utf-8") != text:
                stale.append(service)
        else:
            target.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {target.relative_to(ROOT)}")
    if stale:
        print(f"OpenAPI spec out of date for: {', '.join(stale)}")
        print("Run: uv run python scripts/export_openapi.py   and commit the result.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
