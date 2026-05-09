from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "templates" / "visual_poetic_worlds.json"
RANDOM_WORLD_ID = "random"


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {"archetypes": {}, "worlds": {}}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))


def _score_item(text: str, item: dict) -> int:
    score = 0
    for keyword in item.get("keywords", []):
        if keyword and keyword in text:
            score += 3 if len(keyword) > 1 else 1
    return score


def _stable_pick(items: dict, text: str) -> tuple[str, dict]:
    keys = sorted(items)
    if not keys:
        return "", {}
    digest = hashlib.sha1(text.encode("utf-8")).digest()
    key = keys[digest[0] % len(keys)]
    return key, items[key]


def _stable_pick_scored(scored: list[tuple[str, dict, int]], text: str) -> tuple[str, dict, int]:
    if not scored:
        return "", {}, 0
    digest = hashlib.sha1(text.encode("utf-8")).digest()
    return scored[digest[0] % len(scored)]


def _select_scored(items: dict, text: str, *, best_fit_random: bool = True) -> tuple[str, dict, int]:
    scored = [(item_id, item, _score_item(text, item)) for item_id, item in items.items()]
    scored.sort(key=lambda row: (-row[2], row[0]))
    if scored and scored[0][2] > 0:
        if not best_fit_random:
            return scored[0]
        top_score = scored[0][2]
        best_candidates = [row for row in scored if row[2] == top_score]
        return _stable_pick_scored(best_candidates, text)
    picked_id, picked = _stable_pick(items, text)
    return picked_id, picked, 0


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword and keyword in text for keyword in keywords)


def _count_matches(text: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword and keyword in text)




def _is_metaphor_only(text, scene_tokens):
    """检测场景词是否只出现在比喻句中，没有真实场景描写"""
    mp = ["像", "仿佛", "如同", "犹如", "像是", "就像", "好似", "好比", "宛如"]
    if not scene_tokens:
        return False
    for token in scene_tokens:
        if not token or token not in text:
            continue
        in_met = False
        for p in mp:
            c = p + token
            if c in text:
                in_met = True
                r = text.replace(c, "")
                if token in r:
                    return False
                break
        if not in_met:
            return False
    return True


def _score_world_item(text: str, world_id: str, world: dict) -> tuple[int, list[str]]:
    score = _score_item(text, world)
    reasons: list[str] = []

    productivity_tokens = [
        "习惯",
        "沉淀",
        "行动",
        "执行",
        "待办",
        "遗留",
        "闭环",
        "笔记",
        "电脑",
        "草稿",
        "发布",
        "完成",
    ]
    cognition_to_action_tokens = ["认知", "蜕变", "优秀", "力竭", "对齐"]
    explicit_train_tokens = ["火车", "列车", "车窗", "站台", "车票", "铁轨", "行李", "旅途", "远行"]
    explicit_ocean_tokens = ["海", "海边", "大海", "海岸", "潮水", "潮线", "浪", "沙滩"]
    explicit_cosmos_tokens = ["宇宙", "星空", "星辰", "旷野", "第一性原理", "大千世界"]
    explicit_mountain_tokens = ["山", "山路", "晨雾", "登山", "山顶", "脚步", "远方"]
    explicit_rural_tokens = ["农村", "乡村", "院子", "土路", "父母", "家人", "亲情", "老家"]
    explicit_city_tokens = ["城市", "地铁", "路口", "通勤", "公司", "岗位", "面试", "职业"]
    ordinary_inner_tokens = ["自己", "生活", "普通", "害怕", "回避", "孤独", "房间", "门口"]

    explicit_scene_hits = {
        "train_journey": _count_matches(text, explicit_train_tokens),
        "ocean_shore": _count_matches(text, explicit_ocean_tokens),
        "star_cosmos": _count_matches(text, explicit_cosmos_tokens),
        "mountain_path": _count_matches(text, explicit_mountain_tokens),
        "rural_family": _count_matches(text, explicit_rural_tokens),
        "city_daylight": _count_matches(text, explicit_city_tokens),
        "ordinary_life": _count_matches(text, ordinary_inner_tokens),
    }
    max_explicit_hits = max(explicit_scene_hits.values() or [0])

    if world_id in explicit_scene_hits and explicit_scene_hits[world_id] > 0:
        # 检查场景词是否只出现在比喻句（像/仿佛/如同）中
        scene_tokens_map = {
            "train_journey": explicit_train_tokens,
            "ocean_shore": explicit_ocean_tokens,
            "star_cosmos": explicit_cosmos_tokens,
            "mountain_path": explicit_mountain_tokens,
            "rural_family": explicit_rural_tokens,
            "city_daylight": explicit_city_tokens,
            "ordinary_life": ordinary_inner_tokens,
        }
        matched_tokens = [t for t in scene_tokens_map.get(world_id, []) if t and t in text]
        if _is_metaphor_only(text, matched_tokens):
            # 只加一半分数，标记为隐喻场景
            boost = max(3, (7 + explicit_scene_hits[world_id] * 2) // 2)
            score += boost
            reasons.append(f"metaphor_scene_cue:+{boost}")
        else:
            boost = 7 + explicit_scene_hits[world_id] * 2
            score += boost
            reasons.append(f"explicit_scene_cue:+{boost}")

    if world_id == "workspace_reality":
        if _contains_any(text, productivity_tokens):
            score += 6
            reasons.append("productivity_or_habit_theme")
        if _contains_any(text, cognition_to_action_tokens) and _contains_any(text, productivity_tokens):
            score += 4
            reasons.append("cognition_to_action_theme")
    elif world_id == "ordinary_life":
        if _contains_any(text, ["习惯", "沉淀", "生活", "自己", "回避"]):
            score += 2
            reasons.append("daily_life_or_habit_theme")
        if max_explicit_hits >= 2 and explicit_scene_hits["ordinary_life"] == 0:
            score = max(0, score - 3)
            reasons.append("explicit_scene_elsewhere_penalty")
    elif world_id == "mountain_path":
        if _contains_any(text, ["挑战", "坚持", "目标", "突破", "向外", "跨出", "第一步"]):
            score += 4
            reasons.append("challenge_or_threshold_theme")
        if _contains_any(text, productivity_tokens) and not _contains_any(text, explicit_mountain_tokens):
            score = max(0, score - 4)
            reasons.append("productivity_theme_without_mountain_cue_penalty")
    elif world_id == "ocean_shore":
        if _contains_any(text, ["开阔", "世界", "答案", "孤独"]) and _contains_any(text, explicit_ocean_tokens):
            score += 4
            reasons.append("ocean_openness_theme")
        elif score > 0 and not _contains_any(text, explicit_ocean_tokens):
            score = max(0, score - 3)
            reasons.append("ocean_requires_clear_ocean_cue")
    elif world_id == "star_cosmos":
        if _contains_any(text, ["认知", "时代", "第一性原理", "世界"]) and _contains_any(text, explicit_cosmos_tokens):
            score += 4
            reasons.append("cosmos_cognition_theme")
        elif score > 0 and not _contains_any(text, explicit_cosmos_tokens):
            score = max(0, score - 3)
            reasons.append("cosmos_requires_clear_cosmos_cue")
    elif world_id == "rural_family":
        if _contains_any(text, explicit_rural_tokens):
            score += 4
            reasons.append("family_origin_theme")
        elif score > 0:
            score = max(0, score - 2)
            reasons.append("rural_requires_family_or_origin_cue")
    elif world_id == "city_daylight":
        if _contains_any(text, explicit_city_tokens):
            score += 4
            reasons.append("urban_career_theme")
    elif world_id == "train_journey":
        if _contains_any(text, explicit_train_tokens):
            score += 6
            reasons.append("explicit_train_or_travel_cue")
        elif score > 0:
            score = max(0, score - 4)
            reasons.append("generic_journey_cue_penalized_without_train_cue")

    return score, reasons


def _select_world_scored(worlds: dict, text: str) -> tuple[str, dict, int, list[dict]]:
    scored: list[tuple[str, dict, int, list[str]]] = []
    for world_id, world in worlds.items():
        score, reasons = _score_world_item(text, world_id, world)
        scored.append((world_id, world, score, reasons))
    scored.sort(key=lambda row: (-row[2], row[0]))

    selection_debug = [
        {"id": world_id, "label": world.get("label"), "score": score, "reasons": reasons}
        for world_id, world, score, reasons in scored
    ]
    if scored and scored[0][2] > 0:
        top_score = scored[0][2]
        
        # 负面约束：抽象世界没有 explicit_scene_cue 时，强制选择现实世界
        _ABSTRACT_WORLDS = {"star_cosmos", "ocean_shore", "train_journey", "mountain_path"}
        _REALITY_WORLDS = {"workspace_reality", "ordinary_life", "city_daylight", "rural_family"}
        
        top_id = scored[0][0]
        if top_id in _ABSTRACT_WORLDS:
            # 检查 Top 1 是否有 explicit scene cue
            top_reasons = scored[0][3]
            has_explicit = any("explicit_scene_cue" in r for r in top_reasons)
            if not has_explicit:
                # 找最高分的现实世界
                reality_candidates = [row for row in scored if row[0] in _REALITY_WORLDS and row[2] > 0]
                if reality_candidates:
                    # 如果现实世界与抽象世界分差不超过 5，强制选现实世界
                    reality_top = reality_candidates[0]
                    if top_score - reality_top[2] <= 5:
                        picked_id, picked, picked_score = reality_top[0], reality_top[1], reality_top[2]
                        # 在 selection_debug 中标记强制调整
                        for item in selection_debug:
                            if item["id"] == picked_id:
                                item.setdefault("reasons", []).append("reality_override:abstract_world_lacks_explicit_scene")
                            if item["id"] == top_id:
                                item.setdefault("reasons", []).append(f"overridden_by_reality:gap_{top_score - reality_top[2]}")
                        return picked_id, picked, picked_score, selection_debug

        best_candidates = [row for row in scored if row[2] == top_score]
        picked_id, picked, picked_score = _stable_pick_scored(
            [(world_id, world, score) for world_id, world, score, _ in best_candidates],
            text,
        )
        return picked_id, picked, picked_score, selection_debug

    picked_id, picked = _stable_pick(worlds, text)
    return picked_id, picked, 0, selection_debug


def _expression_text(expression_plan: dict | None) -> str:
    if not expression_plan:
        return ""
    parts = []
    for unit in expression_plan.get("units", []):
        parts.append(unit.get("subtitle_text", ""))
        parts.append(unit.get("spoken_text", ""))
        parts.extend(unit.get("emphasis_words", []))
    return " ".join(parts)


def _motif(archetype: dict, world: dict) -> dict:
    progression = world.get("progression", [])
    symbols = world.get("symbols", [])
    metaphor = f"{archetype.get('label', '反思')}在{world.get('label', '现实世界')}中展开：{world.get('texture', '')}"
    return {
        "visual_metaphor": metaphor,
        "recurring_symbols": symbols[:5],
        "progression": progression[:6],
        "avoid": [
            "unrelated random locations",
            "commercial poster look",
            "sci-fi robot unless the selected world requires cosmos symbolism",
            "pitch black depressed imagery",
            "text, subtitles, logos, watermarks",
            "different protagonist across shots",
        ],
    }


def build_visual_poetic_plan(
    reflection: str,
    expression_plan: dict | None = None,
    emotion: dict | None = None,
    preferred_world_id: str = "random",
    input_structure: dict | None = None,
) -> dict:
    config = _load_config()
    structure_text = json.dumps(input_structure or {}, ensure_ascii=False)
    text = " ".join([reflection, _expression_text(expression_plan), json.dumps(emotion or {}, ensure_ascii=False), structure_text])
    archetype_id, archetype, archetype_score = _select_scored(config.get("archetypes", {}), text)

    worlds = config.get("worlds", {})
    world_selection_debug = []
    if preferred_world_id != "random" and preferred_world_id in worlds:
        world_id, world, world_score = preferred_world_id, worlds[preferred_world_id], 99
        selection_mode = "manual_world_theme_archetype"
    else:
        world_id, world, world_score, world_selection_debug = _select_world_scored(worlds, text)
        selection_mode = "auto_theme_best_fit"

    motif = _motif(archetype, world)
    return {
        "archetype": {
            "id": archetype_id,
            "label": archetype.get("label"),
            "core_relation": archetype.get("core_relation"),
            "emotional_motion": archetype.get("emotional_motion"),
            "match_score": archetype_score,
        },
        "world": {
            "id": world_id,
            "label": world.get("label"),
            "texture": world.get("texture"),
            "match_score": world_score,
            "selection_mode": selection_mode,
            "selection_debug": world_selection_debug[:6],
        },
        "motif": motif,
        "input_structure": {
            "relationship": (input_structure or {}).get("relationship"),
            "main_theme": (input_structure or {}).get("main_theme"),
            "parenthetical_theme": (input_structure or {}).get("parenthetical_theme"),
            "visual_transition": (input_structure or {}).get("visual_transition"),
            "question_analysis": (input_structure or {}).get("question_analysis"),
        },
        "continuity_rules": [
            "one video must stay in one visual world",
            "repeat the same recurring symbols across shots",
            "keep the same protagonist and light logic",
            "every shot must serve the archetype relation and emotional motion",
        ],
    }


def visual_world_choices() -> list[tuple[str, str]]:
    config = _load_config()
    choices = [("自动：根据主题选择最适合", RANDOM_WORLD_ID)]
    for world_id, world in (config.get("worlds") or {}).items():
        choices.append((world.get("label", world_id), world_id))
    return choices


def visual_poetic_prompt(plan: dict | None) -> str:
    if not plan:
        return ""
    archetype = plan.get("archetype", {})
    world = plan.get("world", {})
    motif = plan.get("motif", {})
    return "\n".join(
        [
            f"Visual archetype: {archetype.get('label')} ({archetype.get('core_relation')}); {archetype.get('emotional_motion')}.",
            f"Visual world: {world.get('label')}; {world.get('texture')}.",
            f"Visual metaphor: {motif.get('visual_metaphor')}.",
            f"Recurring symbols: {', '.join(motif.get('recurring_symbols', []))}.",
            f"Progression: {' -> '.join(motif.get('progression', []))}.",
            f"Avoid: {', '.join(motif.get('avoid', []))}.",
        ]
    )
