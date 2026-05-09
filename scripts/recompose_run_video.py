from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.recompose_service import get_recomposable_runs, recompose_run_video  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Recompose an existing run without regenerating images or calling LLM.")
    parser.add_argument("--run-dir", default=None, help="Existing generated/runs/<run_id> directory. Defaults to latest recomposable run.")
    parser.add_argument("--no-backup", action="store_true", help="Do not back up existing final.mp4 before overwriting.")
    parser.add_argument("--strict-audio", action="store_true", help="Fail if BGM or narration audio is missing instead of regenerating.")
    parser.add_argument(
        "--mode",
        choices=["moviepy", "audio_only"],
        default="moviepy",
        help="Recompose mode: 'moviepy' for full recompose, 'audio_only' for FFmpeg fast audio replacement.",
    )
    args = parser.parse_args()

    if args.run_dir:
        run_dir = Path(args.run_dir)
        if not run_dir.is_absolute():
            run_dir = ROOT / run_dir
    else:
        runs = get_recomposable_runs()
        if not runs:
            raise SystemExit("No recomposable run directories found.")
        run_dir = Path(runs[0]["path"])

    if not run_dir.exists():
        raise SystemExit(f"Run directory does not exist: {run_dir}")

    result = recompose_run_video(
        run_dir,
        backup_existing=not args.no_backup,
        strict_audio=args.strict_audio,
        mode=args.mode,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
