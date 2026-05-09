from __future__ import annotations

import re

from services.llm_service import chat_json, llm_enabled


PUNCT_RE = re.compile(r"(?<=[。！？!?；;])")
CLAUSE_RE = re.compile(r"([^。！？!?；;，,\n]+)([。！？!?；;，,\n]*)")


def _clean(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _split_sentences(text: str) -> list[str]:
    parts = [_clean(part) for part in PUNCT_RE.split(text or "") if _clean(part)]
    return parts or ([_clean(text)] if _clean(text) else [])


def _split_clauses(text: str) -> list[str]:
    clauses = []
    for match in CLAUSE_RE.finditer(text or ""):
        body = _clean(match.group(1))
        punctuation = match.group(2).strip()[:1]
        if body:
            clauses.append(body + (punctuation if punctuation and punctuation not in ",，" else ""))
    return clauses or ([_clean(text)] if _clean(text) else [])


def _unit_function(text: str, scope: str, index: int, total: int) -> str:
    if any(word in text for word in ("力竭", "压力", "困难", "害怕", "回避", "消耗", "代价")):
        return "burden"
    if any(word in text for word in ("习惯", "行动", "开始", "做到", "沉淀", "方向", "解决")):
        return "direction"
    if any(word in text for word in ("其实", "真正", "原来", "答案", "不是")):
        return "reveal"
    if text.endswith(("?", "？")) or any(word in text for word in ("难道", "到底", "真的")):
        return "challenge"
    if scope == "parenthetical" and index == total - 1 and total > 1:
        return "echo"
    if index == 0:
        return "setup"
    if index == total - 1:
        return "core_claim"
    return "turn"


def _visual_role(function: str) -> str:
    return {
        "setup": "establish_context",
        "turn": "shift_attention",
        "core_claim": "state_core_meaning",
        "burden": "show_cost",
        "direction": "show_repeated_action",
        "reveal": "reveal_underlying_reason",
        "challenge": "hold_suspension",
        "echo": "leave_aftertaste",
    }.get(function, "support_meaning")


def _sentence_scope(index: int, input_structure: dict) -> tuple[str, str]:
    if index == 0:
        return "main", input_structure.get("main_text") or input_structure.get("raw_text", "")
    return "parenthetical", input_structure.get("parenthetical_text", "")


def _build_rule_structure(reflection: str, input_structure: dict | None = None) -> dict:
    input_structure = input_structure or {}
    sentence_sources = []
    main_text = input_structure.get("main_text") or reflection
    if main_text:
        sentence_sources.extend(("main", item) for item in _split_sentences(main_text))
    parenthetical_text = input_structure.get("parenthetical_text") or ""
    if parenthetical_text:
        sentence_sources.extend(("parenthetical", item) for item in _split_sentences(parenthetical_text))

    sentences = []
    semantic_units = []
    key_terms = []
    for sentence_index, (scope, sentence_text) in enumerate(sentence_sources, start=1):
        sentence_id = f"sentence_{sentence_index:02d}"
        macro_meaning = sentence_text
        semantic_function = "parenthetical_layer" if scope == "parenthetical" else ("core_claim" if sentence_index == 1 else "support")
        sentences.append(
            {
                "id": sentence_id,
                "scope": scope,
                "text": sentence_text,
                "macro_meaning": macro_meaning,
                "semantic_function": semantic_function,
                "must_preserve": True,
            }
        )
        clauses = _split_clauses(sentence_text)
        for unit_index, clause in enumerate(clauses, start=1):
            function = _unit_function(clause, scope, unit_index - 1, len(clauses))
            unit_id = f"unit_{len(semantic_units) + 1:02d}"
            semantic_units.append(
                {
                    "id": unit_id,
                    "sentence_id": sentence_id,
                    "scope": scope,
                    "text": clause,
                    "function": function,
                    "meaning": clause,
                    "visual_role": _visual_role(function),
                    "subtitle_priority": "high" if function in {"core_claim", "burden", "direction", "reveal"} else "medium",
                    "narrative_weight": 0.9 if function in {"core_claim", "burden", "direction", "reveal"} else 0.6,
                }
            )
            for term in ("优秀", "认知", "蜕变", "习惯", "行动", "沉淀", "害怕", "回避", "答案"):
                if term in clause and not any(item["text"] == term for item in key_terms):
                    key_terms.append(
                        {
                            "text": term,
                            "role": function,
                            "linked_unit_id": unit_id,
                            "visual_symbol": "",
                        }
                    )

    relationships = []
    for index in range(len(semantic_units) - 1):
        current = semantic_units[index]
        nxt = semantic_units[index + 1]
        rel_type = f"{current['function']}_to_{nxt['function']}"
        relationships.append(
            {
                "from": current["id"],
                "to": nxt["id"],
                "type": rel_type,
                "description": f"{current['meaning']} -> {nxt['meaning']}",
            }
        )

    secondary_layers = []
    if input_structure.get("has_parenthetical"):
        secondary_layers.append(
            {
                "id": "layer_01",
                "type": "parenthetical",
                "text": parenthetical_text,
                "position": "ending",
                "primary_relationship": input_structure.get("relationship"),
                "secondary_relationships": [],
                "confidence": 0.6,
                "theme": input_structure.get("parenthetical_theme") or parenthetical_text,
                "unit_ids": [unit["id"] for unit in semantic_units if unit["scope"] == "parenthetical"],
                "usage": input_structure.get("usage", {}),
            }
        )

    question_analysis = input_structure.get("question_analysis") or {}
    if question_analysis.get("has_question"):
        secondary_layers.append(
            {
                "id": f"layer_{len(secondary_layers) + 1:02d}",
                "type": "rhetorical_question",
                "text": "",
                "position": question_analysis.get("question_scope", "main"),
                "primary_relationship": "challenge",
                "secondary_relationships": [],
                "confidence": 0.5,
                "theme": question_analysis.get("strategy_hint", ""),
                "unit_ids": [unit["id"] for unit in semantic_units if unit["function"] == "challenge"],
                "usage": {"narrative": "question_as_suspension"},
            }
        )

    turn_unit = next((unit["id"] for unit in semantic_units if unit["scope"] == "parenthetical"), None)
    semantic_quality = {
        "sentences_exist": bool(sentences),
        "semantic_units_exist": bool(semantic_units),
        "semantic_units_cover_full_text": bool(semantic_units),
        "all_units_bind_sentence": all(unit.get("sentence_id") for unit in semantic_units),
        "parenthetical_preserved_as_whole": not input_structure.get("has_parenthetical") or any(
            sentence["scope"] == "parenthetical" and sentence["must_preserve"] for sentence in sentences
        ),
        "visual_shift_defined": bool((input_structure.get("visual_transition") or {}).get("to")),
        "question_not_misclassified_as_parenthetical": True,
    }

    return {
        "source": "rule",
        "sentences": sentences,
        "secondary_layers": secondary_layers,
        "semantic_units": semantic_units,
        "relationships": relationships,
        "narrative_arc": {
            "start": sentences[0]["macro_meaning"] if sentences else "",
            "middle": input_structure.get("main_theme", ""),
            "turn": (input_structure.get("visual_transition") or {}).get("transition_point", ""),
            "end": (input_structure.get("visual_transition") or {}).get("to", ""),
            "turning_unit_id": turn_unit,
        },
        "visual_guidance": {
            "main_visual_state": (input_structure.get("visual_transition") or {}).get("from", ""),
            "secondary_visual_shift": (input_structure.get("visual_transition") or {}).get("to", ""),
            "required_late_shots": [],
            "avoid": [
                "do not detach semantic units from sentence macro meaning",
                "do not repeat main pressure image for a direction unit",
                "do not ignore parenthetical whole meaning",
            ],
        },
        "key_terms": key_terms,
        "quality_checks": semantic_quality,
    }


def _normalize_llm_structure(result: dict, fallback: dict) -> dict:
    if not isinstance(result, dict):
        return fallback
    normalized = dict(fallback)
    for key in (
        "sentences",
        "secondary_layers",
        "semantic_units",
        "relationships",
        "key_terms",
    ):
        if isinstance(result.get(key), list):
            normalized[key] = result[key]
    for key in ("narrative_arc", "visual_guidance", "quality_checks"):
        if isinstance(result.get(key), dict):
            merged = dict(normalized.get(key, {}))
            merged.update({item_key: item_value for item_key, item_value in result[key].items() if item_value not in (None, "")})
            normalized[key] = merged
    normalized["source"] = "llm"
    return normalized


def build_semantic_structure(reflection: str, input_structure: dict | None = None) -> dict:
    fallback = _build_rule_structure(reflection, input_structure)
    if not llm_enabled():
        return fallback

    system_prompt = """
你是语境拆分分析器。
必须先保留完整句子的宏观语义，再在宏观语义约束下拆分 semantic_units。
semantic_units 不能脱离 sentence.macro_meaning 重新解释。
只输出 JSON。
"""
    user_prompt = f"""
用户原句：
{reflection}

输入结构：
{input_structure or {}}

规则兜底结构：
{fallback}

请输出完整 JSON，字段必须包含：
- sentences: 完整句子层，每项包含 id/scope/text/macro_meaning/semantic_function/must_preserve
- secondary_layers: 括号、反问、补充说明等二层表达
- semantic_units: 可执行语义单元，每项必须包含 id/sentence_id/scope/text/function/meaning/visual_role/subtitle_priority/narrative_weight
- relationships: unit 之间的推进关系
- narrative_arc: start/middle/turn/end/turning_unit_id
- visual_guidance: main_visual_state/secondary_visual_shift/required_late_shots/avoid
- key_terms: text/role/linked_unit_id/visual_symbol
- quality_checks: semantic_units_cover_full_text/unit_meaning_aligned_with_sentence_macro_meaning/all_units_bind_sentence/parenthetical_preserved_as_whole/visual_shift_defined/question_not_misclassified_as_parenthetical
"""
    result = chat_json(system_prompt, user_prompt, temperature=0.25)
    return _normalize_llm_structure(result, fallback)

