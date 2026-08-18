---
name: req-schedule-edit
description: |
  国泰海通科技平台需求排期极速修改与查询工具。支持按需求编号（R26xxxxxxx）、史诗编号（E/PG 开头批量更新下属 Story）或大宽表 rowId 写入。WebSocket 直连 + 本地热缓存，热缓存 <1s 极速落库，带缓存回读校验（--verify）。支持界面 Playwright 兜底（--browser）。
  触发词：修改排期、需求排期修改、修改需求排期、需求排期确认、排期修改、排期改成、排期调整、R2607150083 20260821。
agent_created: true
---

# 国泰海通需求排期修改技能 (req-schedule-edit)

⚡ **极速性能**：直连科技平台大宽表 WebSocket + 本地热缓存 (`.sheet_rows_cache.pkl`)，无需打开浏览器页面。热缓存响应 **<1s** 极速落库！

---

## 📌 架构与执行入口

本技能底层对接 `gtht-skills` 的极速 WebSocket 协议引擎：

```bash
# 核心 WebSocket 直连脚本路径：
SCRIPT="/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/gtht-skills/gtht-demand-fetch/scripts/schedule_fast.py"
```

---

## 🚀 使用方法

### 1. 按需求号写排期（最常用推荐）

将目标需求的「计划生产排期」修改为指定日期（支持 `20260821` 或 `2026-08-21`），并自动回读校验落库：

```bash
python3 "$SCRIPT" R2607150083 20260821 --verify
```

### 2. 按史诗写排期（批量更新史诗下所有 Story）

传入史诗编号（`E` 或 `PG` 开头，如 `PG202204-0261`），自动批量更新该史诗关联的所有 Story 的计划生产排期：

```bash
python3 "$SCRIPT" PG202204-0261 20260821 --verify
```

### 3. 只读查询当前排期

不带日期参数时，直接查询并显示目标行当前的计划生产排期：

```bash
python3 "$SCRIPT" R2607150083
```

### 4. 强制刷新缓存 / UI 浏览器兜底

* 强制刷新大宽表本地缓存（大宽表行数据变动或新增 Story 时使用）：
  ```bash
  python3 "$SCRIPT" R2607150083 20260821 --refresh --verify
  ```
* 界面 Playwright DOM 点击模式（仅在 API/WS 协议异常时作为 UI 兜底）：
  ```bash
  .venv/bin/python /Users/wujin/.workbuddy/skills/req-schedule-edit/scripts/edit_req_schedule.py R2607150083 20260821 --headed
  ```

---

## 📋 参数说明

| 参数名 | 必填 | 示例/格式 | 说明 |
| :--- | :---: | :--- | :--- |
| `<req_id>` | **是** | `R2607150083` / `PG202204-0261` | 目标需求编号或史诗编号 |
| `<YYYYMMDD>` | 否 | `20260821` / `2026-08-21` | 目标排期日期；未传时为只读查询模式 |
| `--verify` | 否 | N/A | 修改完成后追加缓存回读比对校验 |
| `--refresh` | 否 | N/A | 强制重新拉取全量大宽表以刷新本地缓存 |

---

## ⚙️ 原理与可靠性说明

1. **WebSocket 直链**：建立 `wss://fintech.gtht.com.cn/ws/table-socket/table/websocket/{tableId}` 通信通道，发送行索引更新数据帧；
2. **热缓存加速**：大宽表全量行映射缓存至 `~/.local/share/gtht/.sheet_rows_cache.pkl`（TTL 2 小时），极速定位目标行；
3. **安全确认**：服务端回包 `code: 1` 即代表服务端落库成功，无需等待整页加载。
