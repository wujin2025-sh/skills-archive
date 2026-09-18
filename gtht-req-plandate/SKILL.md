---
name: 调整需求计划交付时间
description: '调整国泰海通金融科技平台需求管理中的「需求预计上线时间」与「需求预计交付验收时间」两个字段。支持按需求编号（R26xxxxxxx）或史诗编号（E/PG 开头）批量修改。基于 adjust-plandate 的「修改排期」弹窗逻辑，自动打开需求详情页 → 点击「修改排期」→ 在「需求排期确认」弹窗中修改两个日期字段并提交保存，支持 Session 免登录态复用、单会话批量执行、幂等跳过。参考 adjust-plandate skill 实现。

  触发词：调整需求计划交付时间、修改需求交付时间、调整需求交付验收时间、修改需求预计上线时间、修改需求预计交付验收时间、需求排期修改、需求交付时间、gtht-req-plandate、Rxxxx 修改交付时间、史诗 修改交付时间。'
disable: false
---


# 调整需求计划交付时间

## 概述

访问国泰海通金融科技平台「需求管理」详情页，点击右上角「修改排期」按钮，在「需求排期确认」弹窗中自动修改 **「需求预计交付验收时间」** 与 **「需求预计上线时间」** 两个字段，并提交保存，支持 Session 免登录态复用。

> 📌 **与 adjust-plandate 的区别**：`adjust-plandate` 修改的是 **Story 级「计划生产排期」**（大宽表 WebSocket 直连）；本技能修改的是 **需求级「预计上线时间 / 预计交付验收时间」**（需求详情页「修改排期」弹窗，Playwright 交互）。

本技能支持以下模式：
1. **单笔修改模式**：指定单个需求编号（形如 `R2607150083`），精准修改其两个日期字段。
2. **史诗批量修改模式**：指定史诗编号（形如 `E2603040001` 或 `PG202204-0259`），系统自动通过史诗管理 API 获取该史诗下所有关联需求，并在同一个浏览器会话中顺序完成批量修改。

## 触发条件

当用户提及以下关键词或意图时使用本技能：
- **调整需求计划交付时间**、**修改需求交付时间**
- **调整需求交付验收时间**、**修改需求预计上线时间**、**修改需求预计交付验收时间**
- **需求排期修改**（针对需求级字段，非 Story 计划生产排期）
- 提供需求编号或史诗编号并要求调整交付/上线时间，如：
  - `调整 R2607150083 的交付时间为 20261031`
  - `修改 PG202204-0259 下所有需求的预计上线时间为 20261031`
  - `把史诗 E2603040001 的需求交付验收时间改为 2026-10-31`

## 使用方法

脚本位于 `scripts/edit_req_plandate.py`，在含 playwright 的工作虚拟环境中运行：

```bash
.venv/bin/python /Users/wujin/.workbuddy/skills/gtht-req-plandate/scripts/edit_req_plandate.py <需求编号/史诗编号> <目标交付验收日期> [目标上线日期] [--headed]
```

### 参数说明

| 参数 | 必填 | 说明 |
| :--- | :---: | :--- |
| `<需求编号/史诗编号>` | **是** | 需求编号 `R2607150083` 或史诗编号 `PG202204-0259` / `E2603040001` |
| `<目标交付验收日期>` | **是** | 目标「需求预计交付验收时间」，支持 `20261031` / `2026-10-31` / `2026/10/31` |
| `[目标上线日期]` | 否 | 目标「需求预计上线时间」，缺省时与交付验收日期相同 |
| `--headed` | 否 | 显示浏览器窗口（调试用） |

### 示例

- 修改单个需求 `R2607150083` 的交付验收与上线时间均为 `20261031`：
```bash
.venv/bin/python /Users/wujin/.workbuddy/skills/gtht-req-plandate/scripts/edit_req_plandate.py R2607150083 20261031
```

- 分别指定交付验收时间与上线时间：
```bash
.venv/bin/python /Users/wujin/.workbuddy/skills/gtht-req-plandate/scripts/edit_req_plandate.py R2607150083 2026-10-31 2026-11-05
```

- 批量修改史诗 `PG202204-0259` 下所有需求的交付验收与上线时间：
```bash
.venv/bin/python /Users/wujin/.workbuddy/skills/gtht-req-plandate/scripts/edit_req_plandate.py PG202204-0259 20261031
```

## 技术细节

- **史诗枚举**：对于史诗编号输入，先从已存 Session 提取 Token 及 Cookies，通过 `listAllByExamples` 获取史诗内部 ID，再用 `demand-service/demandsub/list`（`epicIds` 参数）拉取该史诗下全部关联需求 ID；失败时降级为大宽表 `getSheetContent` 的 `epicConcat` 扫描兜底。
- **单会话批量执行**：Playwright 启动后一次性遍历所有待修改需求 ID 进行页面导航与修改，复用浏览器实例，最大限度提升批量修改效率。
- **日期输入自适应**：先填上线时间再填交付验收时间（Order 1），若前端最大/最小日期范围校验导致未生效，自动切换为 Order 2（先交付验收后上线），绕过校验。
- **幂等跳过**：弹窗内比对当前值与目标值，若两个字段均已等于目标值则跳过提交，避免重复网络请求。
- **登录兜底**：Session 文件存在则复用；不存在则自动登录并保存。

## 依赖与环境

- Python + `playwright`、`requests`（建议使用 `.workbuddy/binaries/python/envs/default/bin/python3` 或技能自带 `.venv`）
- 凭据：`config.json`（`username` / `password`），支持明文或 `password_encrypted` 加密
- Session：`.fintech_session.json`（自动复用，12h 内免登录）