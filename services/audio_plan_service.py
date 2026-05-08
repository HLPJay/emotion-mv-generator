from __future__ import annotations


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _clean_line(text: str) -> str:
    cleaned = text.strip().rstrip("。！？!?，,；;")
    return cleaned + "。"


def _pause_duration(pause_type: str, source_duration: float) -> float:
    if pause_type == "short_pause":
        return _clamp(source_duration, 0.65, 1.0)
    if pause_type == "heavy_pause":
        return _clamp(source_duration, 1.05, 1.55)
    if pause_type == "ending_silence":
        return _clamp(source_duration, 1.5, 2.2)
    return 0.0


def _line_duration(text: str, source_duration: float) -> float:
    # Chinese emotional VO tends to need room. Keep short lines from snapping too fast.
    estimated = 0.34 * len(text.strip("。！？!?，, ")) + 0.75
    return round(_clamp(max(source_duration, estimated), 1.8, 3.4), 2)


def _music_prompt(emotion: dict) -> str:
    mood = emotion.get("mood", "deep night introspection")
    primary = emotion.get("emotion", "restrained sadness")
    mappings = [
        "minimal cinematic ambient",
        "deep night atmosphere",
        "soft low piano",
        "subtle warm pad",
        "slow tempo",
        "low dynamic range",
        "no vocal",
        "no lyrics",
        "restrained and realistic",
        "not dramatic",
        f"mood: {mood}",
        f"emotion: {primary}",
    ]
    return ", ".join(mappings)


def build_audio_plan(subtitle_plan: dict, emotion: dict, storyboard: list[dict]) -> dict:
    narration = []
    timeline_cursor = 0.8
    visual_durations = []

    rhythm = subtitle_plan.get("rhythm", [])
    for item in rhythm:
        text = item.get("text", "").strip()
        pause_type = item.get("pause_type", "none")
        source_duration = float(item.get("duration", 1.0))

        if text == "...":
            pause = round(_pause_duration(pause_type, source_duration), 2)
            timeline_cursor += pause
            visual_durations.append(pause)
            continue

        line = _clean_line(text)
        duration = _line_duration(line, source_duration)
        next_pause = 0.0
        delivery = "low, restrained, intimate, like a late-night self monologue"
        breath_before = bool(narration and duration >= 2.2)
        narration.append(
            {
                "text": line,
                "start": round(timeline_cursor, 2),
                "estimated_duration": duration,
                "pause_after": next_pause,
                "delivery": delivery,
                "breath_before": breath_before,
            }
        )
        timeline_cursor += duration
        visual_durations.append(duration)

    # Transfer explicit pause durations onto the previous spoken line, so TTS pause tags sit after words.
    narration_index = -1
    for item in rhythm:
        text = item.get("text", "").strip()
        if text == "...":
            if narration_index >= 0:
                narration[narration_index]["pause_after"] = round(
                    _pause_duration(item.get("pause_type", "short_pause"), float(item.get("duration", 1.0))),
                    2,
                )
        else:
            narration_index += 1

    target_duration = round(max(timeline_cursor + 1.2, sum(visual_durations) + 1.0), 2)
    music_duration = round(target_duration + 3.0, 2)

    adjusted_storyboard = []
    rhythm_index = 0
    for shot in storyboard:
        shot_copy = dict(shot)
        if rhythm_index < len(visual_durations):
            shot_copy["duration"] = visual_durations[rhythm_index]
        adjusted_storyboard.append(shot_copy)
        rhythm_index += 1

    return {
        "target_duration": target_duration,
        "lead_in": 0.8,
        "tail_silence": 1.2,
        "voice": {
            "model": "speech-2.8-hd",
            "voice_id": "male-qn-qingse",
            "speed": 0.82,
            "pitch": -1,
            "volume": 1.0,
            "emotion": "sad",
        },
        "narration": narration,
        "music": {
            "model": "music-2.6",
            "prompt": _music_prompt(emotion),
            "duration": music_duration,
            "volume": 0.22,
            "fade_in": 1.2,
            "fade_out": 2.5,
        },
        "mix": {
            "narration_volume": 1.0,
            "music_volume": 0.22,
            "duck_music_under_voice": True,
            "ambient_fallback_volume": 0.18,
        },
        "adjusted_storyboard": adjusted_storyboard,
    }


def narration_text_from_audio_plan(audio_plan: dict) -> str:
    lines = []
    for item in audio_plan.get("narration", []):
        text = item["text"]
        if item.get("breath_before"):
            text = f"(breath){text}"
        pause_after = float(item.get("pause_after", 0.0))
        if pause_after > 0:
            text = f"{text}<#{pause_after:.2f}#>"
        lines.append(text)
    return "\n".join(lines).strip()
