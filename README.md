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
核心：emotion / visual_style / visual_poetic_plan / narrative_plan
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

## Narrative Plan

为了让视频不只是“关键词配图”，项目在视觉意境后新增了镜头叙事层：

```text
expression_plan
→ visual_poetic_plan
→ narrative_plan
→ storyboard
→ image prompt
```

`visual_poetic_plan` 负责确定世界、符号和意境；`narrative_plan` 负责确定每个非暂停镜头的叙事任务。

输出文件：

```text
generated/runs/<run_id>/narrative_plan.json
```

典型字段：

```json
{
  "arc": "从遗留停滞到轻微行动",
  "turning_point": "括号内容、提问或核心承认进入时",
  "visual_strategy": "现实工作台里，从待办堆积、手停住，推进到第一次执行动作。",
  "shots": [
    {
      "function": "establish_state",
      "purpose": "建立当前处境和情绪背景",
      "visual_intent": "桌面、笔记本、电脑屏幕和未完成待办，人物只以背影或手进入画面",
      "camera_intent": "establishing"
    }
  ]
}
```

这些字段会继续注入 `storyboard` 和图片 prompt：

```text
narrative_function
emotional_purpose
visual_intent
generation_mode
```

因此每张图会被要求服务一个镜头功能，例如建立状态、加重停滞、揭示问题、转折、行动信号或结尾留白，而不是只画出相关物件。

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
  "max_completion_tokens": 8192,
  "json_retries": 2,
  "json_response_format": false,
  "api_key": "你的 API Key"
}
```

长分镜容易超过默认输出长度，建议保留 `max_completion_tokens: 8192`。

- `json_retries` 控制大模型返回非 JSON 或被截断时的重试次数。
- `json_response_format` 控制是否向 OpenAI-compatible 接口传 `response_format={"type":"json_object"}`。如果当前供应商不支持该字段，保持 `false`。
- 当 LLM 开启时，分镜必须来自大模型。若多次重试仍无法得到合法 JSON，本次生成会明确失败并写入报告，不会静默退回本地分镜。
- 只有关闭 LLM 时，才会使用本地兜底分镜。

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

## 音乐与重拼视频

项目默认会调用 MiniMax Music API 生成真实 BGM：

```text
generated/runs/<run_id>/audio/bgm.mp3
```

MiniMax `music-2.6` 可能生成耗时较长。Token Plan 用户建议使用：

```json
{
  "music": {
    "enabled": true,
    "model": "music-2.6",
    "output_format": "hex",
    "request_timeout_seconds": 600,
    "retry_attempts": 3,
    "retry_backoff_seconds": [5, 15],
    "fallback_models": [],
    "fallback_on_error": true
  }
}
```

说明：

- `request_timeout_seconds` 控制音乐接口等待时间，默认 600 秒。
- `retry_attempts` 控制同一个音乐模型的重试次数，默认 3 次。
- `retry_backoff_seconds` 控制重试间隔，默认先等 5 秒，再等 15 秒。
- `fallback_models` 默认不再自动加入 `music-2.6-free`；Token Plan 用户通常不支持 free 模型，强行 fallback 会产生 `2061 your current token plan not support model`。
- 如果确实有可用的备用模型，可以手动写入 `fallback_models`。

如果 `bgm.mp3` 不存在，说明音乐生成失败，视频会退回本地兜底音：

```text
generated/runs/<run_id>/audio/generated_ambient.wav
```

同时还可能生成一层低音量环境声：

```text
generated/runs/<run_id>/audio/environment_*.wav
```

最终报告会记录音频状态，重点看：

```json
{
  "audio_status": {
    "bgm_exists": true,
    "fallback_ambient_exists": true,
    "environment_sound_count": 1,
    "music_error": "",
    "used_music_fallback": false
  }
}
```

如果音乐接口失败，错误原因会写入：

```text
generated/runs/<run_id>/audio/music_generation_error.txt
```

并同步进入 `run_report.json` 的 `warnings`。

单步测试音乐生成：

```powershell
python scripts\test_music_generation.py --model music-2.6 --prompt "cinematic emotional ambient score, soft piano motif, warm pads, slow tempo, no vocal, no lyrics"
```

使用最近一次生成的 `audio_plan.json` 测试音乐：

```powershell
python scripts\test_music_generation.py --use-latest-plan --model music-2.6
```

如果图片已经生成成功，只想重新生成 BGM 并重拼最终视频，不重新生成图片：

```powershell
python scripts\recompose_run_video.py
```

指定某个 run 重拼：

```powershell
python scripts\recompose_run_video.py --run-dir "generated\runs\<run_id>"
```

重拼脚本会复用已有：

```text
adjusted_storyboard.json
audio_plan.json
emotion.json
images/scene_*.png
audio/narration_*.mp3
```

然后重新生成或复用 BGM，重写：

```text
final.mp4
run_report.json
run_report.md
```

如果原来已有 `final.mp4`，默认会先备份为：

```text
final_before_recompose.mp4
```

重拼时会优先复用已有：

```text
generated/runs/<run_id>/audio/bgm.mp3
```

如果 `bgm.mp3` 已存在，不会重复调用 MiniMax 音乐接口；如果不存在，才会尝试生成 BGM。

## 停顿镜头节奏

字幕节奏里仍然可以保留 `...`，用于旁白停顿、呼吸和结尾留白。

为了避免视频中间频繁切图，`...` 对应的停顿镜头默认会复用上一张画面：

- 不再为每个中间停顿额外调用图片生成接口。
- 停顿期间不显示字幕，画面保持上一镜头的视觉内容。
- 视频合成会弱化“上一镜头 -> 停顿镜头”的淡入淡出，减少闪切感。
- `image_generation_metadata.json` 会记录 `visual_hold_reused_indices`，方便确认哪些镜头复用了上一画面。

## 视频合成性能

视频编码参数可以在 `config/model_config.json` 的 `video` 字段里调整：

```json
{
  "video": {
    "fps": 24,
    "codec": "libx264",
    "audio_codec": "aac",
    "preset": "veryfast",
    "threads": 6
  }
}
```

常用建议：

```text
日常迭代：preset=veryfast, fps=24
最快预览：preset=ultrafast, fps=20
最终质量：preset=medium, fps=24
```

每次合成会写入性能明细：

```text
generated/runs/<run_id>/video_compose_timings.json
```

其中会记录：

```json
{
  "duration": 27.22,
  "fps": 24,
  "preset": "veryfast",
  "threads": 6,
  "timings": {
    "build_video_clips": 4.457,
    "music_prepare": 0.0,
    "narration_prepare": 0.456,
    "background_audio": 0.071,
    "environment_audio": 1.262,
    "write_videofile": 220.213
  }
}
```

如果合成慢，优先看 `write_videofile`。这个阶段是 MoviePy 逐帧渲染与 H.264 编码，通常是最慢的部分。


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

阶段归档见：

```text
docs/archive_2026-05-09.md
```
