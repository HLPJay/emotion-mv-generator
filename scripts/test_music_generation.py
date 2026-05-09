from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.music_service import generate_music_audio  # noqa: E402


DEFAULT_PROMPT = (
    "cinematic emotional ambient score, wide atmospheric space, soft piano motif, "
    "warm evolving pads, slow tempo, no vocal, no lyrics, intimate and reflective"
)


def _latest_audio_plan() -> dict | None:
    runs_dir = ROOT / "generated" / "runs"
    if not runs_dir.exists():
        return None
    run_dirs = [path for path in runs_dir.iterdir() if path.is_dir() and (path / "audio_plan.json").exists()]
    if not run_dirs:
        return None
    latest = max(run_dirs, key=lambda path: path.stat().st_mtime)
    return json.loads((latest / "audio_plan.json").read_text(encoding="utf-8-sig"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Test MiniMax music generation only.")
    parser.add_argument("--model", default=None, help="Override music model, e.g. music-2.6 or music-2.6-free.")
    parser.add_argument("--prompt", default=None, help="Override music prompt.")
    parser.add_argument("--output-dir", default=str(ROOT / "generated" / "music_step_test"))
    parser.add_argument("--use-latest-plan", action="store_true", help="Use latest generated run audio_plan.json.")
    args = parser.parse_args()

    audio_plan = _latest_audio_plan() if args.use_latest_plan else None
    if audio_plan is None:
        audio_plan = {
            "music": {
                "model": args.model or "music-2.6",
                "prompt": args.prompt or DEFAULT_PROMPT,
            }
        }
    else:
        audio_plan.setdefault("music", {})
        if args.model:
            audio_plan["music"]["model"] = args.model
        if args.prompt:
            audio_plan["music"]["prompt"] = args.prompt

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("MUSIC_REQUEST")
    print(json.dumps(audio_plan.get("music", {}), ensure_ascii=False, indent=2))
    try:
        output = generate_music_audio(audio_plan, output_dir)
    except Exception as exc:
        print("MUSIC_ERROR")
        print(f"{exc.__class__.__name__}: {exc}")
        raise SystemExit(1)

    print("MUSIC_SUCCESS")
    print(output)


if __name__ == "__main__":
    main()
