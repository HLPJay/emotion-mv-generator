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

## Key Visual + I2I 连续性实验

当前先采用文字连续性控制：

```text
subject / location / recurring objects / lighting / palette
```

后续可实验更强一致性：

```text
1. 先用 T2I 生成 key_visual.png
2. 后续镜头使用 image-to-image 参考 key_visual
3. 控制不同景别、角度和动作
```

注意风险：

- 首图不好会带偏整条视频。
- I2I 可能导致镜头过于相似。
- 情绪 MV 不一定需要同一张脸完全一致，更需要同一气质、空间和光线。
