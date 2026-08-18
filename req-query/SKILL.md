---
name: 需求查询
description: |
  金融科技平台需求管理极速查询工具。优先打 REST API 直连获取需求详情与核心要素（标题、级别、状态、提出人、提交部门、期望上线时间、背景及内容等），0.28s 秒级返回。支持 --headed 模式打开无头/有头浏览器进行 UI 确认。
  触发词：需求查询、查需求、Rxxxx、需求编号、需求管理、req_query、req-query。
agent_created: true
---

# 需求查询技能 (req-query)

⚡ **极速性能**：优先使用 REST API 直连模式（复用 `gtht-skills` 的会话），耗时仅 **0.28 秒** 即可极速输出完整需求要素、提交人部门及关联附件列表。

---

## 📌 触发条件

当用户提及以下关键词或提供需求编号时触发本技能：

- **需求查询**、**查需求**、**查询需求**、**req_query**、**req-query**
- 提供需求编号格式如 `R2605250074`
- 需求管理、需求列表

---

## 🚀 使用方法

### 1. 默认极速 REST API 查询 (0.28s 秒级返回)

```bash
python3 "/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/gtht-skills/gtht-demand-fetch/scripts/fetch_demand.py" <需求编号>
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

1. **REST API 优先 (0.28s)**：直连 `demand-service/demandsub/queryDemandsubInfo` REST API，绕过复杂的全局搜索与 AG Grid / Ant Table 页面渲染；
2. **凭据与会话共享**：统一复用 `~/.config/gtht/config.json` 及 `~/.local/share/gtht/session.json` 中的 JWT Token；
3. **附件与图片智能提取**：自动将需求单中包含的原型图与文档附件同步下载归档至 `附件/` 目录，供后续分析。
