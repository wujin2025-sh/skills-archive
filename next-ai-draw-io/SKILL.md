---
name: next-ai-draw-io
displayName: Next AI Draw.io（AI 驱动 Draw.io 实时绘图）
version: "0.2.3"
description: 基于 Next AI Draw.io 与 MCP 协议的智能图表生成与实时协作技能。支持自然语言生成/修改 Draw.io 图表、浏览器画布实时渲染同步、云原生架构图（AWS/GCP/Azure/阿里云/微服务）、多页面标签管理及 .drawio/.png/.svg 多格式导出。
homepage: https://github.com/DayuanJiang/next-ai-draw-io
license: Apache-2.0
metadata:
  author: DayuanJiang
  repo: https://github.com/DayuanJiang/next-ai-draw-io
  mcp_package: "@next-ai-drawio/mcp-server"
---

# Next AI Draw.io: AI 驱动 Draw.io 实时绘图与多端联动

Next AI Draw.io 是由 Dayuan Jiang 开发的开源 AI 图表生成与实时协作系统。通过 Model Context Protocol (MCP) 与本地嵌入式 HTTP 服务，使 AI Agent 能够直接操控 Draw.io 画布，并在浏览器中实现**毫秒级实时所见即所得 (WYSIWYG) 渲染与交互式编辑**。

---

## 🎯 核心功能与特性

1. **浏览器实时同步预览**：AI 创建或修改图表时，浏览器画布实时流式更新，无需手动保存或重新导入。
2. **多模态与自然语言图表生成**：
   - 流程图（Flowcharts）、时序图（Sequence Diagrams）
   - 云原生架构图（AWS, GCP, Azure, 阿里云, 腾讯云）
   - 微服务拓扑、数据流图、UML/ER 关系图
3. **版本历史与回退**：内置视觉化版本快照，支持随时回退到任意历史版本。
4. **精细化增量修改**：支持基于 Cell ID 的定向增、删、改，无需重绘整个图表。
5. **多页面（Multi-Page Tabs）管理**：支持单文件多标签页的增删改查。
6. **多格式导出**：一键导出为 `.drawio`、高保真 `.png` 或矢量 `.svg` 文件。

---

## 🛠️ MCP 工具清单 (Available MCP Tools)

MCP 服务名为 `drawio`，提供以下 10 大核心工具：

| 工具名称 (Tool) | 功能描述 | 核心参数 |
| :--- | :--- | :--- |
| `start_session` | 启动本地服务并在浏览器中打开实时画布 | `port`（可选，默认 6002） |
| `create_new_diagram` | 基于标准 Draw.io XML 创建新图表 | `xml`（必填，图表 XML 字符串） |
| `load_diagram` | 从磁盘读取现有的 `.drawio` 文件到会话中 | `path`（必填，文件绝对路径） |
| `edit_diagram` | 按 Cell ID 执行局部更新、新增或删除操作 | `operations`（包含 update/add/delete 的操作列表） |
| `get_diagram` | 提取当前画布的完整 XML 数据 | 无 |
| `export_diagram` | 将当前图表导出并保存至本地文件 | `path`（必填，支持 .drawio, .png, .svg）, `format` |
| `list_pages` | 列出图表中所有的标签页及其基本信息 | 无 |
| `add_page` | 向当前图表追加新的空白页面/标签页 | `name`（可选，页面名称） |
| `rename_page` | 重命名指定的标签页 | `page_id` 或 `page_index`, `new_name` |
| `delete_page` | 删除指定的标签页（保护最后一页不被删除） | `page_id` 或 `page_index` |

---

## 💻 启动与配置指南

### 1. 本地全局运行环境

MCP Server 已全局安装至系统环境：
- **可执行文件路径**：`/Users/wujin/.npm-global/bin/next-ai-drawio-mcp`
- **NPM 包名**：`@next-ai-drawio/mcp-server@latest`

### 2. MCP 客户端配置

#### Antigravity / Gemini 配置 (`~/.gemini/antigravity/mcp_config.json`)
```json
{
  "mcpServers": {
    "drawio": {
      "command": "/Users/wujin/.npm-global/bin/next-ai-drawio-mcp",
      "args": []
    }
  }
}
```

#### Cursor 配置 (`~/.cursor/mcp.json`)
```json
{
  "mcpServers": {
    "drawio": {
      "command": "/Users/wujin/.npm-global/bin/next-ai-drawio-mcp",
      "args": []
    }
  }
}
```

#### Claude Code CLI 配置
```bash
claude mcp add drawio -- npx @next-ai-drawio/mcp-server@latest
```

---

## 🚀 典型工作流示例

### 工作流 A：新建图表并实时预览
1. Agent 调用 `start_session`，在默认浏览器弹出 `http://localhost:6002/?mcp=...` 页面；
2. Agent 构建符合 Draw.io 规范的 XML（支持 `<mxGraphModel>`、节点与连线）；
3. Agent 调用 `create_new_diagram(xml=...)`，浏览器画布瞬间呈现出完整的拓扑图；
4. 确认无误后，Agent 调用 `export_diagram(path="/path/to/arch.drawio")` 存盘。

### 工作流 B：已有图表的增量维护与修改
1. Agent 调用 `load_diagram(path="/path/to/legacy.drawio")` 将现有图表载入会话；
2. Agent 调用 `start_session` 打开浏览器查看现状；
3. 用户提出修改（如：“在网关后面加一个 Redis 缓存节点”）；
4. Agent 调用 `edit_diagram` 精确新增节点并重连边线；
5. 调用 `export_diagram` 覆盖或另存为新文件。

---

## 🤝 与 `drawio-skill` 的分工与协作

| 对比维度 | **next-ai-draw-io** (本技能) | **drawio-skill** (本地桌面 CLI) |
| :--- | :--- | :--- |
| **交互模式** | **浏览器实时所见即所得预览**，边生成边看 | 本地无头生成 + CLI 导出图片查看 |
| **强项场景** | 交互式实时设计、渐进式对话修改、多页面管理 | 10k+ 图标库精准样式检索 (`shapesearch.py`)、Graphviz 自动排版 |
| **最佳结合** | 使用 `drawio-skill` 检索精准云厂商图标 style，配合 `next-ai-draw-io` 在浏览器中进行实时构图与交互调整！ |

