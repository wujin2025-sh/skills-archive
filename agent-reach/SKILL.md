---
name: agent-reach
description: Agent Reach 全网跨平台多媒体与网页情报检索引擎。给 AI Agent 一键装上互联网能力：支持 YouTube 字幕/视频检索、B站免登录直连检索（bili-cli）、Jina Reader 语义网页读取、RSS/Atom 订阅解析、Reddit、Twitter、Xueqiu 等多后端自动路由。内置多后端容灾与自检（agent-reach doctor）。
triggers:
  - agent-reach
  - Agent Reach
  - 网页读取
  - 视频信息检索
  - YouTube字幕
  - B站免登录搜索
---

# Agent Reach：全网跨平台多媒体与情报检索引擎

> **定位**：聚合 YouTube、B站、Twitter、Reddit、小红书、雪球、RSS 等平台的情报采集工具，自动完成多后端路由与容灾降级。
> **核心优势**：零配置支持网页纯净解析、YouTube 字幕提取、B站视频搜索；已集成 `bili`、`yt-dlp` 等底层高速原生工具。

---

## 🚀 常用场景与调用命令

### 1. 快速健康检查
```bash
agent-reach doctor
```
一键体检各个平台的连通状态与可用后端。

### 2. 视频多媒体素材检索与字幕
- **B站（免登录直连）**：
  ```bash
  bili search "327国债期货 万国证券" --limit 10
  bili info BV1xxxxxx
  ```
- **YouTube 字幕与讲座转录**：
  ```bash
  yt-dlp --write-auto-sub --skip-download --sub-lang zh-Hans,zh,en "https://www.youtube.com/watch?v=xxxxxx"
  ```

### 3. 干净 Markdown 网页读取（Jina Reader 引擎）
无需启动笨重浏览器，极速提取文章主体文本与排版：
```bash
curl -s "https://r.jina.ai/https://目标网页链接"
```

### 4. 平台协同与进阶组合
- 对于需要复杂登录态与反爬验证的国内平台（如微信公众号图文、小红书图集、雪球长文），优先联动 **`opencli`**（利用已建立的 Chrome 浏览器桥接）；
- 对于公开内容、视频字幕与 RSS 聚合流，使用 **`agent-reach`** 与原生 CLI 组合秒级响应。
