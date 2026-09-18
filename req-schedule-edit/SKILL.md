---
name: adjust-plandate
description: '国泰海通科技平台需求排期极速修改与查询工具 v3。支持按需求编号（R26xxxxxxx）、史诗编号（E/PG 开头批量更新下属 Story）。Python websockets 直连 + 本地热缓存索引，热缓存 <1s 极速落库，带缓存回读校验（--verify）。Playwright 仅做登录兜底。

  触发词：修改排期、需求排期修改、修改需求排期、需求排期确认、排期修改、排期改成、排期调整、R2607150083 20260821、adjust-plandate。

  '
disable: false
---

# 国泰海通需求排期修改技能 (adjust-plandate) — v3 极速直连引擎

⚡ **极速性能**：Python `websockets` 直连科技平台 WebSocket + 预建索引热缓存（`.table_cache_index.json`）。热缓存查询 **<0.1s**，WebSocket 写回 **~0.2s/行**，无需打开浏览器！

---

## 📌 架构与执行入口

```bash
# v3 极速直连引擎（推荐）：
SCRIPT_V3="/Users/wujin/.chat/skills/adjust-plandate/scripts/schedule_fast_v3.py"

# v2 旧版（Playwright 兜底，仅当 v3 异常时使用）：
SCRIPT_V2="/Users/wujin/.chat/skills/adjust-plandate/scripts/schedule_fast.py"
```

---

## 🚀 使用方法

### 1. 按需求号写排期（最常用推荐）

```bash
python3 "$SCRIPT_V3" R2607150083 20260821 --verify
```

### 2. 按史诗写排期（批量更新史诗下所有 Story）

```bash
python3 "$SCRIPT_V3" PG202204-0261 20260821 --verify
```

### 3. 只读查询当前排期（不带日期参数）

```bash
python3 "$SCRIPT_V3" R2607150083
```

### 4. 强制刷新缓存

```bash
python3 "$SCRIPT_V3" R2607150083 20260821 --no-cache --verify
```

### 5. 旧版 Playwright 兜底（仅当 v3 异常时）

```bash
python3 "$SCRIPT_V2" R2607150083 20260821 --verify
```

### 6. 🔄 排期修改后联动重点关注需求同步

> **工作流约定**：`adjust-plandate` 排期修改执行完成后，**必须主动提醒用户运行 `/wujin-focus-demand` 技能**，将修改后的排期同步到腾讯文档「重点需求」子表，确保重点关注需求的排期信息在腾讯文档中实时更新。

```bash
# 排期修改完成后，提醒用户执行：
/wujin-focus-demand
```

**说明**：当修改的排期涉及「重点关注」需求时，此联动是确保腾讯文档与科技平台数据一致的关键步骤。

---

## 📋 参数说明

| 参数名 | 必填 | 示例/格式 | 说明 |
| :--- | :---: | :--- | :--- |
| `<req_id>` | **是** | `R2607150083` / `PG202204-0261` | 目标需求编号或史诗编号 |
| `<YYYYMMDD>` | 否 | `20260821` / `2026-08-21` | 目标排期日期；未传时为只读查询模式 |
| `--verify` | 否 | N/A | 修改后重新拉取 API 回读校验 |
| `--no-cache` | 否 | N/A | 强制忽略热缓存，重新拉取全量大宽表 |

---

## ⚙️ v3 原理与性能

### 架构图
```
用户输入 (Rxxxx YYYYMMDD)
    │
    ├─ ① 热缓存索引查询 (O(1) demandId → Story)  ── <0.1s
    │     └─ 未命中 → API 拉取 14960 行 (~16s) → 建索引存盘
    │
    ├─ ② WebSocket 直连更新 (Python websockets)  ── ~0.2s/行
    │     └─ wss://fintech.gtht.com.cn/ws/table-socket/table/websocket/{tableId}
    │     └─ 心跳初始化 → 发送数据帧 → 等待 code:1 确认
    │
    └─ ③ 缓存同步 → 更新本地索引 → 输出 Markdown 结果
```

### 性能基准（热缓存命中时）
| 操作 | 耗时 | 说明 |
| :--- | :---: | :--- |
| 只读查询 | **~0.1s** | 索引 O(1) 定位，无网络请求 |
| 单行写回 | **~0.3s** | WebSocket 连接 + 发送 + 确认 |
| 10 行批量写回 | **~1.5s** | 逐条发送 + 100ms 间隔防限流 |
| 首次 API 拉取 | **~16s** | 44MB 数据，仅首次或缓存过期时触发 |

### 可靠性保障
1. **WebSocket 直链**：`wss://.../table/websocket/{tableId}` 通信通道，服务端回包 `code: 1` 确认落库
2. **热缓存加速**：全量行映射索引缓存至 `~/.cache/adjust-plandate/`（TTL 2 小时）
3. **登录兜底**：API 登录 → Playwright 浏览器登录（双重保障）
4. **Session 持久化**：JWT token 存盘复用，12h 内免登录

---

## ⚠️ 已知问题与避坑指南（2026-09-08 实测沉淀，2026-09-09 v3.1 已自动修复）

> **v3.1 关键升级（2026-09-09）**：以下问题 1~3 已由脚本**自动修复**，无需再人工逐条补写。
> 1. 批量写回默认改为**逐条独立 WebSocket 连接**（`ws_update(per_item_connection=True)`），从源头规避单连接连续写入丢帧；
> 2. 校验**无条件执行**且改为**强制 `--no-cache` API 全量回读**，API 回读为空时判定为**未持久化**（不再乐观误报成功）；
> 3. 校验发现未落库 Story 后**自动逐条补写重试**（最多 3 轮），直至全部落库或达上限。
> 因此日常批量修改（含 4+ 条）直接执行 `SCRIPT_V3 PGxxxx yyyymmdd` 即可，脚本会自动保证落库。

### 问题 1：批量 WebSocket 写回可能丢数据（v3.1 已自动修复）
- **现象（历史）**：一次 WebSocket 连接写入多条 Story（如 6 条），服务端逐条返回 `code: 1` 确认，但实际仅部分落库（6 条仅成功 2 条）。
- **根因**：服务端 WebSocket 处理器对同一连接中的连续写入帧存在异步丢失，确认回包不代表数据库已持久化。
- **v3.1 修复**：写回默认改为**逐条独立连接**（每条单独建连→发送→确认→关闭），从根本上规避丢帧。

### 问题 2：热缓存会误报成功（v3.1 已自动修复）
- **现象（历史）**：脚本本地热缓存会在 WebSocket 写回后立即更新目标值，导致 `--verify` 读取缓存而非真实 API，误判全部成功。
- **v3.1 修复**：校验**无条件执行**，且强制 `--no-cache` 从 API 全量回读；API 回读为空时判定为**未持久化**（不再乐观误报成功）。`--verify` 参数已无实际作用（校验始终执行）。

### 问题 3：失败 Story 自动逐条补写（v3.1 已内置，无需人工）
- **v3.1 内置**：校验发现未落库 Story 后，脚本自动用独立连接逐条补写（最多 3 轮），每轮补写后重新 `--no-cache` 回读确认，直至全部落库。
- **人工兜底（仅当脚本自动补写仍失败时）**：
  ```bash
  python3 "$SCRIPT_V3" PGxxxx yyyymmdd --story-filter S260xxxxxx   # 逐条补写
  python3 "$SCRIPT_V3" PGxxxx yyyymmdd --no-cache                   # 全量确认
  ```
