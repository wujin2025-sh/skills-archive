---
name: omnivoice
description: Speak and transcribe through the user's local VoiceStudio — free, offline, no API key. Text-to-speech (including the user's cloned voices) and speech-to-text via the OpenAI-compatible API at localhost:3900.
---

# VoiceStudio — 本地 TTS（语音合成）与 STT（语音转写）

用户运行着 [VoiceStudio](https://github.com/debpalash/VoiceStudio)，这是一个完全本地化的语音应用，在 `http://localhost:3900/v1` 提供兼容 OpenAI 的音频 API。每当用户要求生成语音、朗读文本、克隆声音或转写音频时即可使用它——零成本、离线可用，且音频数据绝不离开本地机器。

## 前提条件与自动准备流程（Agent 调用本技能时必须先执行）

每次接收到语音合成 (TTS) 或语音转写 (STT) 任务时，Agent **必须优先完成以下准备**：

1. **健康检查**：
   ```sh
   curl -sf http://localhost:3900/health
   ```
2. **准备结果响应**：
   - **健康（返回 200 / ok）**：服务就绪，直接继续执行后续 TTS/STT 请求。
   - **异常 / 无法连接**：
     - Agent 应先向用户汇报：“已进行服务探针检查，检测到本地 VoiceStudio 服务未在 `http://localhost:3900` 启动。”
     - 提示用户启动 VoiceStudio 桌面客户端，或指导用户在源码目录启动后端服务 (`bun run dev:api`)。
     - 待服务启动成功后再继续执行请求。

## 文本转语音 (Text-to-speech)

```sh
curl -s http://localhost:3900/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model": "tts-1", "voice": "alloy", "input": "TEXT HERE", "response_format": "wav"}' \
  --output speech.wav
```

- `model`：`tts-1` 或 `tts-1-hd` — 两者均映射到用户当前启用的 TTS 引擎。
- `voice`：OpenAI 标准音色名称（`alloy`、`echo`、`nova` 等）可用，**但最强大的功能是用户自己克隆的音色 Profile ID** — 先获取声音列表（详见下方），当用户提及“我的声音”、“旁白声音”或指定音色名称时，优先使用对应克隆音色。
- `response_format`：`wav`、`mp3`、`flac`、`opus` 或 `pcm`。
- 长文本处理：支持长文本 — 引擎内部会自动按句子边界切分处理。

## 探索用户的克隆音色

```sh
curl -s http://localhost:3900/v1/audio/voices
```

列出所有已克隆/设计的音色 Profile（含 id 和名称）以及已安装的引擎。将 Profile 的 id 作为调用 `/speech` 接口时的 `voice` 参数值。

## 语音转文本 (Speech-to-text)

```sh
curl -s http://localhost:3900/v1/audio/transcriptions \
  -F file=@clip.wav -F model=whisper-1 -F response_format=json
```

- `model`：`whisper-1` 映射到当前启用的 ASR 引擎（默认 WhisperX；用户可在 设置 → 引擎 中自由切换）。
- `response_format`：`json`、`text`、`verbose_json`（包含逐句分段时间戳）、`srt` 或 `vtt` — 当用户需要字幕时，可直接指定输出 `srt`/`vtt`。

## Python 调用示例（使用 openai SDK）

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:3900/v1", api_key="none")  # api_key 可填写任意字符串，后端不作校验

audio = client.audio.speech.create(model="tts-1", voice="alloy", input="Hello!", response_format="wav")
text = client.audio.transcriptions.create(model="whisper-1", file=open("clip.wav", "rb")).text
```

## 注意事项

- **无需 API 密钥、无频率限制、无账单费用** — 全部运行在用户自身的硬件设备上。冷启动后的首次合成可能耗时稍长（需加载模型）；后续调用速度极快。
- 更多高级功能：除基础语音合成/转写外，更高级的功能（如视频配音、批量任务、音色设计、有声书制作等）均支持完整的 REST API — 交互式 API 文档已内置于应用中（**设置 → OpenAPI 参考**），也可引导用户在应用内打开查看。
- 若调用时提示引擎/模型错误，具体的排查细节通常包含在响应体中 — 请原样展示给用户；VoiceStudio 的错误信息均设计为用户可自行修复的指引（例如提示需要在设置中开启哪个开关）。
