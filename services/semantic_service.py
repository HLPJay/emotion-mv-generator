from __future__ import annotations

from services.llm_service import chat_json, llm_enabled


def expand_semantics(reflection: str) -> dict:
    if not llm_enabled():
        return {
            "literal_meaning": reflection,
            "context_analysis": {
                "speaker_state": "自我审视中，情绪克制但有压力。",
                "implied_situation": "外部困难只是表层，真正的矛盾来自对自己的不满。",
                "relationship_to_self": "带有自责、羞耻和想直面的复杂感。",
                "temporal_feel": "像深夜回想某个时刻后的低声独白。",
            },
            "appropriate_expansion": {
                "inner_conflict": "害怕的不是困境本身，而是自己在困境前退缩的那一面。",
                "emotional_subtext": "这句话的重量在于无法替自己辩解。",
                "visual_associations": ["停住的手", "未发送的文字", "镜子里的沉默", "深夜房间"],
            },
            "boundaries": ["不新增人生道理", "不替用户立人设", "不编造具体经历", "不强行升华"],
        }

    system_prompt = """
你是一个“真实感悟语义扩充器”，不是文案创作者。
你的任务是把用户的一句话补成后续分镜系统能理解的结构化语义。

允许扩充：
- 字面意思的保真解释
- 语境分析：说话者状态、潜在处境、自我关系、时间氛围
- 适当扩展：内在冲突、情绪潜台词、生活镜头联想
- 只扩展“这句话已经暗示的东西”

禁止：
- 写鸡汤
- 讲人生大道理
- 替用户新增价值观
- 强行升华
- 改写用户原意
- 编造具体经历、人际关系或事件
- 把“可能的镜头细节”写成“用户真的经历过的事”
- 用“他/她可能经历了某件事”这种确定叙述

只输出 JSON，不要输出解释。
"""
    user_prompt = f"""
用户原句：
{reflection}

请输出：
{{
  "literal_meaning": "不改写、不升华地解释原句字面含义",
  "context_analysis": {{
    "speaker_state": "说话者当下精神状态",
    "implied_situation": "只基于原句可推断的潜在处境，不编具体事件",
    "relationship_to_self": "说话者如何看待自己",
    "temporal_feel": "适合的视频时间感和空气感"
  }},
  "appropriate_expansion": {{
    "inner_conflict": "一句话描述内在冲突",
    "emotional_subtext": "一句话描述未明说但能被感到的情绪潜台词",
    "visual_associations": ["4-6个普通生活镜头元素，不要写成具体经历"]
  }},
  "forbidden_expansions": ["不应该扩充的方向"]
}}
"""
    return chat_json(system_prompt, user_prompt, temperature=0.35)
