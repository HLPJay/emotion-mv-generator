# AI Reflection Video Generator

一句真实反思，生成一条 9:16 情绪型短视频。

这个 MVP 先把主链路跑通：

1. 输入一句感悟
2. 解析情绪与氛围
3. 拆解字幕节奏
4. 生成生活化镜头脚本
5. 本地生成电影感占位画面
6. 拼接字幕、镜头运动、BGM，输出 MP4

默认不依赖真实 LLM 或图片模型。后续接入 MiniMax M2.7 / image-01 时，只需要替换 `services/llm_service.py` 和 `services/image_service.py`。

## 运行

```bash
pip install -r requirements.txt
python app.py
```

打开 Gradio 提供的本地地址，输入一句感悟即可生成视频。

## 视觉风格控制

视频默认使用 `随机：影像质感`。视觉风格只控制摄影质感，不再控制场景。

两个下拉框职责不同：

```text
意境世界 = 内容舞台 / 视觉母题 / 象征关系
视觉风格 = 光线 / 色彩 / 颗粒 / 镜头质感
```

例如：

```text
意境世界：山路远方
视觉风格：薄雾诗意光
```

表示镜头仍然发生在山路远方，但画面采用薄雾、柔光、低对比的诗意摄影质感。

可选风格定义在：

```text
templates/visual_styles.json
```

当前内置：

```text
natural_daylight_film     自然日光胶片
warm_memory_film          温柔回忆胶片
cool_clear_reflection     冷静清透反思
misty_poetic_light        薄雾诗意光
wide_sublime_cinema       开阔宏大电影感
rain_after_clarity        雨后清明
minimal_quiet_realism     极简安静现实
```

默认随机会根据文案和情绪选择合适的影像质感；具体场景由 `visual_poetic_plan` 的意境世界决定。

所有风格都遵守统一底线：

```text
反思，不消沉
有情绪，但不绝望
生活化，不广告化
不过黑，不惊悚
```

每次生成会在 run 目录保存：

```text
visual_style.json
```

报告中也会记录本次使用的视觉风格。

视觉风格还包含连续性约束：

```text
same ordinary adult throughout
same visual world from visual_poetic_plan
consistent lighting logic
consistent palette
recurring symbols from visual_poetic_plan
```

这用于减少人物、空间和画面气质在同一条视频中频繁跳变。

同时每次生成会保存：

```text
visual_continuity.json
```

它会明确本条视频的：

```text
subject
location
recurring_objects
lighting
palette
```

并注入分镜与图片 prompt。当前使用文字连续性控制；更强的 `key visual + image-to-image` 方案记录在 `docs/backlog.md`。

## 运行事件日志

每次生成会写入：

```text
generated/runs/<run_id>/run_events.jsonl
```

每一行记录一个步骤事件：

```json
{"step":"image_generation","status":"success","duration_seconds":40.83}
```

用于排查：

```text
哪一步最慢
哪一步失败
是否生成到了 report
最终视频路径
```

`run_report.md` 会汇总关键事件。

## Gradio 调试面板

页面现在包含多个调试 Tab：

```text
核心：emotion / visual_style
节奏：expression_plan / subtitle_plan / audio_plan
分镜：storyboard
报告：run_report / run_dir
```

用于直接在页面查看内部运行结果，不必每次手动翻 run 目录。

## Expression Plan

项目现在有一层统一的表达导演层：

```text
用户输入
→ expression_plan
→ subtitle_plan
→ audio_plan
→ storyboard
```

`expression_plan` 会识别：

```text
primary: 主体感悟
secondary: 括号解释
question: 追问句
setup / turn / core_admission / context_note / question / ending_echo
```

每个表达单元都会带有：

```text
subtitle_text
spoken_text
emphasis_words
voice_layer
speed / pitch / volume
pause_after
camera_intent
```

这样字幕、声音、镜头不再各自理解原文，而是共用同一份表达控制计划。配置文件在：

```text
templates/voice_performance_profiles.json
```

## Visual Poetic Plan

为了避免图片和主题脱节，项目新增了视觉意境层：

```text
expression_plan
→ visual_poetic_plan
→ storyboard
→ image prompt
```

`visual_poetic_plan` 不把场景固定成电脑前，而是先选择：

```text
visual_archetype: 视觉原型，例如跨过边界、开始上路、从遗留到行动
visual_world: 视觉世界，例如普通生活、城市白天、农村亲情、山路远方、海边远望、星空宇宙、火车旅途
motif: 本条视频反复出现的视觉符号和镜头推进
```

一条视频只会选择一个视觉世界，并要求：

```text
same world
same recurring symbols
same protagonist
same light logic
same emotional progression
```

配置文件在：

```text
templates/visual_poetic_worlds.json
```

这样同一个主题可以有多种意境表达，但同一条视频内部不会乱跳世界。

页面里可以手动选择“意境世界”：

```text
自动：根据主题选择最适合
普通生活
现实工作台
城市白天
农村亲情
山路远方
海边远望
星空宇宙
火车旅途
```

默认是自动主题适配：先根据文案、表达计划和情绪选择最贴近的意境世界；如果多个世界同样适合，会做稳定选择；如果没有明显主题线索，才用稳定兜底。手动选择时，只固定 `visual_world`，`visual_archetype` 仍然会根据文案主题匹配，所以不会变成生硬套场景。

## Subtitle Guard

字幕模型输出后会经过规则守门，避免字幕重复、过长或停顿混乱。

守门逻辑：

```text
标准化字幕文本
拆分附着在句尾的 ...
去除重复字幕
限制非停顿字幕最多 4 条
重建 short_pause / heavy_pause / ending_silence
保留原句里的逗号、句号、问号等自然标点
识别括号内容为 secondary 解释层
```

输出会包含：

```json
{
  "guard": {
    "changed": true,
    "actions": ["normalized_subtitle_text", "rebuilt_pause_sequence"],
    "spoken_count": 3,
    "max_spoken_lines": 4
  }
}
```

报告中如果字幕被守门器修正，会出现 `subtitle_guard_changed` warning。

字幕还会做语义防碎句处理：

```text
避免 “只是每次。” / “就已经。” 这类半句话独立出现
自动合并过短连接句
保持字幕是语义完整短句
```

字幕视觉使用偏大的电影感样式：

```text
主句字号约 74，长句自动略微缩小
括号解释内容字号约 50，位置略低，颜色略弱
最多 2 行
主句位置在画面约 69% 高度
柔白文字 + 轻阴影
淡入 0.28s / 淡出 0.38s
```

括号输入约定：

```text
相比于生活的困境，我一直更害怕的是怯弱的自己。（只有自己最懂自己，越害怕越回避）
```

会被拆成：

```text
primary: 相比于生活的困境，
primary: 我一直更害怕的是怯弱的自己。
secondary: 只有自己最懂自己，
secondary: 越害怕越回避。
```

`secondary` 字幕会更小，且旁白使用 `secondary_voice` 的内心补充音色。默认仍然是男声，只是更轻、更低、更近；若第二音色不可用，会自动退回主音色，避免整条视频失败。

第二音色可以在 `config/model_config.json` 的 `audio.secondary_voice_id` 中替换：

```json
{
  "audio": {
    "voice_id": "male-qn-qingse",
    "secondary_voice_id": "male-qn-qingse"
  }
}
```

## 替换文本大模型 API

当前文本模型调用使用 OpenAI-compatible Chat Completions 格式。日常使用直接改：

```text
config/model_config.json
```

DeepSeek 示例：

```json
{
  "enabled": true,
  "provider": "deepseek",
  "api_base": "https://api.deepseek.com",
  "model": "deepseek-chat",
  "api_key": "你的 API Key"
}
```

OpenAI 示例：

```json
{
  "enabled": true,
  "provider": "openai",
  "api_base": "https://api.openai.com/v1",
  "model": "gpt-4.1-mini",
  "api_key": "你的 API Key"
}
```

MiniMax 示例，前提是你的账号接口支持 OpenAI-compatible chat completions：

```json
{
  "enabled": true,
  "provider": "minimax",
  "api_base": "https://api.minimaxi.com/v1",
  "model": "MiniMax-M2.7-highspeed",
  "api_key": "你的 API Key"
}
```

图片生成使用 MiniMax image-01，配置在同一个文件的 `image` 字段：

```json
{
  "image": {
    "enabled": true,
    "provider": "minimax",
    "api_base": "https://api.minimaxi.com/v1",
    "model": "image-01",
    "api_key": "",
    "aspect_ratio": "9:16",
    "response_format": "base64",
    "prompt_optimizer": true,
    "fallback_on_error": true
  }
}
```

`image.api_key` 为空时会复用顶部的 `api_key`。单步测试图片：

```powershell
python scripts\test_image_step.py
```

图片生成排查：

- 每次生成会在图片目录写入 `image_generation_metadata.json`。
- `fallback_detected=false` 表示真实图片 API 成功。
- `fallback_detected=true` 表示至少有一张图退回了本地占位图，具体原因看 `errors` 和 `fallback_indices`。
- MiniMax image-01 对 prompt 长度有限制，当前项目会把图片 prompt 压缩到 `1400` 字符以内，避免触发 `prompt length must be less than 1500`。
- 如果页面里图片带有 `CINEMATIC LIFE SHOT` 测试字样，基本可以判断是本地占位图，不是真实 API 图片。

关闭真实模型、回到本地规则：

```json
{
  "enabled": false,
  "provider": "deepseek",
  "api_base": "https://api.deepseek.com",
  "model": "deepseek-chat",
  "api_key": ""
}
```

环境变量仍然可以覆盖配置文件，适合临时测试。

PowerShell 示例：

```powershell
$env:REFLECTION_LLM_ENABLED="1"
$env:REFLECTION_LLM_API_BASE="https://api.deepseek.com"
$env:REFLECTION_LLM_MODEL="deepseek-chat"
$env:REFLECTION_LLM_API_KEY="你的 API Key"
```

单步测试：

```powershell
python scripts\test_step.py semantic
python scripts\test_step.py emotion
python scripts\test_step.py subtitle
python scripts\test_step.py storyboard
python scripts\test_step.py all
```


## 目录

```text
app.py
services/
  llm_service.py
  emotion_service.py
  subtitle_service.py
  storyboard_service.py
  image_service.py
  video_service.py
prompts/
templates/
assets/
  music/
  fonts/
generated/
  images/
  videos/
```

## 产品原则

用户负责真实感悟，AI 负责视觉表达。

AI 不替用户写鸡汤，不讲大道理，不强行升华，只做情绪理解、镜头生成、节奏拆解与视觉表达。

## Backlog

遗留设计记录见：

```text
docs/backlog.md
```
