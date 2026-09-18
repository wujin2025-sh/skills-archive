---
name: call-recorder-toggle
description: 一键电话录音开关技能。调用此技能可启动录音、停止录音或查询当前录音状态，录音结束后自动保存 .wav 并触发 /audio-to-minutes
  转写与 Obsidian 归档。
disable: false
---


# 🎙️ 电话录音开关技能 (call-recorder-toggle)

本技能提供 100% 手控可控的电话/会议录音一键开关与自动归档管道。

### 🚀 常用动作与指令

1. **一键切换开关 (Toggle)**：
   运行 `/Users/wujin/.workbuddy/skills/call-recorder-toggle/scripts/toggle.py toggle`
   * 若当前未在录音，自动开启录音并弹窗提示 `🔴 电话录音已开启`。
   * 若当前正在录音，自动结束录音、安全存盘 `.wav` 并弹窗 `🟢 电话录音已保存`，同时调起 `/audio-to-minutes` 进行文本转写归档。

2. **强行开启录音 (Start)**：
   运行 `/Users/wujin/.workbuddy/skills/call-recorder-toggle/scripts/toggle.py start`

3. **强行停止录音 (Stop)**：
   `python3 /Users/wujin/.workbuddy/skills/call-recorder-toggle/scripts/toggle.py stop`

4. **查询录音状态 (Status)**：
   `python3 /Users/wujin/.workbuddy/skills/call-recorder-toggle/scripts/toggle.py status`
