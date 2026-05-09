from __future__ import annotations

from services.llm_service import chat_json, llm_enabled


DEFAULT_FUNCTIONS = [
    {
        "function": "establish_state",
        "purpose": "建立当前处境和情绪背景",
        "camera_intent": "establishing",
    },
    {
        "function": "press_stagnation",
        "purpose": "加重停住、迟疑或堆积的感觉",
        "camera_intent": "close_detail",
    },
    {
        "function": "reveal_core_problem",
        "purpose": "揭示真正的内在问题",
        "camera_intent": "static_hold",
    },
    {
        "function": "turning_point",
        "purpose": "让括号、提问或自我提醒带来情绪转向",
        "camera_intent": "slow_push",
    },
    {
        "function": "first_action",
        "purpose": "给出一个小而具体的行动信号",
        "camera_intent": "action_detail",
    },
    {
        "function": "aftertaste",
        "purpose": "留下安静余味，不把情绪说满",
        "camera_intent": "static_hold",
    },
]


WORLD_INTENTS = {
    "workspace_reality": {
        "arc": "从遗留停滞到轻微行动",
        "strategy": "现实工作台里，从待办堆积、手停住，推进到第一次执行动作。",
        "visuals": [
            "桌面、笔记本、电脑屏幕和未完成待办，人物只以背影或手进入画面",
            "手停在键盘上，光标闪烁，没有输入",
            "待办列表和草稿叠在一起，屏幕光压住人物",
            "人从屏幕前轻轻抬头，光线略微变亮",
            "手指靠近发布按钮，或开始敲下第一个字",
            "屏幕光变亮，房间仍然安静，桌面不再显得混乱",
        ],
    },
    "ocean_shore": {
        "arc": "从孤独停留到面向开阔",
        "strategy": "海边远望里，用潮水、脚印、背影和天空变化表达从停住到迈步。",
        "visuals": [
            "淡蓝海边，一个孤独背影站在潮线内侧",
            "潮水靠近脚边，人物仍然没有移动",
            "脚印被海水冲淡，远处海面安静",
            "人物抬头看向海平线，天空稍微打开",
            "一只脚向前迈出，留下新的脚印",
            "远处天空变亮，海面留白，人物仍然很小",
        ],
    },
    "mountain_path": {
        "arc": "从路口迟疑到走向远方",
        "strategy": "山路远方里，用雾、脚步和远处光线表达开始行动。",
        "visuals": [
            "山路起点，一个背影停在路边",
            "雾挡住前路，脚步停在泥土上",
            "近景看见鞋底和未走出的路",
            "远处光线从雾里出现",
            "人物迈出一步，山路向前延伸",
            "路在远方打开，人物进入留白",
        ],
    },
    "city_daylight": {
        "arc": "从人群边缘到走向出口",
        "strategy": "城市白天里，用站台、路口和出口表达从旁观到进入行动。",
        "visuals": [
            "城市站台或路口，一个人站在人群边缘",
            "人群移动，主角仍然停着",
            "近景呈现手里的手机、草稿或未发送内容",
            "车门或路口灯光变化，人物开始抬头",
            "人物向出口或斑马线迈出一步",
            "城市远处变开阔，光线克制但明亮",
        ],
    },
    "ordinary_life": {
        "arc": "从室内停住到轻微打开",
        "strategy": "普通生活里，用门、窗光、桌面和背影表达从停顿到打开。",
        "visuals": [
            "安静房间，桌面和生活物件停在原处",
            "人物坐在光线边缘，动作停住",
            "近景呈现未完成的纸张、杯子或打开的门缝",
            "人物转向窗户或门，光线稍微变化",
            "手碰到门把手，或拿起桌上的东西",
            "门开一条缝，室内保持安静留白",
        ],
    },
}


def _spoken_units(expression_plan: dict | None) -> list[dict]:
    if not expression_plan:
        return []
    return [unit for unit in expression_plan.get("units", []) if unit.get("subtitle_text")]


def _semantic_units(semantic_structure: dict | None) -> list[dict]:
    return (semantic_structure or {}).get("semantic_units", []) or []


def _sentence_by_id(semantic_structure: dict | None) -> dict[str, dict]:
    return {
        sentence.get("id"): sentence
        for sentence in (semantic_structure or {}).get("sentences", [])
        if sentence.get("id")
    }


def _semantic_for_index(semantic_units: list[dict], index: int) -> dict:
    if not semantic_units:
        return {}
    return semantic_units[min(index, len(semantic_units) - 1)]


def _function_from_semantic(semantic_unit: dict, fallback: dict) -> dict:
    unit_function = semantic_unit.get("function")
    if unit_function == "burden":
        return DEFAULT_FUNCTIONS[1]
    if unit_function == "direction":
        return DEFAULT_FUNCTIONS[4]
    if unit_function == "reveal":
        return DEFAULT_FUNCTIONS[2]
    if unit_function == "challenge":
        return DEFAULT_FUNCTIONS[3]
    if unit_function == "echo":
        return DEFAULT_FUNCTIONS[5]
    if unit_function == "core_claim":
        return DEFAULT_FUNCTIONS[2]
    return fallback


def _world_id(visual_poetic_plan: dict | None) -> str:
    return str(((visual_poetic_plan or {}).get("world") or {}).get("id") or "ordinary_life")


def _function_for_index(index: int, total: int, role: str) -> dict:
    if total <= 1:
        return DEFAULT_FUNCTIONS[-1]
    if role == "secondary":
        return DEFAULT_FUNCTIONS[3 if index < total - 1 else 5]
    if index == 0:
        return DEFAULT_FUNCTIONS[0]
    if index == total - 1:
        return DEFAULT_FUNCTIONS[5]
    if total >= 5:
        mapped = min(index, len(DEFAULT_FUNCTIONS) - 2)
        return DEFAULT_FUNCTIONS[mapped]
    if index == 1:
        return DEFAULT_FUNCTIONS[1]
    return DEFAULT_FUNCTIONS[2]


def _fallback_narrative_plan(
    reflection: str,
    expression_plan: dict | None,
    visual_poetic_plan: dict | None,
    emotion: dict | None,
    input_structure: dict | None = None,
    semantic_structure: dict | None = None,
) -> dict:
    units = _spoken_units(expression_plan)
    semantic_units = _semantic_units(semantic_structure)
    sentences = _sentence_by_id(semantic_structure)
    world_id = _world_id(visual_poetic_plan)
    world = WORLD_INTENTS.get(world_id, WORLD_INTENTS["ordinary_life"])
    shots = []
    total = len(units)
    relationship = (input_structure or {}).get("relationship", "none")
    transition = (input_structure or {}).get("visual_transition", {})
    parenthetical_theme = (input_structure or {}).get("parenthetical_theme", "")
    question_analysis = (input_structure or {}).get("question_analysis", {})
    for index, unit in enumerate(units):
        role = unit.get("role", "primary")
        semantic_unit = _semantic_for_index(semantic_units, index)
        sentence = sentences.get(semantic_unit.get("sentence_id"), {})
        function = _function_for_index(index, total, role)
        function = _function_from_semantic(semantic_unit, function)
        visual = world["visuals"][min(index, len(world["visuals"]) - 1)]
        if semantic_unit:
            visual = (
                f"{visual}。语义单元：{semantic_unit.get('meaning', semantic_unit.get('text', ''))}。"
                f"完整句语义：{sentence.get('macro_meaning', '')}。"
                f"视觉职责：{semantic_unit.get('visual_role', '')}。"
            )
        if role == "secondary":
            target = transition.get("to") or parenthetical_theme or visual
            visual = f"括号层进入，关系是 {relationship}。不要重复前半段压力画面，转向：{target}。同一视觉世界中保留连续人物和光线。"
            if relationship in {"resolve", "deepen"}:
                function = DEFAULT_FUNCTIONS[4 if index < total - 1 else 5]
            elif relationship in {"contrast", "reveal", "challenge"}:
                function = DEFAULT_FUNCTIONS[3]
        if role == "question":
            visual = f"反问或自我追问进入，画面更静、更近，形成悬置感：{visual}"
            function = DEFAULT_FUNCTIONS[3]
        shots.append(
            {
                "unit_id": unit.get("id"),
                "subtitle_text": unit.get("subtitle_text"),
                "role": role,
                "function": function["function"],
                "purpose": function["purpose"],
                "emotion": unit.get("semantic_role") or (emotion or {}).get("emotion"),
                "visual_intent": visual,
                "camera_intent": function["camera_intent"],
                "generation_mode": "text_to_image",
                "parenthetical_relationship": relationship if role == "secondary" else "",
                "parenthetical_theme": parenthetical_theme if role == "secondary" else "",
                "question_strategy": question_analysis.get("strategy_hint", "") if role == "question" else "",
                "semantic_unit_id": semantic_unit.get("id", ""),
                "sentence_id": semantic_unit.get("sentence_id", ""),
                "sentence_macro_meaning": sentence.get("macro_meaning", ""),
                "unit_meaning": semantic_unit.get("meaning", ""),
                "visual_role": semantic_unit.get("visual_role", ""),
            }
        )
    return {
        "arc": world["arc"],
        "turning_point": transition.get("transition_point") or "括号内容、提问或核心承认进入时",
        "visual_strategy": f"{world['strategy']} 括号关系：{relationship}；后半段视觉转向：{transition.get('to', '')}",
        "principle": "每个镜头必须承担叙事任务，而不是只做关键词配图。",
        "source_text": reflection,
        "input_structure": input_structure or {},
        "semantic_structure_summary": {
            "sentence_count": len((semantic_structure or {}).get("sentences", [])),
            "unit_count": len(semantic_units),
            "narrative_arc": (semantic_structure or {}).get("narrative_arc", {}),
            "visual_guidance": (semantic_structure or {}).get("visual_guidance", {}),
        },
        "shots": shots,
    }


def _normalize_plan(plan: dict, fallback: dict) -> dict:
    if not isinstance(plan, dict):
        return fallback
    shots = plan.get("shots")
    if not isinstance(shots, list) or not shots:
        return fallback
    normalized = dict(fallback)
    normalized.update({key: value for key, value in plan.items() if key != "shots" and value})
    fallback_shots = fallback["shots"]
    normalized_shots = []
    for index, source in enumerate(shots):
        base = fallback_shots[min(index, len(fallback_shots) - 1)] if fallback_shots else {}
        item = dict(base)
        if isinstance(source, dict):
            item.update({key: value for key, value in source.items() if value not in (None, "")})
        normalized_shots.append(item)
    normalized["shots"] = normalized_shots[: len(fallback_shots)] if fallback_shots else normalized_shots
    return normalized


def build_narrative_plan(
    reflection: str,
    expression_plan: dict | None,
    visual_poetic_plan: dict | None,
    emotion: dict | None = None,
    input_structure: dict | None = None,
    semantic_structure: dict | None = None,
) -> dict:
    fallback = _fallback_narrative_plan(reflection, expression_plan, visual_poetic_plan, emotion, input_structure, semantic_structure)
    if not llm_enabled():
        return fallback

    system_prompt = """
你是情绪短视频的镜头叙事导演。
你的任务不是写分镜细节，而是给每个非暂停字幕分配叙事功能、情绪目的和视觉意图。
必须保持用户原意，不要新增观点，不要鸡汤化。
只输出 JSON。
"""
    user_prompt = f"""
用户原句：
{reflection}

表达计划：
{expression_plan or {}}

视觉意境计划：
{visual_poetic_plan or {}}

情绪：
{emotion or {}}

输入结构分析：
{input_structure or {}}

语境拆分结构：
{semantic_structure or {}}

请输出：
{{
  "arc": "整条视频的情绪弧线",
  "turning_point": "转折点",
  "visual_strategy": "总体视觉推进策略",
  "shots": [
    {{
      "unit_id": "对应 expression unit id",
      "subtitle_text": "对应字幕",
      "role": "primary/secondary/question",
      "function": "establish_state/press_stagnation/reveal_core_problem/turning_point/first_action/aftertaste",
      "purpose": "这一镜为什么存在",
      "emotion": "这一镜的具体情绪",
      "visual_intent": "这一镜应该怎么画",
      "camera_intent": "establishing/close_detail/static_hold/slow_push/action_detail",
      "generation_mode": "text_to_image",
      "parenthetical_relationship": "如果本镜来自括号层，填写括号和主句关系，否则为空",
      "parenthetical_theme": "如果本镜来自括号层，填写括号主题，否则为空",
      "question_strategy": "如果本镜来自反问/提问，填写悬置策略，否则为空",
      "semantic_unit_id": "绑定的 semantic unit id",
      "sentence_id": "绑定的完整句 id",
      "sentence_macro_meaning": "完整句宏观语义",
      "unit_meaning": "当前语义单元含义",
      "visual_role": "当前语义单元的视觉职责"
    }}
  ]
}}
"""
    try:
        result = chat_json(system_prompt, user_prompt, temperature=0.28)
    except Exception:
        return fallback
    return _normalize_plan(result, fallback)
