from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.report_service import write_run_report


def main() -> None:
    runs = sorted((ROOT / "generated" / "runs").glob("*"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not runs:
        raise SystemExit("No run directories found.")
    report = write_run_report(runs[0])
    print(json.dumps({"run_id": report["run_id"], "warnings": report["warnings"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
