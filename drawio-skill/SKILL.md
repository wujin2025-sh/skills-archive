---
name: drawio-skill
version: 1.14.0
description: 当用户请求绘制各种图表、流程图、架构图、ER 图、UML / 时序图 / 类图、网络拓扑图、机器学习/深度学习模型结构图（Transformer/CNN/LSTM）、思维导图或任何可视化表达时使用。当向用户解释包含 3 个及以上组件系统、复杂数据流或适合可视化展示的关系时，也可主动使用。最适合需要自定义样式、丰富形状库、泳道或可导出图片（PNG/SVG/PDF/JPG）的图表场景。通过本地原生 draw.io 桌面 CLI 生成 .drawio XML 并导出图片。
license: MIT
homepage: https://github.com/Agents365-ai/drawio-skill
compatibility: 依赖本地 PATH 中的 draw.io 桌面应用 CLI（macOS/Linux/Windows）。视觉自检步骤需要支持 Vision 能力的模型（如 Claude Sonnet/Opus）；不可用时自动优雅跳过。可选的自动排版脚本 (scripts/autolayout.py) 需要安装 Graphviz (dot)。
platforms: [macos, linux, windows]
metadata: {"openclaw":{"requires":{"anyBins":["draw.io","drawio"]},"emoji":"📐","os":["darwin","linux","win32"],"install":[{"id":"brew-drawio","kind":"brew","formula":"drawio","bins":["drawio"],"label":"Install draw.io via Homebrew","os":["darwin"]},{"id":"brew-graphviz","kind":"brew","formula":"graphviz","bins":["dot"],"label":"Install Graphviz for optional autolayout.py","os":["darwin"],"optional":true}]},"hermes":{"tags":["drawio","diagram","flowchart","architecture","visualization","uml"],"category":"design","requires_tools":["drawio","draw.io"],"related_skills":["mermaid","excalidraw","plantuml"]},"author":"Agents365-ai","version":"1.14.0"}
---

# Draw.io 图表生成技能 (Draw.io Diagrams)

## 1. 概述

生成 `.drawio` XML 文件并通过本地原生的 draw.io 桌面应用 CLI 导出为 PNG/SVG/PDF/JPG。

**支持的格式：** PNG, SVG, PDF, JPG — 绝不需要任何浏览器自动化控制。

PNG、SVG 和 PDF 导出支持 `--embed-diagram` (`-e`) 参数 — 导出的图片文件内部包含完整的图表 XML 数据，因此将其重新拖入 draw.io 即可恢复为可编辑的原始图表。使用双扩展名（如 `name.drawio.png`）来提示内部内嵌了 XML 数据。

## 2. 适用与不适用场景

**适用本技能的场景：** 制作精美、高精度的图表（架构图、网络图、严格的 UML 图、ER 实体关系图），任何需要不透明填充颜色、10,000+ 预置/品牌图标、泳道或自定义几何形状的图表，并导出为可编辑的 PNG/SVG/PDF。

**不适合本技能（应分发至其他技能）的场景：**
- 需要休闲的手绘/白板风格 → 使用 **excalidraw** 或 **tldraw**。
- 嵌入在 Git / Markdown 中通过代码直接渲染的图表 → 使用 **mermaid**（通用）或 **plantuml**（UML）。
- 无限画布的手绘涂鸦或自由画笔 → 使用 **tldraw**。

## 3. 随包内置资源

当工作流提及以下资源时，根据需要读取 — 无需预先将其放入上下文：

| 文件 | 何时读取 |
|---|---|
| `references/diagram-types.md` | 用户指定了特定图表类型（ERD、UML 类图、时序图、架构图、ML/DL 模型图、流程图） |
| `references/shapes.md` + `scripts/shapesearch.py` | 图表需要 **特定的形状/图标** — 云服务图标（AWS/Azure/GCP）、Cisco/Kubernetes/网络符号、UML/BPMN/ER/电气/P&ID 元素 — 或任何需要精准设置 `style=` 字符串的时刻。执行 `shapesearch.py "<关键词>"` 可查询 10k+ 官方图形的精确样式 |
| `scripts/aiicons.py` | 图表涉及 **AI/LLM 品牌图标**（OpenAI, Claude, Gemini, Mistral, Llama, HuggingFace, Ollama, LangChain 等） — `aiicons.py "<品牌>"` 返回品牌 Logo 的 draw.io `image` 样式（基于 CDN 的 lobe-icons；加 `--embed` 支持内联数据）。draw.io 本身没有内置 AI Logo。参见 `references/shapes.md` → "AI / LLM brand logos" |
| `references/style-presets.md` | 用户要求学习/保存/列表/设置默认/删除样式预设，或者需要应用已解析的预设规则 |
| `references/style-extraction.md` | 在 Learn 学习流程中需要提取预设的过程 |
| `references/troubleshooting.md` | 导出失败、Vision 校验拒绝 PNG 或渲染出现异常时 |
| `scripts/repair_png.py` | 每次执行 `-e` PNG 导出后调用 — 修复 draw.io CLI 导出的截断 IEND 数据块（Known Issue #8） |
| `scripts/encode_drawio_url.py` | CLI 不可用时生成浏览器兜底 diagrams.net URL（加 `--edit` 生成可编辑的在线编辑器 URL） |
| `scripts/autolayout.py` / `references/autolayout.md` | 图表体量大或依赖复杂排版（依赖图/调用图、代码结构、>~15 个节点），需要 Graphviz 计算节点位置与正交边路由 |
| `scripts/pyimports.py` · `jsimports.py` · `goimports.py` · `rustimports.py` | 可视化 **Python, JS/TS, Go 或 Rust 项目**结构 — 提取导入依赖图供自动排版使用 |
| `scripts/pyclasses.py` | 可视化 **Python 类继承树 / 类图** — 提取类及其继承关系供自动排版使用 |
| `scripts/validate.py` | 生成 `.drawio` 后，在 Vision 自检前执行快速结构 Lint 校验（检查悬空边、重复 ID、错误父子关系、重叠） |

## 4. 前置条件与环境依赖

本地必须已安装 draw.io 桌面应用，并且 CLI 可被调用：

**macOS 沙盒/隔离环境注意事项（例如 codex.app 等沙盒）：** 在某些带有沙盒隔离的 macOS 环境中，调用 draw.io 桌面 CLI（即使运行 `drawio --version`）可能会导致进程崩溃或无任何输出。遇到此情况时，请将 CLI 视为**在沙盒隔离中不可用** — 不要在沙盒内重复尝试。优先在**非沙盒宿主环境**中执行 CLI 导出，或使用浏览器 URL 兜底 / 纯 `.drawio` XML 输出。

```bash
# macOS (Homebrew 推荐；CLI 可执行文件为 `drawio`)
brew install --cask drawio
drawio --version

# macOS (非 PATH 时的全路径)
/Applications/draw.io.app/Contents/MacOS/draw.io --version

# Windows
"C:\Program Files\draw.io\draw.io.exe" --version

# Linux
drawio --version
```

安装 draw.io 桌面端（若缺失）：
- macOS：`brew install --cask drawio` 或从 https://github.com/jgraph/drawio-desktop/releases 下载
- Windows：从 https://github.com/jgraph/drawio-desktop/releases 下载安装包
- Linux：从 https://github.com/jgraph/drawio-desktop/releases 下载 `.deb`/`.rpm` — **请勿使用 snap**（AppArmor 沙盒拒绝服务器密钥环，会导致崩溃）

## 5. 标准工作流 (Workflow)

在开始工作流前，评估用户的请求是否足够明确。若缺少关键细节，询问 1-3 个有针对性的问题：
- **图表类型** — 哪种预设？（ERD、UML、时序图、架构图、ML/DL模型图、流程图或通用图表）
- **导出格式** — PNG（默认）、SVG、PDF 或 JPG？
- **输出位置** — 默认为用户的工作目录；若用户指定了路径（如 `./artifacts/`）则遵从。用户未提及则不必询问。
- **范围/精细度** — 包含多少组件？是否有指定的特定技术栈或标签？

若用户请求中已包含了这些细节或属于简单的常见场景（例如“画一个 X 的流程图”），可跳过询问。

### 步骤 0 — 解析当前启用的样式预设 (Preset)

判断是否有用户自定义的样式预设适用于本次生成。
- 扫描用户消息中是否明确提及样式预设名称（如 "use my `<name>` style", "in `<name>` mode"）。
- 否则检查 `~/.drawio-skill/styles/` 目录中是否有包含 `"default": true` 的预设。
- 若均无，则使用内建默认色彩与规范。

### 步骤 1 — 检查依赖并确认二进制路径

在当前系统中确认 draw.io 二进制命令名称（`drawio` 或 `draw.io` 或路径），并在随后的命令行中保持一致。

### 步骤 2 — 规划设计 (Plan)

确定形状、相互关系、排版方向（从左到右 LR 或从上到下 TB），并按层级/分层进行分组。

### 步骤 3 — 生成 `.drawio` XML 文件 (Generate)

对于小巧/精致的图表直接手动计算写入坐标；对于大型或复杂排版图表（>15 个节点），使用 `autolayout.py` 自动计算节点与正交路由边。生成后可运行 `validate.py` 进行静态 Lint 校验。

### 步骤 4 — 导出草图预览 (Export Draft)

运行 CLI 导出预览 PNG。**在此步骤切勿使用 `-e`**（`-e` 附加的内嵌 XML 会导致视觉 Vision API 报 400 错）。预览时使用 `--width 2000` 限制图片尺寸，防止超过 Vision 模型尺寸上限。保存为单扩展名 `<name>.png`。

### 步骤 5 — 视觉自检 (Self-Check)

利用 Agent 的 Vision 视觉能力读取生成的 PNG 预览图，自行检查节点重叠、文本截断、悬空边或连线穿透节点等问题，自动修正后重绘（最多执行 2 轮自检）。

### 步骤 6 — 用户审查循环 (Review Loop)

将预览图展示给用户，根据反馈针对性地修改 XML 节点、颜色、文字或布局，重新导出并确认，直至用户满意。

### 步骤 7 — 终案导出 (Final Export)

用户批准后，使用 `-e` 导出终案（如 `<name>.drawio.png`），导出后立即对 PNG 执行 `python3 scripts/repair_png.py` 修复 IEND 尾部数据。报告导出的文件路径并可提供打开查看提示。

---

## 6. XML 结构与格式规范

### 文件基本骨架 (File Skeleton)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="drawio" version="26.0.0">
  <diagram name="Page-1">
    <mxGraphModel>
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <!-- 用户图形元素从 id="2" 开始 -->
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

**关键规则：**
- `id="0"` 和 `id="1"` 是必需的根单元格 — 切勿遗漏
- 用户图形节点从 `id="2"` 开始依次递增
- 所有节点默认设置 `parent="1"`（除非处于容器内，则使用容器的 `id`）
- 文本需在 style 中包含 `html=1` 以保证正确渲染
- **切勿在 XML 注释中使用 `--`** — 这违反 XML 规范并引发解析错误
- 属性中的特殊字符需转义：`&amp;`, `&lt;`, `&gt;`, `&quot;`
- **标签中的多行文本：** 使用 `&#xa;` 作为换行符（不要用字面量 `\n`）。例如 `value="第1行&#xa;第2行"`

---

## 7. 导出命令汇总 (Export Commands)

存在**两种**导出模式：

1. **预览/自检模式**（工作流步骤 4）— **不加 `-e`**，输出 `diagram.png`。
2. **终案/交付模式**（工作流步骤 7）— **必须加 `-e`**，输出 `diagram.drawio.png`（内嵌可编辑 XML）。

```bash
# 1. 预览 PNG (工作流步骤 4，自检前) — 不加 -e，限制最大宽度 2000px
drawio -x -f png --width 2000 -o diagram.png input.drawio

# 2. 终案 PNG (工作流步骤 7，用户批准后) — 包含 -e 内嵌 XML，双扩展名
drawio -x -f png -e -s 2 -o diagram.drawio.png input.drawio
# 终案 PNG 导出后立即执行修复
python3 scripts/repair_png.py diagram.drawio.png

# 3. SVG 导出 (终案)
drawio -x -f svg -e -o diagram.svg input.drawio

# 4. PDF 导出 (终案)
drawio -x -f pdf -e -o diagram.pdf input.drawio
```

---

## 8. 降级兜底方案 (Fallback Chain)

当环境工具受限或不可用时，优雅地降级处理：

| 场景 | 处理方式 |
|----------|----------|
| 缺少 draw.io CLI，但 Python 可用 | 使用浏览器 URL 兜底（`encode_drawio_url.py` 生成 diagrams.net 链接） |
| 缺少 draw.io CLI 且无 Python | 仅生成 `.drawio` XML 文件，提示用户手动在桌面端或网页端打开 |
| 沙盒隔离导致 CLI 崩溃或无输出 | 视为沙盒内 CLI 不可用，提供浏览器 URL 兜底或仅生成 XML |
| Vision 视觉能力不可用 | 跳过步骤 5 自检，直接将导出图片展示给用户 |
| Linux 无头服务器导出失败 | 尝试 `xvfb-run -a`，或使用 Docker (`tomkludy/drawio-renderer`) API 导出 |
