from __future__ import annotations

import re

from services.llm_service import chat_json, llm_enabled


PUNCTUATION_RE = re.compile(r"[。！？!?；;，,\n]+")
PAUSE_RE = re.compile(r"(\.{3,}|…+)")
TRAILING_PUNCTUATION_RE = re.compile(r"[。！？!?；;，,.\s]+$")
PAREN_RE = re.compile(r"[（(]([^（）()]*)[）)]")
MAX_SPOKEN_LINES = 4
MAX_CONTEXT_LINES = 2
MIN_LINE_CHARS = 6
FRAGMENT_PREFIXES = ("只是", "因为", "所以", "但是", "可是", "而是", "就", "却", "也", "还")
FRAGMENT_EXACT = {"只是", "只是每次", "就已经", "因为", "所以", "但是", "可是", "而是"}


def _clean_sentence(sentence: str) -> str:
    sentence = sentence.strip(" \t\r\n。！？!?；;，,")
    if not sentence:
        return ""
    return sentence + "。"


def _split_reflection_context(reflection: str) -> tuple[str, list[str]]:
    contexts = [match.group(1).strip() for match in PAREN_RE.finditer(reflection) if match.group(1).strip()]
    main = PAREN_RE.sub("", reflection).strip()
    return main, contexts


def _ensure_punctuation(text: str, punctuation: str = "。") -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    if cleaned[-1] in "。！？!?；;，,":
        return cleaned
    return cleaned + punctuation


def _source_lines_with_roles(source_text: str) -> list[dict]:
    main, contexts = _split_reflection_context(source_text)
    lines: list[dict] = []

    def add_segments(text: str, role: str, limit: int) -> None:
        parts = re.split(r"([。！？!?；;，,\n]+)", text)
        added = 0
        for index in range(0, len(parts), 2):
            body = parts[index].strip()
            if not body:
                continue
            punctuation = parts[index + 1].strip() if index + 1 < len(parts) else ""
            if "\n" in punctuation:
                punctuation = "。"
            punctuation = punctuation[:1] if punctuation else "。"
            lines.append({"text": _ensure_punctuation(body, punctuation), "role": role})
            added += 1
            if added >= limit:
                break

    add_segments(main, "primary", MAX_SPOKEN_LINES)
    for context in contexts[:MAX_CONTEXT_LINES]:
        add_segments(context, "secondary", MAX_CONTEXT_LINES)
    return lines


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


def build_subtitle_plan_from_expression(expression_plan: dict) -> dict:
    subtitles: list[str] = []
    rhythm: list[dict] = []
    units = expression_plan.get("units", [])
    for index, unit in enumerate(units):
        text = unit.get("subtitle_text", "").strip()
        if not text:
            continue
        role = unit.get("role", "primary")
        semantic_role = unit.get("semantic_role", "setup")
        subtitles.append(text)
        rhythm.append(
            {
                "text": text,
                "role": role,
                "semantic_role": semantic_role,
                "pause_type": "none",
                "duration": 2.15 if role == "secondary" else 2.3,
                "reason": f"expression:{semantic_role}",
                "unit_id": unit.get("id"),
                "spoken_text": unit.get("spoken_text", text),
                "emphasis_words": unit.get("emphasis_words", []),
                "voice_layer": unit.get("voice_layer", "main"),
                "speed": unit.get("speed"),
                "pitch": unit.get("pitch"),
                "volume": unit.get("volume"),
                "emotion": unit.get("emotion"),
                "breath_before": unit.get("breath_before", False),
            }
        )
        pause_type = "ending_silence" if index == len(units) - 1 else ("short_pause" if role == "secondary" else "heavy_pause")
        pause_after = float(unit.get("pause_after", 1.0))
        subtitles.append("...")
        rhythm.append(
            {
                "text": "...",
                "role": role,
                "semantic_role": semantic_role,
                "pause_type": pause_type,
                "duration": 1.6 if pause_type == "ending_silence" else pause_after,
                "reason": f"expression_pause:{semantic_role}",
                "unit_id": unit.get("id"),
            }
        )
    return {
        "subtitles": subtitles,
        "rhythm": rhythm,
        "guard": {
            "changed": False,
            "actions": ["built_from_expression_plan"],
            "spoken_count": len(units),
            "max_spoken_lines": None,
            "note": "expression_plan controls line count; legacy Subtitle Guard limit is bypassed here",
            "roles": {"primary": "main reflection", "secondary": "parenthetical context", "question": "direct question"},
        },
    }


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

    merged_lines, merge_actions = _merge_fragments(spoken_lines)
    actions.extend(merge_actions)
    return merged_lines, actions


def _line_key_text(text: str) -> str:
    return _dedupe_key(text)


def _is_fragment(text: str) -> bool:
    key = _line_key_text(text)
    if key in FRAGMENT_EXACT:
        return True
    if len(key) < MIN_LINE_CHARS:
        return True
    return any(key.startswith(prefix) and len(key) <= 6 for prefix in FRAGMENT_PREFIXES)


def _merge_fragments(lines: list[str]) -> tuple[list[str], list[str]]:
    if not lines:
        return lines, []

    actions = []
    merged: list[str] = []
    index = 0
    while index < len(lines):
        current = lines[index]
        if _is_fragment(current) and index + 1 < len(lines):
            combined = _ensure_sentence(TRAILING_PUNCTUATION_RE.sub("", current) + TRAILING_PUNCTUATION_RE.sub("", lines[index + 1]))
            merged.append(combined)
            actions.append("merged_semantic_fragment")
            index += 2
            continue
        if _is_fragment(current) and merged:
            previous = TRAILING_PUNCTUATION_RE.sub("", merged[-1])
            merged[-1] = _ensure_sentence(previous + TRAILING_PUNCTUATION_RE.sub("", current))
            actions.append("merged_semantic_fragment")
            index += 1
            continue
        merged.append(current)
        index += 1

    if len(merged) > MAX_SPOKEN_LINES:
        merged = merged[:MAX_SPOKEN_LINES]
        actions.append("trimmed_to_max_spoken_lines")
    return merged, actions


def _normalize_spoken_items(spoken_lines: list[str] | list[dict]) -> list[dict]:
    items = []
    for line in spoken_lines:
        if isinstance(line, dict):
            text = line.get("text", "").strip()
            role = line.get("role", "primary")
        else:
            text = str(line).strip()
            role = "primary"
        if text:
            items.append({"text": text, "role": role if role in {"primary", "secondary"} else "primary"})
    return items


def _rebuild_rhythm(spoken_lines: list[str] | list[dict]) -> dict:
    spoken_items = _normalize_spoken_items(spoken_lines)
    subtitles: list[str] = []
    rhythm: list[dict] = []
    for index, item in enumerate(spoken_items):
        line = item["text"]
        role = item["role"]
        subtitles.append(line)
        rhythm.append(
            {
                "text": line,
                "role": role,
                "pause_type": "none",
                "duration": 2.15 if role == "secondary" else (2.4 if index == len(spoken_items) - 1 else 2.1),
                "reason": "context note" if role == "secondary" else "guarded spoken line",
            }
        )

        pause_type = "ending_silence" if index == len(spoken_items) - 1 else ("short_pause" if role == "secondary" else ("short_pause" if index == 0 else "heavy_pause"))
        duration = {"short_pause": 0.85, "heavy_pause": 1.2, "ending_silence": 1.6}[pause_type]
        subtitles.append("...")
        rhythm.append(
            {
                "text": "...",
                "role": role,
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
    source_items = _source_lines_with_roles(source_text)
    if source_items:
        source_texts = [item["text"] for item in source_items]
        if source_texts != spoken_lines:
            actions.append("preserved_source_punctuation")
        if any(item["role"] == "secondary" for item in source_items):
            actions.append("marked_parenthetical_context")
        spoken_lines = source_items
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
        "spoken_count": len(_normalize_spoken_items(spoken_lines)),
        "max_spoken_lines": MAX_SPOKEN_LINES,
        "roles": {"primary": "main reflection", "secondary": "parenthetical context"},
    }
    return guarded


def build_subtitle_rhythm(reflection: str) -> list[str]:
    return build_subtitle_plan(reflection)["subtitles"]
