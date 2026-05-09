from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


def load_storyboard_subtitles(run_dir: Path) -> list[dict[str, Any]]:
    """Load subtitles from adjusted_storyboard.json for editing.

    Returns a list of dicts with index (1-based), scene_id, role, subtitle, duration.
    """
    run_dir = Path(run_dir)
    path = run_dir / "adjusted_storyboard.json"
    if not path.exists():
        raise FileNotFoundError(f"adjusted_storyboard.json not found in {run_dir}")

    storyboard = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(storyboard, list):
        raise ValueError("adjusted_storyboard.json must contain a list")

    result = []
    for i, shot in enumerate(storyboard, start=1):
        result.append({
            "index": i,
            "scene_id": f"scene_{i:02d}",
            "role": shot.get("subtitle_role", "primary"),
            "subtitle": shot.get("subtitle", ""),
            "duration": shot.get("duration"),
        })
    return result


def update_storyboard_subtitles(run_dir: Path, updates: list[dict[str, Any]]) -> dict[str, Any]:
    """Update subtitle texts in adjusted_storyboard.json.

    Args:
        run_dir: Path to the run directory.
        updates: List of dicts with "index" (1-based) and "subtitle" fields.

    Returns:
        Dict with success, changed_count, backup_path.
    """
    run_dir = Path(run_dir)
    path = run_dir / "adjusted_storyboard.json"
    if not path.exists():
        raise FileNotFoundError(f"adjusted_storyboard.json not found in {run_dir}")

    storyboard = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(storyboard, list):
        raise ValueError("adjusted_storyboard.json must contain a list")

    # Validate all indices before making any changes
    max_index = len(storyboard)
    for update in updates:
        idx = update.get("index")
        if idx is None:
            raise ValueError("Each update must have an 'index' field")
        if not isinstance(idx, int) or idx < 1 or idx > max_index:
            raise ValueError(f"index {idx} out of range (1-{max_index})")
        if "subtitle" not in update:
            raise ValueError(f"Update at index {idx} missing 'subtitle' field")

    # Build index -> update map
    update_map = {u["index"]: u for u in updates}

    # Create backup
    backups_dir = run_dir / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    existing_backups = sorted(backups_dir.glob("adjusted_storyboard_*.json"))
    next_num = 1
    if existing_backups:
        try:
            last = existing_backups[-1].stem
            next_num = int(last.replace("adjusted_storyboard_", "")) + 1
        except ValueError:
            next_num = 1
    backup_name = f"adjusted_storyboard_{next_num:03d}.json"
    backup_path = backups_dir / backup_name
    shutil.copy2(path, backup_path)

    # Apply updates
    changed_count = 0
    for i, shot in enumerate(storyboard, start=1):
        if i in update_map:
            new_subtitle = update_map[i]["subtitle"]
            if shot.get("subtitle") != new_subtitle:
                shot["subtitle"] = new_subtitle
                changed_count += 1

    # Write back
    path.write_text(json.dumps(storyboard, ensure_ascii=False, indent=2), encoding="utf-8-sig")

    return {
        "success": True,
        "changed_count": changed_count,
        "backup_path": str(backup_path),
    }
