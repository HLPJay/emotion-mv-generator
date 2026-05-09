from __future__ import annotations


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _clean_line(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    if cleaned[-1] in "。！？!?，,；;":
        return cleaned
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
        "cinematic emotional ambient score",
        "wide atmospheric space",
        "soft piano motif",
        "warm evolving pads",
        "low cello or soft synth bass foundation",
        "gentle pulse underneath",
        "slow tempo",
        "gradual emotional build",
        "medium-low dynamic range",
        "clear immersive atmosphere",
        "intimate and reflective",
        "no vocal",
        "no lyrics",
        "not melodramatic",
        "do not overpower narration",
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
        role = item.get("role", "primary")
        semantic_role = item.get("semantic_role", "setup")
        source_duration = float(item.get("duration", 1.0))

        if text == "...":
            pause = round(_pause_duration(pause_type, source_duration), 2)
            timeline_cursor += pause
            visual_durations.append(pause)
            continue

        line = _clean_line(item.get("spoken_text") or text)
        duration = _line_duration(line, source_duration)
        next_pause = 0.0
        delivery = (
            "softer, slightly closer, like a parenthetical inner note"
            if role == "secondary"
            else "low, restrained, intimate, like a reflective self monologue"
        )
        breath_before = bool(item.get("breath_before") or (narration and duration >= 2.2))
        narration.append(
            {
                "text": line,
                "subtitle_text": text,
                "role": role,
                "semantic_role": semantic_role,
                "voice_layer": item.get("voice_layer", "inner" if role == "secondary" else ("direct" if role == "question" else "main")),
                "unit_id": item.get("unit_id"),
                "emphasis_words": item.get("emphasis_words", []),
                "speed": item.get("speed"),
                "pitch": item.get("pitch"),
                "volume": item.get("volume", 0.88 if role == "secondary" else 1.0),
                "emotion": item.get("emotion"),
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
        if rhythm_index < len(rhythm):
            shot_copy["subtitle_role"] = rhythm[rhythm_index].get("role", "primary")
            shot_copy["semantic_role"] = rhythm[rhythm_index].get("semantic_role", "setup")
            shot_copy["unit_id"] = rhythm[rhythm_index].get("unit_id")
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
        "secondary_voice": {
            "model": "speech-2.8-hd",
            "speed": 0.86,
            "pitch": -2,
            "volume": 0.84,
            "emotion": "neutral",
        },
        "direct_voice": {
            "model": "speech-2.8-hd",
            "speed": 0.84,
            "pitch": -1,
            "volume": 0.94,
            "emotion": "neutral",
        },
        "narration": narration,
        "music": {
            "model": "music-2.6",
            "prompt": _music_prompt(emotion),
            "duration": music_duration,
            "volume": 0.34,
            "fade_in": 1.2,
            "fade_out": 2.5,
        },
        "mix": {
            "narration_volume": 1.0,
            "music_volume": 0.34,
            "duck_music_under_voice": True,
            "ambient_fallback_volume": 0.28,
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
