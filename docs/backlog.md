# Backlog

## 主句 + 括号语境输入

用户输入可以支持两层结构：

```text
相比于生活的困境，我一直更害怕的是怯弱的自己。
（只有自己最懂自己，越害怕越回避）
```

设计原则：

- 括号外是 `main_text`，用于字幕、旁白、视频核心表达。
- 括号内是 `context_note`，用于情绪理解、语义扩充、分镜、音乐和视觉方向。
- 默认 `context_note` 不直接进入字幕和旁白，避免解释感破坏留白。
- 后续可增加选项：仅用于理解、作为结尾字幕、作为旁白补充、完全忽略。

建议新增：

```text
services/input_parser_service.py
```

结构：

```json
{
  "raw_text": "...",
  "main_text": "...",
  "context_note": "...",
  "has_context_note": true,
  "context_usage": "guide_only"
}
```

链路使用：

- `emotion_service`: `main_text + context_note`
- `semantic_service`: `main_text + context_note`
- `subtitle_service`: `main_text` only
- `storyboard_service`: `main_text + context_note + subtitles`
- `audio_plan`: subtitles only
- `image_prompt`: storyboard + context_note
