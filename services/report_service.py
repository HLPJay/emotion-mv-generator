from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _probe_media(path: Path) -> dict:
    if not path.exists():
        return {"exists": False}
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size",
        "-show_entries",
        "stream=index,codec_type,codec_name,sample_rate,channels,width,height",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True)
        data = json.loads(result.stdout.decode("utf-8", errors="ignore"))
    except Exception as exc:
        return {"exists": True, "error": str(exc)}
    data["exists"] = True
    return data


def _volume_detect(path: Path) -> dict:
    if not path.exists():
        return {"exists": False}
    command = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(path),
        "-af",
        "volumedetect",
        "-vn",
        "-sn",
        "-dn",
        "-f",
        "null",
        "NUL",
    ]
    try:
        result = subprocess.run(command, capture_output=True)
        output = result.stderr.decode("utf-8", errors="ignore")
    except Exception as exc:
        return {"exists": True, "error": str(exc)}

    metrics = {"exists": True}
    for line in output.splitlines():
        if "mean_volume:" in line:
            metrics["mean_volume"] = line.split("mean_volume:", 1)[1].strip()
        if "max_volume:" in line:
            metrics["max_volume"] = line.split("max_volume:", 1)[1].strip()
    return metrics


def _asset_list(directory: Path, pattern: str) -> list[dict]:
    if not directory.exists():
        return []
    return [
        {
            "name": path.name,
            "path": str(path),
            "size": path.stat().st_size,
        }
        for path in sorted(directory.glob(pattern))
    ]


def _read_events(run_dir: Path) -> list[dict]:
    path = run_dir / "run_events.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def _duration(media_info: dict) -> float | None:
    try:
        return round(float(media_info.get("format", {}).get("duration")), 3)
    except (TypeError, ValueError):
        return None


def _video_resolution(media_info: dict) -> str | None:
    for stream in media_info.get("streams", []):
        if stream.get("codec_type") == "video":
            return f"{stream.get('width')}x{stream.get('height')}"
    return None


def _has_audio(media_info: dict) -> bool:
    return any(stream.get("codec_type") == "audio" for stream in media_info.get("streams", []))


def build_run_report(run_dir: Path) -> dict:
    input_text = _read_text(run_dir / "input.txt")
    emotion = _read_json(run_dir / "emotion.json") or {}
    subtitle_plan = _read_json(run_dir / "subtitle_plan.json") or {}
    storyboard = _read_json(run_dir / "storyboard.json") or []
    audio_plan = _read_json(run_dir / "audio_plan.json") or {}
    visual_style = _read_json(run_dir / "visual_style.json") or {}
    events = _read_events(run_dir)
    adjusted_storyboard = _read_json(run_dir / "adjusted_storyboard.json") or []

    final_video = run_dir / "final.mp4"
    narration = run_dir / "audio" / "narration.mp3"
    bgm = run_dir / "audio" / "bgm.mp3"

    video_info = _probe_media(final_video)
    narration_info = _probe_media(narration)
    bgm_info = _probe_media(bgm)
    volume = _volume_detect(final_video)

    images = _asset_list(run_dir / "images", "scene_*.png")
    subtitle_images = _asset_list(run_dir / "subtitles", "subtitle_*.png")

    warnings = []
    if not video_info.get("exists"):
        warnings.append("final.mp4 不存在")
    if not _has_audio(video_info):
        warnings.append("final.mp4 未检测到音频流")
    if len(images) != len(adjusted_storyboard):
        warnings.append("图片数量与调整后分镜数量不一致")
    if not narration.exists():
        warnings.append("旁白文件 narration.mp3 不存在")
    if not bgm.exists():
        warnings.append("BGM 文件 bgm.mp3 不存在，可能使用了 fallback ambient")
    guard = subtitle_plan.get("guard") or {}
    if guard.get("changed"):
        warnings.append(f"subtitle_guard_changed: {', '.join(guard.get('actions', []))}")
    if len(subtitle_plan.get("subtitles", [])) > 8:
        warnings.append("字幕节奏项超过 8 条")

    report = {
        "run_id": run_dir.name,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "paths": {
            "run_dir": str(run_dir),
            "final_video": str(final_video),
            "narration": str(narration),
            "bgm": str(bgm),
        },
        "input": {
            "text": input_text,
            "length": len(input_text),
        },
        "content_summary": {
            "emotion": emotion.get("emotion"),
            "mood": emotion.get("mood"),
            "tone": emotion.get("tone"),
            "subtitles_count": len(subtitle_plan.get("subtitles", [])),
            "subtitle_guard": guard,
            "storyboard_count": len(storyboard),
            "adjusted_storyboard_count": len(adjusted_storyboard),
            "target_duration": audio_plan.get("target_duration"),
            "music_prompt": (audio_plan.get("music") or {}).get("prompt"),
            "visual_style": (visual_style.get("style") or {}).get("label"),
            "visual_style_id": (visual_style.get("style") or {}).get("id"),
        },
        "models": {
            "text": "config:model",
            "image": "config:image.model",
            "speech": (audio_plan.get("voice") or {}).get("model"),
            "music": (audio_plan.get("music") or {}).get("model"),
        },
        "media": {
            "video": {
                "info": video_info,
                "duration": _duration(video_info),
                "resolution": _video_resolution(video_info),
                "has_audio": _has_audio(video_info),
                "volume": volume,
            },
            "narration": {
                "info": narration_info,
                "duration": _duration(narration_info),
            },
            "bgm": {
                "info": bgm_info,
                "duration": _duration(bgm_info),
            },
        },
        "assets": {
            "images": images,
            "subtitle_images": subtitle_images,
        },
        "events": events,
        "warnings": warnings,
    }
    return report


def write_run_report(run_dir: Path) -> dict:
    report = build_run_report(run_dir)
    json_path = run_dir / "run_report.json"
    md_path = run_dir / "run_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_report_markdown(report), encoding="utf-8")
    return report


def render_report_markdown(report: dict) -> str:
    warnings = report.get("warnings") or []
    warning_text = "\n".join(f"- {item}" for item in warnings) if warnings else "- 无"
    events = [event for event in report.get("events", []) if event.get("status") in {"success", "failed"}]
    event_text = "\n".join(
        f"- {event.get('step')}: {event.get('status')} ({event.get('duration_seconds', '-') }s)"
        for event in events
    ) or "- 无"
    media = report["media"]
    content = report["content_summary"]
    assets = report["assets"]
    return f"""# Run Report

## Basic

- Run ID: `{report['run_id']}`
- Input: {report['input']['text']}
- Emotion: {content.get('emotion')}
- Mood: {content.get('mood')}
- Tone: {content.get('tone')}
- Visual Style: {content.get('visual_style')} (`{content.get('visual_style_id')}`)

## Structure

- Subtitles: {content.get('subtitles_count')}
- Subtitle Guard Changed: {content.get('subtitle_guard', {}).get('changed')}
- Storyboard: {content.get('storyboard_count')}
- Adjusted Storyboard: {content.get('adjusted_storyboard_count')}
- Target Duration: {content.get('target_duration')}s

## Media

- Video Duration: {media['video'].get('duration')}s
- Resolution: {media['video'].get('resolution')}
- Has Audio: {media['video'].get('has_audio')}
- Mean Volume: {media['video'].get('volume', {}).get('mean_volume')}
- Max Volume: {media['video'].get('volume', {}).get('max_volume')}
- Narration Duration: {media['narration'].get('duration')}s
- BGM Duration: {media['bgm'].get('duration')}s

## Assets

- Images: {len(assets.get('images', []))}
- Subtitle PNGs: {len(assets.get('subtitle_images', []))}

## Models

- Speech: {report['models'].get('speech')}
- Music: {report['models'].get('music')}

## Warnings

{warning_text}

## Events

{event_text}

## Music Prompt

{content.get('music_prompt')}
"""
