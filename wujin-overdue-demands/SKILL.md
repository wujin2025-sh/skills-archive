---
name: wujin-overdue-demands
description: "一键统计我（吴进）受理的且是否逾期交付为「是」、且未上线（过滤已上线状态）的需求汇总明细。"
agent_created: true
---

# 我受理的逾期需求统计技能 (wujin-overdue-demands)

## 概述

直接调用金融科技平台后台列表接口，拉取吴进受理的（`myPutForward: 21`）且是否逾期交付为是（`isexceed: "是"`）的全部需求记录，过滤掉已上线的记录，快速输出到控制台或写入 Markdown 文件。

## 触发条件

当用户提问或指令中包含以下关键词时触发此技能：
- `我受理的逾期需求`
- `逾期未上线需求`
- `逾期交付统计`
- `wujin-overdue-demands`

## 使用方法

在工作空间中运行脚本：

```bash
.venv/bin/python /Users/wujin/.workbuddy/skills/wujin-overdue-demands/scripts/get_overdue_demands.py [-o <输出Markdown文件.md>] [--exclude-status <过滤排除的状态，多个用逗号隔开，默认已上线>]
```

### 示例

1. **直接输出到终端**：
   ```bash
   .venv/bin/python /Users/wujin/.workbuddy/skills/wujin-overdue-demands/scripts/get_overdue_demands.py
   ```

2. **输出并保存为 Markdown 文件**：
   ```bash
   .venv/bin/python /Users/wujin/.workbuddy/skills/wujin-overdue-demands/scripts/get_overdue_demands.py -o /Volumes/Macintosh\ HD_Data/WorkBuddy/需求管理/overdue_summary.md
   ```

3. **不排除任何状态（显示全部 26 个需求）**：
   ```bash
   .venv/bin/python /Users/wujin/.workbuddy/skills/wujin-overdue-demands/scripts/get_overdue_demands.py --exclude-status None
   ```

## 注意事项

- 本技能复用统一的 `.fintech_session.json`。如遇登录态超时失效，请先运行其他带 headed 模式物理登录的技能重新获取 session token。
- 过滤后数据默认按需求编号倒序排列。
