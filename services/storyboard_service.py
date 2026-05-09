from __future__ import annotations

from services.llm_service import chat_json, llm_enabled
from services.visual_continuity_service import visual_continuity_prompt
from services.visual_poetic_service import visual_poetic_prompt
from services.visual_style_service import visual_style_prompt


CAMERAS = ["slow push", "static shot", "slow pan", "gentle handheld", "slow zoom"]
LIGHTING = ["cold screen light", "dark room", "dim desk lamp", "window reflection", "blue gray night"]


SCENE_BANK = {
    "待办": "深夜房间里，一个人坐在电脑前，看着未完成的待办列表",
    "深夜电脑": "电脑屏幕发出冷光，手停在键盘上很久没有动作",
    "空房间": "空房间里只有一盏台灯，椅子被轻轻推开",
    "停滞的鼠标": "鼠标指针停在屏幕中央，页面像被时间按下暂停",
    "地铁站台": "清晨地铁站台，一个人站在人群边缘",
    "电脑文档": "空白文档打开着，光标一闪一闪",
    "城市窗户": "高楼窗边，城市灯光在玻璃上反射",
    "未发送邮件": "邮件草稿停在发送按钮前，迟迟没有按下",
    "空椅子": "桌边一把空椅子，房间安静得能听见电流声",
    "窗边": "窗边的人影低头站着，外面的路灯很远",
    "路灯": "夜色里的路灯照着湿润的人行道",
    "无人街道": "凌晨无人街道，便利店灯光还亮着",
    "暂停的时钟": "墙上的时钟停在一个普通却漫长的时刻",
    "未完成笔记": "摊开的笔记本上写到一半，笔尖停住",
    "散落纸张": "桌面散落着纸张，边角被风轻轻掀起",
    "关闭的门": "一扇关闭的门，门缝里透出微弱冷光",
    "镜子": "镜子前的人低头看着自己，表情被阴影遮住",
    "台灯": "台灯照着桌面，周围被夜色包围",
    "笔记本": "笔记本电脑旁放着没喝完的水，屏幕逐渐变暗",
    "清晨窗光": "清晨第一束窗光落进房间，灰尘缓慢漂浮",
}


def _expression_by_subtitle(expression_plan: dict | None) -> dict:
    mapping = {}
    if expression_plan:
        for unit in expression_plan.get("units", []):
            mapping[unit.get("subtitle_text")] = unit
    return mapping


def _blank_shot(subtitle: str, index: int, unit: dict | None = None) -> dict:
    unit = unit or {}
    is_pause = subtitle == "..."
    return {
        "scene": "画面留白，只有微弱光线和缓慢呼吸感" if is_pause else "安静的生活化反思镜头，人物在统一意境世界里短暂停住",
        "subtitle": subtitle,
        "subtitle_role": unit.get("role", "primary"),
        "semantic_role": unit.get("semantic_role", "pause" if is_pause else "setup"),
        "camera_intent": unit.get("camera_intent", ""),
        "camera": CAMERAS[index % len(CAMERAS)],
        "lighting": LIGHTING[index % len(LIGHTING)],
        "duration": 1.2 if is_pause else 2.4,
    }


def _normalize_storyboard(storyboard: list[dict], subtitles: list[str], expression_plan: dict | None = None) -> list[dict]:
    expression_map = _expression_by_subtitle(expression_plan)
    by_subtitle = {}
    for shot in storyboard:
        subtitle = shot.get("subtitle")
        if subtitle and subtitle != "..." and subtitle not in by_subtitle:
            by_subtitle[subtitle] = shot

    normalized = []
    previous_unit = {}
    for index, subtitle in enumerate(subtitles):
        unit = expression_map.get(subtitle, previous_unit if subtitle == "..." else {})
        if subtitle != "...":
            previous_unit = unit
        indexed = storyboard[index] if index < len(storyboard) and storyboard[index].get("subtitle") == subtitle else {}
        source = indexed or by_subtitle.get(subtitle) or {}
        shot = _blank_shot(subtitle, index, unit)
        shot.update({key: value for key, value in source.items() if value not in (None, "")})
        shot["subtitle"] = subtitle
        shot["subtitle_role"] = unit.get("role", shot.get("subtitle_role", "primary"))
        shot["semantic_role"] = unit.get("semantic_role", shot.get("semantic_role", "pause" if subtitle == "..." else "setup"))
        shot["camera_intent"] = unit.get("camera_intent", shot.get("camera_intent", ""))
        shot["duration"] = 1.2 if subtitle == "..." else float(shot.get("duration", 2.4))
        normalized.append(shot)
    return normalized


def _pause_scene(index: int, visual_poetic_plan: dict | None) -> str:
    world = (visual_poetic_plan or {}).get("world", {})
    motif = (visual_poetic_plan or {}).get("motif", {})
    world_id = world.get("id", "")
    symbols = motif.get("recurring_symbols", [])
    symbol_text = ", ".join(symbols[:3]) if symbols else "recurring symbols"
    pause_shots = {
        "ocean_shore": [
            "quiet pause shot: gentle tide slowly washes over a footprint near the shoreline, pale blue sea, small wind movement, no subtitle",
            "quiet pause shot: distant sea horizon and soft waves, the same lonely figure remains still in the lower frame, no subtitle",
        ],
        "mountain_path": [
            "quiet pause shot: morning mist drifts across a mountain path, one small footprint continues forward, no subtitle",
            "quiet pause shot: distant light opens behind the curve of the mountain road, same lone back view, no subtitle",
        ],
        "city_daylight": [
            "quiet pause shot: empty crosswalk after people pass, soft daylight reflected on the road, no subtitle",
            "quiet pause shot: subway door light and a still figure near the platform edge, no subtitle",
        ],
        "workspace_reality": [
            "quiet pause shot: cursor blinking on an unfinished draft, keyboard and screen glow breathing softly, no subtitle",
            "quiet pause shot: hand pauses near the publish button, room tone and screen light, no subtitle",
        ],
        "ordinary_life": [
            "quiet pause shot: window light moves slowly across a quiet room, everyday objects stay still, no subtitle",
            "quiet pause shot: a half-open door and soft daylight, the same protagonist pauses before moving, no subtitle",
        ],
        "rural_family": [
            "quiet pause shot: morning light falls on the courtyard gate, a bag rests near the threshold, no subtitle",
            "quiet pause shot: quiet dirt road leading away from home, warm but restrained light, no subtitle",
        ],
        "star_cosmos": [
            "quiet pause shot: tiny human silhouette under a vast star field, faint path light, no subtitle",
            "quiet pause shot: distant points of light slowly become clearer in the night sky, no subtitle",
        ],
        "train_journey": [
            "quiet pause shot: train window reflection with landscape sliding by softly, no subtitle",
            "quiet pause shot: empty platform edge and a ticket held still in hand, no subtitle",
        ],
    }
    choices = pause_shots.get(world_id)
    if choices:
        return choices[(index // 2) % len(choices)]
    return f"quiet pause shot: the same visual world holds still, {symbol_text} remain in frame, soft breathing rhythm, no subtitle"


def build_storyboard(
    reflection: str,
    emotion: dict,
    subtitles: list[str],
    visual_style: dict | None = None,
    visual_continuity: dict | None = None,
    expression_plan: dict | None = None,
    visual_poetic_plan: dict | None = None,
) -> list[dict]:
    if llm_enabled():
        system_prompt = """
你是一个生活化电影镜头导演。

根据用户原句、情绪解析和字幕节奏，生成 9:16 情绪短视频镜头脚本。

约束：
- 真实生活感。
- 普通人视角。
- 深夜感或安静氛围。
- 不广告化。
- 不科幻。
- 不商业大片。
- 反思而不消沉，画面不能过黑，必须保留可见环境细节。
- 需要遵守视觉风格设定，但不要让风格覆盖用户情绪。
- 需要遵守视觉连续性设定：同一人物气质、同一空间体系、同一光线和色彩逻辑。
- 可以换景别和角度，但不要突然跳到无关地点。
- 每条字幕必须对应一个镜头。
- 只输出 JSON，格式必须是 {"storyboard": [...]}。
"""
        user_prompt = f"""
用户原句：
{reflection}

情绪解析：
{emotion}

字幕：
{subtitles}

表达导演计划：
{expression_plan or {}}

视觉意境计划：
{visual_poetic_prompt(visual_poetic_plan)}

视觉风格设定：
{visual_style_prompt(visual_style) if visual_style else "ordinary reflective realism, not depressive, visible light"}

视觉连续性设定：
{visual_continuity_prompt(visual_continuity)}

请输出 storyboard，每项包含：
- scene: 中文生活化电影镜头
- subtitle: 对应字幕，必须和输入字幕一致
- camera: slow push / static shot / slow pan / gentle handheld / slow zoom 之一
- lighting: 英文简短光线描述
- duration: 数字，只有字幕完全等于 "..." 时才填 1.2，其他字幕填 2.4
"""
        result = chat_json(system_prompt, user_prompt, temperature=0.45)
        return _normalize_storyboard(result["storyboard"], subtitles, expression_plan)

    keywords = emotion.get("visual_keywords", [])
    preferred_elements = []
    poetic_progression = ((visual_poetic_plan or {}).get("motif") or {}).get("progression", [])
    poetic_symbols = ((visual_poetic_plan or {}).get("motif") or {}).get("recurring_symbols", [])
    poetic_world = ((visual_poetic_plan or {}).get("world") or {}).get("label", "")
    poetic_world_id = ((visual_poetic_plan or {}).get("world") or {}).get("id", "")
    scenes = [
        f"{poetic_world}意境中，{step}，反复出现{', '.join(poetic_symbols[:3])}，真实电影感"
        for step in poetic_progression
    ] or [
        SCENE_BANK.get(keyword, f"{keyword}的生活化电影镜头") for keyword in keywords
    ]
    if not scenes:
        scenes = ["深夜房间，一个人安静坐着，像是在和自己对话"]

    expression_by_subtitle = _expression_by_subtitle(expression_plan)

    storyboard = []
    scene_index = 0
    for index, subtitle in enumerate(subtitles):
        unit = expression_by_subtitle.get(subtitle, {})
        if subtitle == "...":
            scene = "画面留白，只有微弱光线和缓慢呼吸感"
            scene = _pause_scene(index, visual_poetic_plan)
        else:
            scene = scenes[scene_index % len(scenes)]
            scene_index += 1

        storyboard.append(
            {
                "scene": scene,
                "subtitle": subtitle,
                "subtitle_role": unit.get("role", "primary"),
                "semantic_role": unit.get("semantic_role", "pause" if subtitle == "..." else "setup"),
                "camera_intent": unit.get("camera_intent", ""),
                "visual_world": poetic_world,
                "visual_world_id": poetic_world_id,
                "recurring_symbols": poetic_symbols,
                "camera": CAMERAS[index % len(CAMERAS)],
                "lighting": LIGHTING[index % len(LIGHTING)],
                "duration": 2.4 if subtitle != "..." else 1.2,
            }
        )

    return storyboard
