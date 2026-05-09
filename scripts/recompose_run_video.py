from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.report_service import write_run_report  # noqa: E402
from services.video_service import compose_video  # noqa: E402


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _latest_run_dir() -> Path:
    runs_dir = ROOT / "generated" / "runs"
    candidates = [
        path
        for path in runs_dir.iterdir()
        if path.is_dir()
        and (path / "adjusted_storyboard.json").exists()
        and (path / "audio_plan.json").exists()
        and (path / "emotion.json").exists()
        and (path / "images").exists()
    ]
    if not candidates:
        raise SystemExit("No recomposable run directories found.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _image_paths(run_dir: Path, storyboard: list[dict]) -> list[Path]:
    paths = [run_dir / "images" / f"scene_{index:02d}.png" for index in range(1, len(storyboard) + 1)]
    missing = [path for path in paths if not path.exists()]
    if missing:
        missing_text = "\n".join(str(path) for path in missing)
        raise SystemExit(f"Missing existing image files; refusing to regenerate images:\n{missing_text}")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Recompose an existing run without regenerating images.")
    parser.add_argument("--run-dir", default=None, help="Existing generated/runs/<run_id> directory. Defaults to latest recomposable run.")
    parser.add_argument("--no-backup", action="store_true", help="Do not back up existing final.mp4 before overwriting.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir) if args.run_dir else _latest_run_dir()
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    if not run_dir.exists():
        raise SystemExit(f"Run directory does not exist: {run_dir}")

    storyboard = _read_json(run_dir / "adjusted_storyboard.json")
    emotion = _read_json(run_dir / "emotion.json")
    audio_plan = _read_json(run_dir / "audio_plan.json")
    images = _image_paths(run_dir, storyboard)

    final_video = run_dir / "final.mp4"
    if final_video.exists() and not args.no_backup:
        backup = run_dir / "final_before_recompose.mp4"
        if not backup.exists():
            shutil.copy2(final_video, backup)

    output = compose_video(storyboard, images, emotion, audio_plan, run_dir)
    report = write_run_report(run_dir)

    print(json.dumps(
        {
            "run_dir": str(run_dir),
            "output": str(output),
            "bgm_exists": (run_dir / "audio" / "bgm.mp3").exists(),
            "audio_status": report.get("audio_status", {}),
            "warnings": report.get("warnings", []),
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
