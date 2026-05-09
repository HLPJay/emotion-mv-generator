from __future__ import annotations

from services.llm_service import chat_json, llm_enabled


EMOTION_KEYWORDS = {
    "长期回避": ["害怕", "怯弱", "回避", "逃避", "不敢", "拖延"],
    "职业迷茫": ["工作", "职业", "上班", "简历", "面试", "未来"],
    "孤独": ["一个人", "孤独", "没人", "沉默", "空房间"],
    "停滞": ["停滞", "原地", "没有变化", "困住", "卡住"],
    "成长焦虑": ["成长", "焦虑", "变好", "优秀", "努力"],
}


MOOD_MAP = {
    "长期回避": ("深夜压抑", "克制独白", ["待办", "深夜电脑", "空房间", "停滞的鼠标"]),
    "职业迷茫": ("清晨迷雾", "低声自问", ["地铁站台", "电脑文档", "城市窗户", "未发送邮件"]),
    "孤独": ("安静空旷", "内心独白", ["空椅子", "窗边", "路灯", "无人街道"]),
    "停滞": ("潮湿沉默", "缓慢凝视", ["暂停的时钟", "未完成笔记", "散落纸张", "关闭的门"]),
    "成长焦虑": ("冷暖交界", "克制希望", ["镜子", "台灯", "笔记本", "清晨窗光"]),
}


def _structure_prompt(input_structure: dict | None) -> str:
    if not input_structure:
        return ""
    return f"""
输入结构分析：
main_theme: {input_structure.get('main_theme')}
parenthetical_theme: {input_structure.get('parenthetical_theme')}
relationship: {input_structure.get('relationship')}
emotional_shift: {input_structure.get('emotional_shift')}
注意：括号用于理解第二层意义，不要让括号完全覆盖主句。
"""


def analyze_emotion(reflection: str, input_structure: dict | None = None) -> dict:
    if llm_enabled():
        system_prompt = """
你是一个情绪解析器，不是文案生成器。
根据用户的一句真实感悟，分析核心情绪、视频氛围、叙事语气和生活化视觉关键词。

约束：
- 不写鸡汤。
- 不讲大道理。
- 不替用户新增观点。
- 只理解情绪和适合的视觉表达。
- 视觉关键词必须是普通生活元素，不要科幻、大片、广告感。
- 只输出 JSON。
"""
        user_prompt = f"""
用户原句：
{reflection}

{_structure_prompt(input_structure)}

请输出：
{{
  "emotion": "核心情绪，2-6个字",
  "mood": "视频氛围，2-8个字",
  "tone": "叙事语气，2-8个字",
  "visual_keywords": ["4个普通生活镜头元素"],
  "style": {{
    "palette": "low saturation blue gray",
    "texture": "film grain",
    "visual_language": "realistic late-night life photography"
  }}
}}
"""
        return chat_json(system_prompt, user_prompt, temperature=0.35)

    scores = {
        emotion: sum(1 for keyword in keywords if keyword in " ".join([reflection, str(input_structure or {})]))
        for emotion, keywords in EMOTION_KEYWORDS.items()
    }
    emotion = max(scores, key=scores.get)
    if scores[emotion] == 0:
        emotion = "长期回避"

    mood, tone, visual_keywords = MOOD_MAP[emotion]
    return {
        "emotion": emotion,
        "mood": mood,
        "tone": tone,
        "visual_keywords": visual_keywords,
        "style": {
            "palette": "low saturation blue gray",
            "texture": "film grain",
            "visual_language": "realistic late-night life photography",
        },
    }
