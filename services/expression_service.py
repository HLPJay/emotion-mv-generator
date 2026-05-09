from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "templates" / "voice_performance_profiles.json"

DEFAULT_PROFILE_ID = "ordinary_reflection"
PAREN_RE = re.compile(r"[（(]([^（）()]*)[）)]")
SEGMENT_RE = re.compile(r"([^。！？!?；;，,\n]+)([。！？!?；;，,\n]*)")

TURN_WORDS = ("但是", "可是", "而是", "却", "但", "后来", "原来", "其实")
CORE_WORDS = (
    "害怕",
    "怯弱",
    "回避",
    "恐慌",
    "迷茫",
    "缺少",
    "职业规划",
    "职业生涯",
    "执行力",
    "闭环",
    "一技之长",
    "产品定义",
    "心流",
    "答案",
    "时间",
    "坚持",
    "挑战",
)
EMPHASIS_WORDS = (
    "更害怕",
    "怯弱的自己",
    "职业规划",
    "职业生涯",
    "执行力",
    "闭环",
    "一技之长",
    "AI",
    "ai",
    "产品定义",
    "心流状态",
    "第一性原理",
    "认知",
    "习惯",
    "行动",
    "时间",
    "坚持",
    "挑战",
    "自己",
    "答案",
    "工具",
)


def _load_profiles() -> dict:
    if not PROFILE_PATH.exists():
        return {}
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8-sig"))


def _profile(profile_id: str = DEFAULT_PROFILE_ID) -> dict:
    profiles = _load_profiles()
    return profiles.get(profile_id) or profiles.get(DEFAULT_PROFILE_ID) or {}


def _segments(text: str, role: str) -> list[dict]:
    items = []
    for match in SEGMENT_RE.finditer(text):
        body = match.group(1).strip()
        if not body:
            continue
        punctuation = match.group(2).strip()
        if "\n" in punctuation:
            punctuation = "。"
        punctuation = punctuation[:1] if punctuation else "。"
        items.append({"text": body + punctuation, "role": role})
    return items


def _semantic_role(item: dict, index: int, total: int) -> str:
    text = item["text"]
    if item["role"] == "secondary":
        return "context_note"
    if item["role"] == "question" or text.endswith(("?", "？")):
        return "question"
    if index == total - 1:
        return "ending_echo"
    if any(word in text for word in CORE_WORDS):
        return "core_admission"
    if any(word in text for word in TURN_WORDS):
        return "turn"
    return "setup" if index == 0 else "turn"


def _role_from_text(text: str, fallback: str) -> str:
    if text.endswith(("?", "？")):
        return "question"
    return fallback


def _emphasis_words(text: str, semantic_role: str) -> list[str]:
    words = []
    for word in EMPHASIS_WORDS:
        if word in text and word not in words:
            words.append(word)
        if len(words) >= (3 if semantic_role == "core_admission" else 2):
            break
    if not words:
        cleaned = text.strip("。！？!?；;，, ")
        if len(cleaned) >= 4 and semantic_role in {"core_admission", "ending_echo"}:
            words.append(cleaned[-min(6, len(cleaned)) :])
    return words


def _spoken_text(text: str, semantic_role: str, role: str) -> str:
    spoken = text.strip()
    spoken = spoken.replace("相比于", "相比")
    spoken = spoken.replace("永远是", "总是")
    if semantic_role == "core_admission":
        spoken = spoken.replace("我一直更害怕的是", "我一直更害怕的，其实是")
        spoken = spoken.replace("缺少的不是", "缺少的，可能不是")
    if role == "secondary":
        spoken = spoken.replace("只有自己最懂自己", "可能也只有自己知道")
        spoken = spoken.replace("越害怕越回避", "越害怕，就越会回避")
    return spoken


def _unit_timing(unit: dict, profile: dict) -> dict:
    semantic = unit["semantic_role"]
    role_config = (profile.get("semantic_roles") or {}).get(semantic, {})
    voices = profile.get("voices") or {}
    voice_layer = role_config.get("voice_layer") or {
        "primary": "main",
        "secondary": "inner",
        "question": "direct",
    }.get(unit["role"], "main")
    voice = voices.get(voice_layer, {})
    base_speed = float(voice.get("speed", 0.84))
    intensity = float(role_config.get("intensity", 0.4))
    speed = round(max(0.72, min(0.94, base_speed - max(0, intensity - 0.45) * 0.08)), 2)
    return {
        "voice_layer": voice_layer,
        "speed": speed,
        "pitch": int(voice.get("pitch", -1)),
        "volume": float(voice.get("volume", 1.0)),
        "emotion": voice.get("emotion", "neutral"),
        "pause_after": float(role_config.get("pause_after", 0.9)),
        "intensity": intensity,
        "breath_before": bool(role_config.get("breath_before", False)),
        "camera_intent": role_config.get("camera_intent", "slow_push"),
    }


def _parenthetical_meta(input_structure: dict | None) -> dict:
    if not input_structure or not input_structure.get("has_parenthetical"):
        return {}
    return {
        "parenthetical_relationship": input_structure.get("relationship"),
        "parenthetical_theme": input_structure.get("parenthetical_theme"),
        "parenthetical_usage": input_structure.get("usage", {}),
        "emotional_shift": input_structure.get("emotional_shift", {}),
        "visual_transition": input_structure.get("visual_transition", {}),
    }


def _build_units(reflection: str, profile: dict, input_structure: dict | None = None) -> list[dict]:
    raw_items = []
    cursor = 0
    for match in PAREN_RE.finditer(reflection):
        before = reflection[cursor : match.start()]
        raw_items.extend(_segments(before, "primary"))
        context = match.group(1).strip()
        if context:
            raw_items.extend(_segments(context, "secondary"))
        cursor = match.end()
    raw_items.extend(_segments(reflection[cursor:], "primary"))

    normalized = []
    for item in raw_items:
        role = _role_from_text(item["text"], item["role"])
        normalized.append({"text": item["text"], "role": role})

    units = []
    total = len(normalized)
    for index, item in enumerate(normalized):
        semantic = _semantic_role(item, index, total)
        timing = _unit_timing({"role": item["role"], "semantic_role": semantic}, profile)
        unit_data = {
                "id": f"unit_{index + 1:02d}",
                "role": item["role"],
                "semantic_role": semantic,
                "subtitle_text": item["text"],
                "spoken_text": _spoken_text(item["text"], semantic, item["role"]),
                "subtitle_style": item["role"],
                "emphasis_words": _emphasis_words(item["text"], semantic),
                **timing,
            }
        if item["role"] == "secondary":
            unit_data.update(_parenthetical_meta(input_structure))
        if item["role"] == "question":
            unit_data["question_analysis"] = (input_structure or {}).get("question_analysis", {})
        units.append(unit_data)
    return units


def build_expression_plan(
    reflection: str,
    emotion: dict | None = None,
    profile_id: str = DEFAULT_PROFILE_ID,
    input_structure: dict | None = None,
) -> dict:
    profile = _profile(profile_id)
    units = _build_units(reflection, profile, input_structure)
    return {
        "profile_id": profile_id,
        "profile_label": profile.get("label", profile_id),
        "description": profile.get("description", ""),
        "emotion": {
            "emotion": (emotion or {}).get("emotion"),
            "mood": (emotion or {}).get("mood"),
            "tone": (emotion or {}).get("tone"),
        },
        "input_structure": input_structure or {},
        "units": units,
        "controls": {
            "meaning_preservation": "strict",
            "rewrite_level": "low",
            "principle": "AI changes delivery, not the user's core thought.",
        },
    }


def subtitles_from_expression(expression_plan: dict) -> list[str]:
    subtitles = []
    units = expression_plan.get("units", [])
    for index, unit in enumerate(units):
        subtitles.append(unit["subtitle_text"])
        subtitles.append("...")
    return subtitles
