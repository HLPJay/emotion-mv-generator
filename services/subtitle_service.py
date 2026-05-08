from __future__ import annotations

import re

from services.llm_service import chat_json, llm_enabled


PUNCTUATION_RE = re.compile(r"[。！？!?；;，,\n]+")
PAUSE_RE = re.compile(r"(\.{3,}|…+)")
TRAILING_PUNCTUATION_RE = re.compile(r"[。！？!?；;，,.\s]+$")
MAX_SPOKEN_LINES = 4


def _clean_sentence(sentence: str) -> str:
    sentence = sentence.strip(" \t\r\n。！？!?；;，,")
    if not sentence:
        return ""
    return sentence + "。"


def build_subtitle_plan(reflection: str) -> dict:
    if llm_enabled():
        system_prompt = """
你是情绪短视频的字幕节奏师，不是文案创作者。
你只负责把用户原句拆成适合短视频观看的“字幕 + 停顿”节奏。

约束：
- 不新增观点。
- 不升华。
- 不说教。
- 保持真实感。
- 可以做轻微语序切分，但不能改变含义。
- "..." 必须作为独立字幕项，不能附着在句尾。
- 每个 "..." 都要说明 pause_type。
- 普通字幕尽量保留中文句号。
- 结尾必须有一个 ending_silence。
- 输出 JSON。
"""
        user_prompt = f"""
用户原句：
{reflection}

请拆成 5-9 个节奏项。
重要句后加入独立的 "..."。
不要加入鸡汤或新观点。

pause_type 只能使用：
- none: 普通字幕
- short_pause: 短停顿，适合轻微换气
- heavy_pause: 重停顿，适合情绪压住
- ending_silence: 结尾留白

请输出：
{{
  "subtitles": ["相比于生活的困境。", "...", "我一直更害怕的。", "...", "是怯弱的自己。", "..."],
  "rhythm": [
    {{"text": "相比于生活的困境。", "pause_type": "none", "duration": 2.2, "reason": "铺垫外部压力"}},
    {{"text": "...", "pause_type": "short_pause", "duration": 0.9, "reason": "换气"}},
    {{"text": "我一直更害怕的。", "pause_type": "none", "duration": 2.0, "reason": "转向内心"}},
    {{"text": "...", "pause_type": "heavy_pause", "duration": 1.2, "reason": "压住真正答案"}},
    {{"text": "是怯弱的自己。", "pause_type": "none", "duration": 2.4, "reason": "核心落点"}},
    {{"text": "...", "pause_type": "ending_silence", "duration": 1.5, "reason": "结尾留白"}}
  ]
}}
"""
        result = chat_json(system_prompt, user_prompt, temperature=0.25)
        return _guard_subtitle_plan(_normalize_plan(result), reflection)

    raw_parts = [_clean_sentence(part) for part in PUNCTUATION_RE.split(reflection)]
    parts = [part for part in raw_parts if part]

    if not parts:
        return {"subtitles": [], "rhythm": [], "guard": {"changed": False, "actions": []}}

    subtitles: list[str] = []
    rhythm: list[dict] = []
    for index, part in enumerate(parts):
        subtitles.append(part)
        rhythm.append({"text": part, "pause_type": "none", "duration": 2.2, "reason": "原句切分"})
        pause_type = "ending_silence" if index == len(parts) - 1 else "heavy_pause"
        duration = 1.5 if pause_type == "ending_silence" else 1.1
        subtitles.append("...")
        rhythm.append({"text": "...", "pause_type": pause_type, "duration": duration, "reason": "留白"})

    return _guard_subtitle_plan({"subtitles": subtitles, "rhythm": rhythm}, reflection)


def _normalize_plan(result: dict) -> dict:
    subtitles = result.get("subtitles") or [item.get("text", "") for item in result.get("rhythm", [])]
    subtitles = [text for text in subtitles if isinstance(text, str) and text.strip()]
    rhythm = result.get("rhythm") or []
    normalized_rhythm = []
    for index, text in enumerate(subtitles):
        source = rhythm[index] if index < len(rhythm) and isinstance(rhythm[index], dict) else {}
        if text == "...":
            pause_type = source.get("pause_type") or ("ending_silence" if index == len(subtitles) - 1 else "short_pause")
        else:
            pause_type = "none"
        duration = source.get("duration")
        if not isinstance(duration, (int, float)):
            if text == "...":
                duration = 1.5 if pause_type == "ending_silence" else 1.1
            else:
                duration = 2.2
        normalized_rhythm.append(
            {
                "text": text,
                "pause_type": pause_type,
                "duration": float(duration),
                "reason": source.get("reason", ""),
            }
        )
    return {"subtitles": subtitles, "rhythm": normalized_rhythm}


def _split_text_and_pauses(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    normalized = text.replace("……", "...").replace("…", "...")
    parts: list[str] = []
    cursor = 0
    for match in PAUSE_RE.finditer(normalized):
        before = normalized[cursor : match.start()].strip()
        if before:
            parts.append(_ensure_sentence(before))
        parts.append("...")
        cursor = match.end()
    rest = normalized[cursor:].strip()
    if rest:
        parts.append(_ensure_sentence(rest))
    return parts


def _ensure_sentence(text: str) -> str:
    cleaned = TRAILING_PUNCTUATION_RE.sub("", text.strip())
    if not cleaned:
        return ""
    return cleaned + "。"


def _dedupe_key(text: str) -> str:
    return re.sub(r"[\s。！？!?；;，,.\-—_]+", "", text)


def _spoken_lines_from_plan(plan: dict) -> tuple[list[str], list[str]]:
    actions = []
    raw_subtitles = plan.get("subtitles") or []
    expanded: list[str] = []
    for item in raw_subtitles:
        if not isinstance(item, str):
            continue
        expanded.extend(_split_text_and_pauses(item))

    if expanded != raw_subtitles:
        actions.append("normalized_subtitle_text")

    spoken_lines = []
    seen = set()
    for item in expanded:
        if item == "...":
            continue
        key = _dedupe_key(item)
        if not key:
            continue
        if key in seen:
            actions.append("removed_duplicate_subtitle")
            continue
        seen.add(key)
        spoken_lines.append(item)

    if len(spoken_lines) > MAX_SPOKEN_LINES:
        spoken_lines = spoken_lines[:MAX_SPOKEN_LINES]
        actions.append("trimmed_to_max_spoken_lines")

    return spoken_lines, actions


def _rebuild_rhythm(spoken_lines: list[str]) -> dict:
    subtitles: list[str] = []
    rhythm: list[dict] = []
    for index, line in enumerate(spoken_lines):
        subtitles.append(line)
        rhythm.append(
            {
                "text": line,
                "pause_type": "none",
                "duration": 2.4 if index == len(spoken_lines) - 1 else 2.1,
                "reason": "guarded spoken line",
            }
        )

        pause_type = "ending_silence" if index == len(spoken_lines) - 1 else ("short_pause" if index == 0 else "heavy_pause")
        duration = {"short_pause": 0.85, "heavy_pause": 1.2, "ending_silence": 1.6}[pause_type]
        subtitles.append("...")
        rhythm.append(
            {
                "text": "...",
                "pause_type": pause_type,
                "duration": duration,
                "reason": "guarded pause",
            }
        )
    return {"subtitles": subtitles, "rhythm": rhythm}


def _fallback_from_source(source_text: str) -> list[str]:
    raw_parts = [_clean_sentence(part) for part in PUNCTUATION_RE.split(source_text)]
    return [part for part in raw_parts if part][:MAX_SPOKEN_LINES]


def _guard_subtitle_plan(plan: dict, source_text: str) -> dict:
    spoken_lines, actions = _spoken_lines_from_plan(plan)
    if not spoken_lines:
        spoken_lines = _fallback_from_source(source_text)
        actions.append("fallback_to_source_text")

    guarded = _rebuild_rhythm(spoken_lines)
    if guarded.get("subtitles") != plan.get("subtitles"):
        actions.append("rebuilt_pause_sequence")

    unique_actions = []
    for action in actions:
        if action not in unique_actions:
            unique_actions.append(action)

    guarded["guard"] = {
        "changed": bool(unique_actions),
        "actions": unique_actions,
        "spoken_count": len(spoken_lines),
        "max_spoken_lines": MAX_SPOKEN_LINES,
    }
    return guarded


def build_subtitle_rhythm(reflection: str) -> list[str]:
    return build_subtitle_plan(reflection)["subtitles"]
