---
name: wechat-download-api
description: 微信公众号文章批量获取、RSS 订阅与全量多格式导出引擎 (FastAPI + FastMCP)。支持一键整号打包为 Markdown / Word / PDF / EPUB / Excel / JSON 7 种格式（图片内嵌离线可看）。内置 FastMCP 服务（6 个工具：list_subscriptions, search_accounts, get_recent_articles, read_article, subscribe_account, unsubscribe_account）与 macOS 一键控制脚本。
triggers:
  - wechat-download-api
  - 微信公众号批量下载
  - 公众号整号导出
  - wechatrss
  - 微信导出PDF
  - 微信导出Markdown
---

# WeChat Download API：微信公众号批量获取、RSS 订阅与整号导出引擎

> **定位**：自托管的微信公众号文章抓取、RSS 订阅与全量多格式打包服务，支持通过 FastMCP 协议供 AI 智能体直接调用。
> **核心优势**：
> 1. **整号历史文章一键导出**：支持打包为 Markdown / HTML / Word / PDF / EPUB / Excel / JSON 7 种格式，Word/PDF/EPUB 自动内嵌图片离线可看；
> 2. **AI 原生 MCP 接口**：内置 FastMCP 服务（注册名：`wechatrss`），支持 AI 直接调用搜索、订阅与阅读文章；
> 3. **反风控设计**：Chrome TLS 指纹模拟 + SOCKS5 代理轮转 + 自动限频。

---

## 🚀 服务管理命令（macOS 原生）

服务位于 `/Volumes/Macintosh HD_Data/Project/wechat-download-api`，已配备一键管理脚本：

```bash
# 启动服务（后台常驻，端口 5050）
"/Volumes/Macintosh HD_Data/Project/wechat-download-api/wechat_service.sh" start

# 查看服务状态与运行日志
"/Volumes/Macintosh HD_Data/Project/wechat-download-api/wechat_service.sh" status

# 停止服务
"/Volumes/Macintosh HD_Data/Project/wechat-download-api/wechat_service.sh" stop

# 重启服务
"/Volumes/Macintosh HD_Data/Project/wechat-download-api/wechat_service.sh" restart
```

---

## 🔑 扫码登录与凭证自动维护

1. 启动服务后，浏览器打开管理后台：
   **`http://localhost:5050/login.html`**
2. 使用微信公众号管理员微信扫码登录。
3. 登录成功后凭证自动保存至 `.env`，有效期约为 **4 天**。
4. 登录后即可通过 API 与 MCP 获取**全网任意公开公众号**的文章，不限于自己的公众号。

---

## 📦 整号多格式导出接口

直接通过浏览器或 HTTP 请求下载整号历史文章打包合集：
- **Markdown 合集**：`http://localhost:5050/api/export/account/{fakeid}.zip`
- **PDF 合集（内嵌高清图片）**：`http://localhost:5050/api/export/account/{fakeid}.pdf`
- **Word 合集（.docx）**：`http://localhost:5050/api/export/account/{fakeid}.docx`
- **EPUB 电子书**：`http://localhost:5050/api/export/account/{fakeid}.epub`
- **Excel 文章清单表**：`http://localhost:5050/api/export/account/{fakeid}.xlsx`

可在 RSS 订阅管理面板（`http://localhost:5050/rss.html`）右侧点击「下载文章」进行可视化筛选与导出。

---

## 🤖 AI 智能体 MCP 调用指南

本项目已在 Antigravity 全局 MCP 配置 (`~/.gemini/antigravity/mcp_config.json`) 中注册为 **`wechatrss`**。

### 提供的 6 大 MCP 工具：
1. `list_subscriptions()`: 列出本机已订阅的所有微信公众号。
2. `search_accounts(query="...")`: 按关键词搜索公众号，获取 `fakeid`。
3. `subscribe_account(fakeid="...")`: 一键订阅目标公众号。
4. `get_recent_articles(since=0, limit=30, source_id="...")`: 按时间增量拉取已抓取的文章列表。
5. `read_article(article_id=...)`: 获取单篇文章的 Markdown 纯净正文（带 YAML frontmatter）。
6. `unsubscribe_account(fakeid="...")`: 取消订阅公众号。
