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

视频默认使用 `随机` 视觉风格。随机不是固定滤镜，而是根据输入文本和情绪做稳定随机选择：同一句输入通常会选择同一个风格，方便复现；不同输入会自然产生差异。

可选风格定义在：

```text
templates/visual_styles.json
```

当前内置：

```text
morning_room_reflection   清晨房间反思
afternoon_window_room     下午窗边房间
daytime_workspace_reflection 白天工位反思
library_quiet_table       图书馆安静桌面
daytime_bus_window        白天公交窗边
sunny_sidewalk_pause      白天街边停顿
kitchen_morning_stillness 早晨厨房静思
park_bench_daylight       白天公园长椅
bookstore_afternoon       下午书店角落
rainy_evening_commute     雨后通勤
late_office_afterhours    下班后办公室
subway_window_reflection  地铁窗影
warm_table_lamp           暖色台灯
quiet_cafe_corner         安静咖啡馆
city_walk_dusk            黄昏城市慢行
small_apartment_window    小房间窗边
```

默认随机会更偏向白天、清晨、下午和自然光场景；夜晚/通勤/办公室等仍可手动指定。

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
same visual world
consistent lighting logic
consistent palette
recurring scene details
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
节奏：subtitle_plan / audio_plan
分镜：storyboard
报告：run_report / run_dir
```

用于直接在页面查看内部运行结果，不必每次手动翻 run 目录。

## Subtitle Guard

字幕模型输出后会经过规则守门，避免字幕重复、过长或停顿混乱。

守门逻辑：

```text
标准化字幕文本
拆分附着在句尾的 ...
去除重复字幕
限制非停顿字幕最多 4 条
重建 short_pause / heavy_pause / ending_silence
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
字号约 62，长句自动略微缩小
最多 2 行
位置在画面约 69% 高度
柔白文字 + 轻阴影
淡入 0.28s / 淡出 0.38s
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
