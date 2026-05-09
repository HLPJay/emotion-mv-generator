from __future__ import annotations

import re

from services.llm_service import chat_json, llm_enabled
from services.text_utils import normalize


PAREN_RE = re.compile(r"[（(]([^（）()]*)[）)]")
QUESTION_MARKERS = ("？", "?", "难道", "岂不是", "真的", "到底", "何尝", "不是吗", "不也是")
RELATIONSHIP_VALUES = {"none", "explain", "deepen", "contrast", "reveal", "challenge", "resolve", "echo"}


def _split_parenthetical(text: str) -> tuple[str, str, bool]:
    parts = [normalize(match.group(1)) for match in PAREN_RE.finditer(text) if normalize(match.group(1))]
    main = normalize(PAREN_RE.sub("", text))
    return main, " ".join(parts), bool(parts)


def _has_question(text: str) -> bool:
    return any(marker in text for marker in QUESTION_MARKERS)


def _relationship_by_rule(main_text: str, parenthetical_text: str) -> str:
    if not parenthetical_text:
        return "none"
    if any(word in parenthetical_text for word in ("其实", "不是", "而是", "却", "反而")):
        return "contrast"
    if any(word in parenthetical_text for word in ("为什么", "到底", "难道", "真的", "吗", "？", "?")):
        return "challenge"
    if any(word in parenthetical_text for word in ("因为", "只是", "也就是", "意味着")):
        return "explain"
    if any(word in parenthetical_text for word in ("需要", "行动", "开始", "做到", "习惯", "沉淀", "解决")):
        return "resolve" if any(word in parenthetical_text for word in ("行动", "开始", "做到", "解决")) else "deepen"
    if any(word in parenthetical_text for word in ("原来", "真正", "最", "答案")):
        return "reveal"
    if len(parenthetical_text) <= 14:
        return "echo"
    return "deepen"


def _usage_for_relationship(relationship: str) -> dict:
    if relationship == "none":
        return {
            "emotion": "main_only",
            "subtitle": "main_only",
            "voice": "same_voice_lower_volume_closer",
            "narrative": "main_linear_arc",
            "image_prompt": "keep_same_world_add_inner_detail",
            "pause_before_parenthetical": "none",
        }
    heavy_pause = relationship in {"contrast", "reveal", "challenge", "resolve"}
    return {
        "emotion": "main_and_parenthetical",
        "subtitle": "include_as_secondary" if relationship != "none" else "main_only",
        "voice": "same_voice_lower_volume_closer" if relationship != "challenge" else "same_voice_slightly_direct_question",
        "narrative": "parenthetical_as_turning_layer" if heavy_pause else "parenthetical_as_inner_layer",
        "image_prompt": "avoid_repeating_main_pressure" if relationship in {"deepen", "contrast", "resolve"} else "keep_same_world_add_inner_detail",
        "pause_before_parenthetical": "heavy_pause" if heavy_pause else "short_pause",
    }


def _fallback_analysis(reflection: str) -> dict:
    main_text, parenthetical_text, has_parenthetical = _split_parenthetical(reflection)
    relationship = _relationship_by_rule(main_text, parenthetical_text)
    has_question = _has_question(reflection)
    return {
        "raw_text": reflection,
        "main_text": main_text or reflection,
        "parenthetical_text": parenthetical_text,
        "has_parenthetical": has_parenthetical,
        "main_theme": main_text or reflection,
        "parenthetical_theme": parenthetical_text,
        "relationship": relationship,
        "relationship_reason": "rule_based_default" if has_parenthetical else "",
        "emotional_shift": {
            "from": "主句情绪",
            "to": "括号带来的第二层含义" if has_parenthetical else "无",
            "intensity": "medium" if has_parenthetical else "none",
        },
        "visual_transition": {
            "from": "主句对应的核心处境",
            "to": "括号对应的补充、反转或行动方向" if has_parenthetical else "无",
            "transition_point": "parenthetical_start" if has_parenthetical else "none",
        },
        "usage": _usage_for_relationship(relationship),
        "question_analysis": {
            "has_question": has_question,
            "question_scope": "parenthetical" if has_question and parenthetical_text and _has_question(parenthetical_text) else ("main" if has_question else "none"),
            "rhetorical_likelihood": "medium" if has_question else "none",
            "strategy_hint": "keep_as_question_role_without_changing_parenthetical_relationship" if has_question else "",
        },
        "source": "rule",
    }


def _normalize_analysis(result: dict, fallback: dict) -> dict:
    if not isinstance(result, dict):
        return fallback
    normalized = dict(fallback)
    for key in (
        "main_theme",
        "parenthetical_theme",
        "relationship",
        "relationship_reason",
        "subtitle_strategy",
        "voice_strategy",
        "narrative_strategy",
    ):
        if result.get(key):
            normalized[key] = result[key]
    if normalized.get("relationship") not in RELATIONSHIP_VALUES:
        normalized["relationship"] = fallback["relationship"]
    for key in ("emotional_shift", "visual_transition", "usage", "question_analysis"):
        value = result.get(key)
        if isinstance(value, dict):
            merged = dict(normalized.get(key, {}))
            merged.update({item_key: item_value for item_key, item_value in value.items() if item_value not in (None, "")})
            normalized[key] = merged
    normalized["source"] = "llm"
    return normalized


def analyze_input_structure(reflection: str, *, use_llm: bool | None = None) -> dict:
    fallback = _fallback_analysis(reflection)
    effective_llm = llm_enabled() if use_llm is None else use_llm
    if not effective_llm or (not fallback["has_parenthetical"] and not fallback["question_analysis"]["has_question"]):
        return fallback

    system_prompt = """
你是输入结构分析器，负责分析主句、括号和反问结构。
只做结构理解，不生成文案，不扩展观点。
关系只能从以下值中选择：
none / explain / deepen / contrast / reveal / challenge / resolve / echo
只输出 JSON。
"""
    user_prompt = f"""
用户原句：
{reflection}

规则兜底结果：
{fallback}

请输出完整 JSON：
{{
  "main_theme": "主句核心含义",
  "parenthetical_theme": "括号核心含义，没有括号则为空",
  "relationship": "none/explain/deepen/contrast/reveal/challenge/resolve/echo",
  "relationship_reason": "为什么是这个关系",
  "emotional_shift": {{
    "from": "主句情绪起点",
    "to": "括号带来的情绪或意义方向",
    "intensity": "none/low/medium/high"
  }},
  "visual_transition": {{
    "from": "前半段视觉方向",
    "to": "后半段视觉方向",
    "transition_point": "none/parenthetical_start/question_start/ending"
  }},
  "usage": {{
    "emotion": "main_only/main_and_parenthetical",
    "subtitle": "main_only/include_as_secondary/ending_echo",
    "voice": "same_voice_lower_volume_closer/same_voice_slightly_direct_question",
    "narrative": "parenthetical_as_inner_layer/parenthetical_as_turning_layer/question_as_suspension",
    "image_prompt": "keep_same_world_add_inner_detail/avoid_repeating_main_pressure",
    "pause_before_parenthetical": "short_pause/heavy_pause"
  }},
  "question_analysis": {{
    "has_question": true,
    "question_scope": "none/main/parenthetical/both",
    "rhetorical_likelihood": "none/low/medium/high",
    "strategy_hint": "对后续提问环节的影响"
  }}
}}
"""
    result = chat_json(system_prompt, user_prompt, temperature=0.25)
    return _normalize_analysis(result, fallback)
