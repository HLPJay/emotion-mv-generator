from __future__ import annotations

from services.llm_service import chat_json, llm_enabled
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


def build_storyboard(reflection: str, emotion: dict, subtitles: list[str], visual_style: dict | None = None) -> list[dict]:
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

视觉风格设定：
{visual_style_prompt(visual_style) if visual_style else "ordinary reflective realism, not depressive, visible light"}

请输出 storyboard，每项包含：
- scene: 中文生活化电影镜头
- subtitle: 对应字幕，必须和输入字幕一致
- camera: slow push / static shot / slow pan / gentle handheld / slow zoom 之一
- lighting: 英文简短光线描述
- duration: 数字，只有字幕完全等于 "..." 时才填 1.2，其他字幕填 2.4
"""
        result = chat_json(system_prompt, user_prompt, temperature=0.45)
        return result["storyboard"]

    keywords = emotion.get("visual_keywords", [])
    preferred_elements = (visual_style or {}).get("style", {}).get("scene_elements", [])
    scenes = [f"{element}里的生活化反思镜头" for element in preferred_elements] or [
        SCENE_BANK.get(keyword, f"{keyword}的生活化电影镜头") for keyword in keywords
    ]
    if not scenes:
        scenes = ["深夜房间，一个人安静坐着，像是在和自己对话"]

    storyboard = []
    scene_index = 0
    for index, subtitle in enumerate(subtitles):
        if subtitle == "...":
            scene = "画面留白，只有微弱光线和缓慢呼吸感"
        else:
            scene = scenes[scene_index % len(scenes)]
            scene_index += 1

        storyboard.append(
            {
                "scene": scene,
                "subtitle": subtitle,
                "camera": CAMERAS[index % len(CAMERAS)],
                "lighting": LIGHTING[index % len(LIGHTING)],
                "duration": 2.4 if subtitle != "..." else 1.2,
            }
        )

    return storyboard
