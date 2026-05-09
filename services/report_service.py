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


def _translate_reason_tag(tag: str) -> str:
    """将机读 reason tag 翻译为中文可读描述"""
    mapping = {
        "explicit_scene_cue": "明确场景线索",
        "metaphor_scene_cue": "隐喻场景线索",
        "productivity_or_habit_theme": "习惯沉淀、现实执行",
        "cognition_to_action_theme": "认知到行动主题",
        "daily_life_or_habit_theme": "日常生活或习惯主题",
        "challenge_or_threshold_theme": "挑战或跨边界主题",
        "ocean_openness_theme": "海边开阔主题",
        "cosmos_cognition_theme": "星空认知主题",
        "family_origin_theme": "家庭或根源主题",
        "urban_career_theme": "城市职业主题",
        "explicit_train_or_travel_cue": "明确火车/旅途用词",
        "generic_journey_cue_penalized_without_train_cue": "无明确火车词，泛旅程词降权",
        "productivity_theme_without_mountain_cue_penalty": "现实执行主题但无山路线索，降权",
        "ocean_requires_clear_ocean_cue": "无明确海边词，降权",
        "cosmos_requires_clear_cosmos_cue": "无明确星空词，降权",
        "rural_requires_family_or_origin_cue": "无明确农村/亲情词，降权",
        "explicit_scene_elsewhere_penalty": "其他场景有更强匹配，降权",
        "reality_override:abstract_world_lacks_explicit_scene": "抽象世界无明确场景线索，强制选现实世界",
    }
    # 处理带数值的 tag: explicit_scene_cue:+15
    for prefix, chinese in mapping.items():
        if tag.startswith(prefix):
            suffix = tag[len(prefix):]
            if suffix:
                return f"{chinese}{suffix}"
            return chinese
    # 处理 override 格式
    if tag.startswith("overridden_by_reality:"):
        return f"因抽象世界无场景线索，被现实世界取代（{tag.split(':')[1]}）"
    return tag


def _translate_reasons(reasons: list[str]) -> str:
    """将 reason tag 列表转为中文可读摘要"""
    if not reasons:
        return ""
    parts = [_translate_reason_tag(r) for r in reasons]
    # 去重（同义 tag 可能重复）
    seen = set()
    unique = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return "；".join(unique)


def _visual_world_selection_summary(visual_poetic_plan: dict) -> dict:
    world = visual_poetic_plan.get("world") or {}
    debug_items = world.get("selection_debug") or []
    top_candidates = []
    for item in debug_items[:3]:
        reasons = item.get("reasons") or []
        top_candidates.append(
            {
                "id": item.get("id"),
                "label": item.get("label"),
                "score": item.get("score"),
                "reasons": reasons,
                "reasons_cn": _translate_reasons(reasons),
            }
        )

    selected = top_candidates[0] if top_candidates else {}
    reasons = selected.get("reasons") or []
    if world.get("selection_mode") == "manual_world_theme_archetype":
        readable = "手动选择意境世界"
    elif reasons:
        readable = _translate_reasons(reasons)
    elif world.get("selection_mode"):
        readable = f"自动匹配，分数 {world.get('match_score')}"
    else:
        readable = ""

    return {
        "id": world.get("id"),
        "label": world.get("label"),
        "score": world.get("match_score"),
        "mode": world.get("selection_mode"),
        "reason": readable,
        "reason_raw": "; ".join(reasons),
        "top_candidates": top_candidates,
    }


def build_run_report(run_dir: Path) -> dict:
    input_text = _read_text(run_dir / "input.txt")
    input_structure = _read_json(run_dir / "input_structure.json") or {}
    semantic_structure = _read_json(run_dir / "semantic_structure.json") or {}
    emotion = _read_json(run_dir / "emotion.json") or {}
    subtitle_plan = _read_json(run_dir / "subtitle_plan.json") or {}
    expression_plan = _read_json(run_dir / "expression_plan.json") or {}
    visual_poetic_plan = _read_json(run_dir / "visual_poetic_plan.json") or {}
    narrative_plan = _read_json(run_dir / "narrative_plan.json") or {}
    storyboard = _read_json(run_dir / "storyboard.json") or []
    audio_plan = _read_json(run_dir / "audio_plan.json") or {}
    visual_style = _read_json(run_dir / "visual_style.json") or {}
    visual_continuity = _read_json(run_dir / "visual_continuity.json") or {}
    events = _read_events(run_dir)
    adjusted_storyboard = _read_json(run_dir / "adjusted_storyboard.json") or []
    video_compose_timings = _read_json(run_dir / "video_compose_timings.json") or {}

    final_video = run_dir / "final.mp4"
    narration = run_dir / "audio" / "narration.mp3"
    bgm = run_dir / "audio" / "bgm.mp3"
    music_error = _read_text(run_dir / "audio" / "music_generation_error.txt")
    narration_segments = _asset_list(run_dir / "audio", "narration_*.mp3")
    environment_sounds = _asset_list(run_dir / "audio", "environment_*.wav")

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
    if not narration.exists() and not narration_segments:
        warnings.append("旁白文件不存在，未找到 narration.mp3 或 narration_*.mp3")
    if not bgm.exists():
        warnings.append("BGM 文件 bgm.mp3 不存在，可能使用了 fallback ambient")
    if music_error:
        warnings.append(f"music_generation_failed: {music_error}")
    guard = subtitle_plan.get("guard") or {}
    if guard.get("changed"):
        warnings.append(f"subtitle_guard_changed: {', '.join(guard.get('actions', []))}")
    if len(subtitle_plan.get("subtitles", [])) > 8:
        warnings.append("字幕节奏项超过 8 条")

    visual_world_selection = _visual_world_selection_summary(visual_poetic_plan)

    report = {
        "run_id": run_dir.name,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "paths": {
            "run_dir": str(run_dir),
            "final_video": str(final_video),
            "narration": str(narration),
            "narration_segments": [item["path"] for item in narration_segments],
            "bgm": str(bgm),
            "environment_sounds": [item["path"] for item in environment_sounds],
        },
        "input": {
            "text": input_text,
            "length": len(input_text),
            "structure": input_structure,
            "semantic_structure": semantic_structure,
        },
        "content_summary": {
            "main_theme": input_structure.get("main_theme"),
            "parenthetical_theme": input_structure.get("parenthetical_theme"),
            "parenthetical_relationship": input_structure.get("relationship"),
            "parenthetical_emotional_shift": input_structure.get("emotional_shift"),
            "parenthetical_visual_transition": input_structure.get("visual_transition"),
            "question_analysis": input_structure.get("question_analysis"),
            "semantic_sentence_count": len(semantic_structure.get("sentences", [])),
            "semantic_unit_count": len(semantic_structure.get("semantic_units", [])),
            "semantic_quality": semantic_structure.get("quality_checks"),
            "semantic_narrative_arc": semantic_structure.get("narrative_arc"),
            "semantic_visual_guidance": semantic_structure.get("visual_guidance"),
            "emotion": emotion.get("emotion"),
            "mood": emotion.get("mood"),
            "tone": emotion.get("tone"),
            "subtitles_count": len(subtitle_plan.get("subtitles", [])),
            "subtitle_guard": guard,
            "expression_profile": expression_plan.get("profile_label"),
            "visual_archetype": (visual_poetic_plan.get("archetype") or {}).get("label"),
            "visual_world": (visual_poetic_plan.get("world") or {}).get("label"),
            "visual_world_id": (visual_poetic_plan.get("world") or {}).get("id"),
            "visual_world_selection": visual_world_selection,
            "visual_motif_symbols": ((visual_poetic_plan.get("motif") or {}).get("recurring_symbols") or []),
            "narrative_arc": narrative_plan.get("arc"),
            "narrative_turning_point": narrative_plan.get("turning_point"),
            "narrative_strategy": narrative_plan.get("visual_strategy"),
            "narrative_functions": [
                {
                    "text": shot.get("subtitle_text"),
                    "function": shot.get("function"),
                    "purpose": shot.get("purpose"),
                    "visual_intent": shot.get("visual_intent"),
                    "semantic_unit_id": shot.get("semantic_unit_id"),
                    "sentence_id": shot.get("sentence_id"),
                    "visual_role": shot.get("visual_role"),
                }
                for shot in narrative_plan.get("shots", [])
            ],
            "expression_units_count": len(expression_plan.get("units", [])),
            "expression_roles": [
                {
                    "text": unit.get("subtitle_text"),
                    "role": unit.get("role"),
                    "semantic_role": unit.get("semantic_role"),
                    "voice_layer": unit.get("voice_layer"),
                    "emphasis_words": unit.get("emphasis_words", []),
                }
                for unit in expression_plan.get("units", [])
            ],
            "storyboard_count": len(storyboard),
            "adjusted_storyboard_count": len(adjusted_storyboard),
            "target_duration": audio_plan.get("target_duration"),
            "music_prompt": (audio_plan.get("music") or {}).get("prompt"),
            "music_error": music_error,
            "visual_style": (visual_style.get("style") or {}).get("label"),
            "visual_style_id": (visual_style.get("style") or {}).get("id"),
            "visual_continuity_subject": (visual_continuity.get("subject") or {}).get("identity"),
            "visual_continuity_location": (visual_continuity.get("location") or {}).get("primary_space"),
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
        "audio_status": {
            "bgm_exists": bgm.exists(),
            "fallback_ambient_exists": (run_dir / "audio" / "generated_ambient.wav").exists(),
            "environment_sound_count": len(environment_sounds),
            "music_error": music_error,
            "used_music_fallback": not bgm.exists(),
        },
        "performance": {
            "video_compose": video_compose_timings,
        },
        "assets": {
            "images": images,
            "subtitle_images": subtitle_images,
            "narration_segments": narration_segments,
            "environment_sounds": environment_sounds,
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
    visual_world_selection = content.get("visual_world_selection") or {}
    def _fmt_candidate(item):
        base = f"- {item.get('label')} (`{item.get('id')}`): {item.get('score')}，{item.get('reasons_cn') or '无额外理由'}"
        raw = item.get('reasons')
        return base + (f" | `{{{'; '.join(raw)}}}`" if raw else "")

    candidate_text = "\n".join(_fmt_candidate(item) for item in visual_world_selection.get("top_candidates", [])) or "- 无"
    return f"""# Run Report

## Basic

- Run ID: `{report['run_id']}`
- Input: {report['input']['text']}
- Main Theme: {content.get('main_theme')}
- Parenthetical Relationship: {content.get('parenthetical_relationship')}
- Parenthetical Theme: {content.get('parenthetical_theme')}
- Semantic Sentences: {content.get('semantic_sentence_count')}
- Semantic Units: {content.get('semantic_unit_count')}
- Emotion: {content.get('emotion')}
- Mood: {content.get('mood')}
- Tone: {content.get('tone')}
- Visual Style: {content.get('visual_style')} (`{content.get('visual_style_id')}`)
- Expression Profile: {content.get('expression_profile')}
- Visual Archetype: {content.get('visual_archetype')}
- Visual World: {content.get('visual_world')} (`{content.get('visual_world_id')}`)
- Visual World Mode: {visual_world_selection.get('mode')}
- Visual World Reason: {visual_world_selection.get('reason')}
- Narrative Arc: {content.get('narrative_arc')}
- Turning Point: {content.get('narrative_turning_point')}

## Visual World Selection

{candidate_text}

## Structure

- Expression Units: {content.get('expression_units_count')}
- Subtitles: {content.get('subtitles_count')}
- Subtitle Guard Changed: {content.get('subtitle_guard', {}).get('changed')}
- Storyboard: {content.get('storyboard_count')}
- Adjusted Storyboard: {content.get('adjusted_storyboard_count')}
- Target Duration: {content.get('target_duration')}s
- Semantic Quality: {content.get('semantic_quality')}

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
- Narration Segments: {len(assets.get('narration_segments', []))}
- Environment Sounds: {len(assets.get('environment_sounds', []))}

## Models

- Speech: {report['models'].get('speech')}
- Music: {report['models'].get('music')}

## Warnings

{warning_text}

## Performance

- Video Compose Preset: {report.get('performance', {}).get('video_compose', {}).get('preset')}
- Video Compose Timings: {report.get('performance', {}).get('video_compose', {}).get('timings')}

## Events

{event_text}

## Music Prompt

{content.get('music_prompt')}
"""
