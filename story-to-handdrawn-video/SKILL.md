---
name: story-to-handdrawn-video
description: 将中文故事文案或按顺序排列的本地图片，转换为带手写字幕、从左至右黑白到彩色显色、可选翻页过渡、安全无裁剪画幅以及无声音轨 Remotion
  画面的手绘日记漫画动画。
disable: false
---


# 故事转手绘视频 (Story to Hand-drawn Video)

通过本 Skill 的 `scripts/run_story_video.py` 使用项目渲染器。当项目目录不是当前工作目录时，设置环境变量 `STORY_VIDEO_PROJECT`。封装脚本不得依赖特定作者的绝对路径。

## 工作流程 (Workflow)

1. 接收行内中文故事文本、UTF-8 文本文件或按顺序排列的本地图片。
2. 保留用户的原始表述。对于文本输入，默认将一个完整句子作为一个镜头节奏（beat），仅在自然叙事转折处拆分长复合句。
3. 对于上传的合成页面，自动裁剪手写字幕和插图，并在本地生成对齐的黑白图层（black-and-white plate）。
4. 在直切模式（direct-cut）下，保持 `字幕(text) → 黑白全图(bw_full) → 彩色(color)` 的顺序，所有阶段均从左至右渐显。
5. 在翻页模式（page-flip）下，保留未作修改的上传主图并静态展示，随后从右下角卷起翻页。不添加字幕、黑白或重配色阶段。在纸张背面保留原页面的淡化版本。
6. 确保所有插图笔触留在白色安全边框内。使用内含式画幅（contained framing），绝不使用 `cover` 裁剪。
7. 生成无声 MP4 视频。配音与可选背景音乐属于后期制作任务。
8. 汇报场景数量、总时长、输出路径以及生成结果是仅计划（plan-only）、预览（preview）还是最终版本（final）。

## 上传图片 (Uploaded images)

预览模式：

```bash
python3 scripts/run_story_video.py \
  --images /absolute/01.jpg /absolute/02.jpg \
  --title "故事标题" \
  --mode preview \
  --transition cut
```

最终渲染（直切模式）：

```bash
python3 scripts/run_story_video.py \
  --images /absolute/01.jpg /absolute/02.jpg \
  --title "故事标题" \
  --mode full \
  --transition cut \
  --page-duration 4.4
```

最终渲染（翻页模式）：

```bash
python3 scripts/run_story_video.py \
  --images /absolute/01.jpg /absolute/02.jpg \
  --title "故事标题" \
  --mode full \
  --transition page-flip \
  --transition-sec 0.7
```

使用 `--layout auto|composite|full` 来控制如何解析上传的页面。

## 故事文本 (Story text)

仅生成计划（不生成图像）：

```bash
python3 scripts/run_story_video.py --input /absolute/story.txt --title "故事标题" --mode plan
```

准备 Codex Image2 任务，然后导入并渲染：

```bash
python3 scripts/run_story_video.py --input /absolute/story.txt --title "故事标题" --mode generate
python3 scripts/run_story_video.py --mode import
python3 scripts/run_story_video.py --mode render
```

默认使用 `--generator codex`。仅当用户明确选择 API 备选方案且 `OPENAI_API_KEY` 可用时，才使用 `--generator api`。仅当用户明确希望替换现有已生成的批次时，才使用 `--force`。

对于时间跨度大、代词歧义、医疗场景或对年龄敏感的角色，通过 `--visual-plan` 提供以两位数场景 ID 为键的 JSON 视觉计划。

## 输出约定 (Output contract)

- 文本故事最终版: `<project>/out/picture_silent.mp4`
- 文本故事预览版: `<project>/out/picture_silent-preview.mp4`
- 上传图片最终版: `<project>/out/uploaded_picture_silent.mp4`
- 上传图片预览版: `<project>/out/uploaded_picture_silent-preview.mp4`
- 分辨率: 最终版 1080×1440；预览版 720×960
- 编码/音频: H.264，静音

除非用户明确要求，否则不要运行单独的校验或测试命令。
