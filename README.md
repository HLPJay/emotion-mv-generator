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
