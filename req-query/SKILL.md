---
name: 需求查询
description: '金融科技平台需求管理极速查询工具。优先走 kjptai MCP 直连（gtht-req-query）获取需求详情与核心要素（标题、级别、状态、提出人、提交部门、期望上线时间、背景及内容等），毫秒级返回。
  支持 --headed 模式打开无头/有头浏览器进行 UI 确认。

  触发词：需求查询、查需求、Rxxxx、需求编号、需求管理、req_query、req-query。

  '
agent_created: true
disable: false
---

# 需求查询技能 (req-query)

⚡ **极速性能**：优先走 kjptai MCP 直连（`gtht-req-query`），毫秒级输出完整需求要素、提交人部门及关联附件列表；MCP 不可用时回退 Playwright 模式。

---

## 📌 触发条件

当用户提及以下关键词或提供需求编号时触发本技能：

- **需求查询**、**查需求**、**查询需求**、**req_query**、**req-query**
- 提供需求编号格式如 `R2605250074`
- 需求管理、需求列表

---

## 🚀 使用方法

### 1. 默认极速查询（kjptai MCP 直连优先，Playwright 兜底）

> ⚠️ **REST API 直连脚本（`fetch_demand.py`）当前不可用**，`gtht-skills` 目录已不存在。推荐优先使用 `gtht-req-query` 技能（kjptai MCP `query_requirement` 纯 MCP 直连，<0.5s 返回），无需脚本、无需浏览器。

当 MCP 不可用或需浏览器兜底时，使用 Playwright 模式：

```bash
.venv/bin/python scripts/req_query.py <需求编号>
```

#### 返回 JSON 核心字段
包含：`demand_id`, `title`, `status`, `priority`, `expected_online`, `submitter`, `submitter_dept`, `background`, `content`, `images`, `attachments`, `elapsed_s`, `extra`。

---

### 2. UI 界面有头查询模式 (打开 Playwright 浏览器)

当用户指定 `--headed` 或需要人工观察 DOM 界面时：

```bash
.venv/bin/python scripts/req_query.py <需求编号> --headed
```

---

## ⚙️ 架构与优化亮点

1. **kjptai MCP 直连优先**：推荐走 `gtht-req-query`（kjptai MCP `query_requirement`，纯 MCP 直连 <0.5s），无需脚本与浏览器；MCP 不可用时回退 Playwright `scripts/req_query.py`（复用 `~/.config/gtht/config.json` 凭据与 `~/.local/share/gtht/session.json` JWT Token，绕过页面渲染）；
2. **凭据与会话共享**：统一复用 `~/.config/gtht/config.json` 及 `~/.local/share/gtht/session.json` 中的 JWT Token；
3. **附件与图片智能提取**：自动将需求单中包含的原型图与文档附件同步下载归档至 `附件/` 目录，供后续分析。
