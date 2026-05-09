from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable

from services.event_service import log_event, track_step
from services.ffmpeg_service import replace_video_audio
from services.report_service import write_run_report
from services.run_service import write_json
from services.video_service import compose_video


def next_recompose_output_path(run_dir: Path, mode: str) -> tuple[Path, int]:
    """Generate next versioned output path for recomposed video.

    Returns (output_path, version) where version starts at 1.
    Output goes into run_dir/recomposed/ directory.
    """
    recomposed_dir = run_dir / "recomposed"
    recomposed_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"final_{mode}_recompose_"
    existing = list(recomposed_dir.glob(f"{prefix}*.mp4"))
    versions = []
    for f in existing:
        try:
            v = int(f.stem.replace(prefix, ""))
            versions.append(v)
        except ValueError:
            pass
    next_version = (max(versions) + 1) if versions else 1
    output_path = recomposed_dir / f"{prefix}{next_version:03d}.mp4"
    return output_path, next_version


def get_recomposable_runs() -> list[dict[str, Any]]:
    """Return all runs that have enough assets to be recomposed."""
    runs_dir = Path(__file__).resolve().parents[1] / "generated" / "runs"
    if not runs_dir.exists():
        return []

    runs = []
    for run_path in runs_dir.iterdir():
        if not run_path.is_dir():
            continue
        storyboard_path = run_path / "adjusted_storyboard.json"
        audio_plan_path = run_path / "audio_plan.json"
        emotion_path = run_path / "emotion.json"
        images_dir = run_path / "images"
        if not all(p.exists() for p in [storyboard_path, audio_plan_path, emotion_path, images_dir]):
            continue

        storyboard = json.loads(storyboard_path.read_text(encoding="utf-8-sig"))
        if not isinstance(storyboard, list) or len(storyboard) == 0:
            continue

        # Validate full image sequence: scene_01 through scene_N must all exist
        missing_images = []
        for i in range(1, len(storyboard) + 1):
            img_path = images_dir / f"scene_{i:02d}.png"
            if not img_path.exists():
                missing_images.append(img_path.name)
        if missing_images:
            continue

        run_id = run_path.name
        final_video = run_path / "final.mp4"
        bgm_path = run_path / "audio" / "bgm.mp3"
        audio_dir = run_path / "audio"

        # Build narration count using actual file naming convention: narration_{index:02d}_{role}.mp3
        narration_count = 0
        missing_narration: list[str] = []
        if audio_plan_path.exists():
            audio_plan_data = json.loads(audio_plan_path.read_text(encoding="utf-8-sig"))
            narration_segments = audio_plan_data.get("narration") or []
            for idx, segment in enumerate(narration_segments, start=1):
                role = segment.get("role", "primary")
                seg_path = audio_dir / f"narration_{idx:02d}_{role}.mp3"
                if seg_path.exists() and seg_path.stat().st_size > 0:
                    narration_count += 1
                else:
                    missing_narration.append(seg_path.name)

        input_txt = run_path / "input.txt"
        if input_txt.exists():
            label_text = input_txt.read_text(encoding="utf-8-sig").strip()[:40]
        else:
            label_text = run_id.split("_", 2)[-1][:40] if "_" in run_id else run_id

        runs.append({
            "run_id": run_id,
            "path": str(run_path),
            "label": label_text,
            "has_final_video": final_video.exists(),
            "has_bgm": bgm_path.exists() and bgm_path.stat().st_size > 0,
            "narration_count": narration_count,
            "scene_count": len(storyboard),
            "mtime": run_path.stat().st_mtime,
        })

    runs.sort(key=lambda r: r["mtime"], reverse=True)
    return runs


def recompose_run_video(
    run_dir: Path,
    *,
    backup_existing: bool = True,
    strict_audio: bool = False,
    mode: str = "moviepy",
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Recompose final.mp4 from existing assets without regenerating images or calling LLM.

    Args:
        run_dir: Path to the run directory.
        backup_existing: If True, backup existing final.mp4 before overwriting.
        strict_audio: If True, raise error when BGM or narration audio is missing
                      instead of allowing regeneration. Use when you want to
                      guarantee no audio generation calls.
        mode: "moviepy" for full recompose, "audio_only" for FFmpeg fast audio replacement.
        progress_callback: Optional callback for progress updates.
    """
    run_dir = Path(run_dir)

    # Audio-only mode: fast path that doesn't regenerate video
    if mode == "audio_only":
        return _recompose_audio_only(run_dir, backup_existing=backup_existing, strict_audio=strict_audio)

    # MoviePy mode: full recompose (original logic)
    for name in ["adjusted_storyboard.json", "audio_plan.json", "emotion.json"]:
        path = run_dir / name
        if not path.exists():
            raise FileNotFoundError(f"Missing required file: {name} in {run_dir}")

    images_dir = run_dir / "images"
    if not images_dir.exists():
        raise FileNotFoundError(f"Missing images directory: {images_dir}")

    storyboard = json.loads((run_dir / "adjusted_storyboard.json").read_text(encoding="utf-8-sig"))
    emotion = json.loads((run_dir / "emotion.json").read_text(encoding="utf-8-sig"))
    audio_plan = json.loads((run_dir / "audio_plan.json").read_text(encoding="utf-8-sig"))

    image_paths = []
    for i in range(1, len(storyboard) + 1):
        img_path = images_dir / f"scene_{i:02d}.png"
        if not img_path.exists():
            raise FileNotFoundError(f"Missing image: {img_path}")
        image_paths.append(img_path)

    if strict_audio:
        audio_dir = run_dir / "audio"
        bgm_path = audio_dir / "bgm.mp3"
        missing_audio: list[str] = []
        if not (bgm_path.exists() and bgm_path.stat().st_size > 0):
            missing_audio.append("bgm.mp3")
        for idx, segment in enumerate((audio_plan.get("narration") or []), start=1):
            role = segment.get("role", "primary")
            seg_path = audio_dir / f"narration_{idx:02d}_{role}.mp3"
            if not (seg_path.exists() and seg_path.stat().st_size > 0):
                missing_audio.append(seg_path.name)
        if missing_audio:
            raise FileNotFoundError(
                f"strict_audio=True but missing audio files: {missing_audio}"
            )

    final_video = run_dir / "final.mp4"
    backup_video = run_dir / "final_before_recompose.mp4"
    if backup_existing and final_video.exists() and not backup_video.exists():
        shutil.copy2(final_video, backup_video)

    # Generate versioned output path (never overwrite final.mp4)
    output_video, version = next_recompose_output_path(run_dir, mode="moviepy")

    log_event(run_dir, "recompose", "started", mode="moviepy")

    try:
        with track_step(run_dir, "video_compose"):
            compose_video(
                storyboard,
                image_paths,
                emotion,
                audio_plan,
                run_dir,
                progress_callback=progress_callback,
                output_path=output_video,
            )

        log_event(
            run_dir,
            "recompose",
            "success",
            engine="moviepy",
            mode="moviepy",
            source_video=str(final_video),
            output_path=str(output_video),
            version=version,
        )
        report = write_run_report(run_dir)

        bgm_path = run_dir / "audio" / "bgm.mp3"
        return {
            "success": True,
            "run_dir": str(run_dir),
            "source_video": str(final_video),
            "output_path": str(output_video),
            "version": version,
            "backup_path": str(backup_video) if backup_video.exists() else None,
            "bgm_exists": bgm_path.exists() and bgm_path.stat().st_size > 0,
            "narration_count": sum(
                1 for idx, seg in enumerate((audio_plan.get("narration") or []), start=1)
                if (run_dir / "audio" / f"narration_{idx:02d}_{seg.get('role', 'primary')}.mp3").exists()
            ),
            "audio_status": report.get("audio_status", {}),
            "warnings": report.get("warnings", []),
            "scene_count": len(storyboard),
        }
    except Exception as exc:
        log_event(run_dir, "recompose", "failed", engine="moviepy", mode="moviepy", error=str(exc), error_type=exc.__class__.__name__)
        raise


def _recompose_audio_only(
    run_dir: Path,
    backup_existing: bool = True,
    strict_audio: bool = False,
) -> dict[str, Any]:
    """Fast audio replacement using FFmpeg without re-encoding video.

    Does not regenerate images, subtitles, or call LLM.
    """
    run_dir = Path(run_dir)
    audio_dir = run_dir / "audio"
    final_video = run_dir / "final.mp4"

    # Validate existing final.mp4
    if not final_video.exists():
        error_msg = f"audio_only mode requires existing final.mp4, not found at {final_video}"
        log_event(run_dir, "recompose", "failed", error=error_msg, mode="audio_only", error_type="FileNotFoundError")
        raise FileNotFoundError(error_msg)

    # Load audio_plan for narration info
    audio_plan_path = run_dir / "audio_plan.json"
    audio_plan = json.loads(audio_plan_path.read_text(encoding="utf-8-sig")) if audio_plan_path.exists() else {}

    bgm_path = audio_dir / "bgm.mp3"

    # Validate audio
    if strict_audio:
        missing_audio: list[str] = []
        if not (bgm_path.exists() and bgm_path.stat().st_size > 0):
            missing_audio.append("bgm.mp3")
        # Check ALL narration files from audio_plan, not just the ones that exist
        for idx, segment in enumerate((audio_plan.get("narration") or []), start=1):
            role = segment.get("role", "primary")
            seg_path = audio_dir / f"narration_{idx:02d}_{role}.mp3"
            if not (seg_path.exists() and seg_path.stat().st_size > 0):
                missing_audio.append(seg_path.name)
        if missing_audio:
            error_msg = f"strict_audio=True but missing audio files: {missing_audio}"
            log_event(run_dir, "recompose", "failed", error=error_msg, mode="audio_only", error_type="FileNotFoundError")
            raise FileNotFoundError(error_msg)

    if not (bgm_path.exists() and bgm_path.stat().st_size > 0):
        error_msg = f"BGM file not found: {bgm_path}"
        log_event(run_dir, "recompose", "failed", error=error_msg, mode="audio_only", error_type="FileNotFoundError")
        raise FileNotFoundError(error_msg)

    # Build audio_tracks list with start/volume metadata for FFmpeg
    bgm_volume = (audio_plan.get("music") or {}).get("volume", 0.22) or 0.22
    audio_tracks: list[dict] = [
        {"path": bgm_path, "start": 0.0, "volume": bgm_volume}
    ]
    for idx, segment in enumerate((audio_plan.get("narration") or []), start=1):
        role = segment.get("role", "primary")
        seg_path = audio_dir / f"narration_{idx:02d}_{role}.mp3"
        if seg_path.exists() and seg_path.stat().st_size > 0:
            audio_tracks.append({
                "path": seg_path,
                "start": segment.get("start", 0.0),
                "volume": 1.0,  # narration uses full volume
            })

    # Backup original
    backup_video = run_dir / "final_before_recompose.mp4"
    if backup_existing and not backup_video.exists():
        shutil.copy2(final_video, backup_video)

    # Generate versioned output path (never overwrite final.mp4)
    output_video, version = next_recompose_output_path(run_dir, mode="audio_only")

    log_event(run_dir, "recompose", "started", mode="audio_only")

    try:
        result = replace_video_audio(
            input_video=final_video,
            output_video=output_video,
            audio_tracks=audio_tracks,
        )

        if not result["success"]:
            # FFmpeg failed - original video untouched since replace_video_audio writes to tmp first
            log_event(
                run_dir,
                "recompose",
                "failed",
                engine="ffmpeg",
                mode="audio_only",
                error=result.get("error", "Unknown FFmpeg error"),
                error_type=result.get("error_type", "FFmpegError"),
            )
            raise RuntimeError(f"FFmpeg audio replacement failed: {result.get('error')}")

        # Success
        log_event(
            run_dir,
            "recompose",
            "success",
            engine="ffmpeg",
            mode="audio_only",
            duration_seconds=result.get("elapsed_seconds"),
            video_stream_copied=result.get("video_stream_copied"),
            input_video_duration_seconds=result.get("input_video_duration_seconds"),
            output_duration_seconds=result.get("output_duration_seconds"),
            source_video=str(final_video),
            output_path=str(output_video),
            version=version,
        )

        return {
            "success": True,
            "run_dir": str(run_dir),
            "source_video": str(final_video),
            "output_path": str(output_video),
            "version": version,
            "backup_path": str(backup_video) if backup_video.exists() else None,
            "engine": result.get("engine"),
            "mode": "audio_only",
            "video_stream_copied": result.get("video_stream_copied"),
            "input_video_duration_seconds": result.get("input_video_duration_seconds"),
            "elapsed_seconds": result.get("elapsed_seconds"),
            "output_duration_seconds": result.get("output_duration_seconds"),
            "warnings": result.get("warnings", []),
        }

    except Exception as exc:
        log_event(run_dir, "recompose", "failed", engine="ffmpeg", mode="audio_only", error=str(exc), error_type=exc.__class__.__name__)
        raise
