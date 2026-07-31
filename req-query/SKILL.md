---
name: 需求查询
description: |
  金融科技平台需求管理列表页查询工具。访问 fintech.gtht.com.cn/kjpt/DemandManage/main，通过搜索框查询需求编号，提取核心需求要素（标题、级别、状态、提出人、经办人等）输出到对话框，并在 headed 模式下打开需求详情页。
  触发词：需求查询、查需求、Rxxxx、需求编号、需求管理、req_query、req-query。
agent_created: true
---

# 需求查询

## 概述

访问国泰海通金融科技平台「需求管理」列表页，通过编号精确查询需求，提取核心要素并输出，同时打开需求详情页供查看。

## 触发条件

当用户提及以下关键词时使用本技能：

- 需求查询、查需求、查询需求、req_query、req-query
- 提供需求编号格式如 `R2605250074`
- 需求管理、需求列表

## 工作流程

1. **登录检查** — 复用 `.fintech_session.json` session，有效期内跳过登录
2. **全局搜索** — 在页面右上角顶部搜索框（placeholder「搜索需求、Story、Task、Bug...」）输入需求编号，按 Enter 跳转到 `/kjpt/globalSearch`
3. **精确匹配** — 全局搜索页自动精确匹配（返回1条），脚本前端二次校验编号列
4. **提取要素** — 从表格行提取：标题、级别、提出人、提出部门、期望上线时间、受理人、状态、OA审批状态
5. **并行查询** — 同时启动大宽表查询和详情页加载（两个独立 Page + `asyncio.gather`），大宽表提取「计划生产排期」和「备注」，详情页提取 Story 列表
6. **合并输出** — 将大宽表的计划生产排期和备注按系统名匹配到对应 Story，格式化输出

## 使用方法

脚本位于 `scripts/req_query.py`，在工作目录运行：

```bash
python3 scripts/req_query.py <需求编号>           # 默认无头模式（极速输出）
python3 scripts/req_query.py <需求编号> --headed # 有头模式（保持浏览器打开）
```

示例：
```bash
python3 scripts/req_query.py R2604090033
```

### 环境要求

- Python 虚拟环境 `.venv/` 中需安装 `playwright`
- Playwright Chromium 已安装
- 使用 `--headed` 模式时显示浏览器窗口并打开详情页

### 输出格式

对话窗口输出示例：

```
**需求查询　|　R2605250074**

　　**标题**：【业务需求】批量余券划转（当日）菜单优化
　　**级别**：P4
　　**状态**：技术评估
　　**OA状态**：已提交

　　**提出人**：郑磊
　　**提出部门**：营运管理部
　　**受理人**：钟贵福
　　**期望上线时间**：2026-06-08

　　**关联 Story（1 条）**
　　　　**1. S2604130028** — Story名称
　　　　　　状态：Story状态 | IT评估：已评估
　　　　　　系统：集中交易系统 | 工程排期：20260529 | 计划生产排期：2026-06-12
　　　　　　开发负责人：xxx | SIT负责人：xxx
　　　　　　计划交付：2026-06-05 | 发布日期：--
　　　　　　备注：涉及交易新规，6月份上线

　　**详情页**：https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId=R2605250074&templateId=8888&flag=1
```

## 技术细节

- **Session 复用**：所有 fintech 技能（需求查询、大宽表查询、版本排期过滤等）统一使用 `/Volumes/Macintosh HD_Data/WorkBuddy/需求管理/.fintech_session.json`，登录有效期内跨技能自动跳过登录
- **登录判断逻辑**：`ensure_login()` 先访问目标页面，若 URL 不含 `login` 则判定已有登录态，直接跳过；否则执行登录并保存 session
- **搜索方式**：页面右上角顶部全局搜索框（`input[placeholder*="搜索需求"]`），按 Enter 跳转到 `/kjpt/globalSearch`，该页面自动精确匹配
- **表格组件**：全局搜索页和详情页使用 Ant Design Table（非 AG Grid）
- **大宽表**：使用 AG Grid 组件，搜索框 `#filter-text-box` 会约7秒自动清空，需用 `.type()` 逐字符输入。通过 `col-id` 属性匹配列名，按需求编号过滤数据行，提取「Story系统」「计划生产排期」「备注」三列
- **数据合并**：大宽表数据按「Story系统」与详情页 Story 的「所属系统」进行模糊匹配（双向子串包含）
- **详情页 URL**：`/kjpt/DemandManage/details?demandId={编号}&templateId=8888&flag=1`
- **Story 表格**：详情页第一个 ant-table（表头含「Story编号」），使用动态列映射（`_build_col_index`）从实际 th 文本构建字段索引，兼容表头列顺序变化

## 前置依赖

```bash
pip install playwright
playwright install chromium
```

## 注意事项

- 登录凭据硬编码在脚本配置区，妥善保管
- 全局搜索页自动精确匹配，无需前端二次过滤（脚本仍做校验）
- **大宽表查询在并行中执行，失败时静默降级**（不显示计划生产排期和备注）
- headed 模式下浏览器保持打开，按 Enter 关闭
- **异步架构**：使用 `async_playwright`，大宽表和详情页通过 `asyncio.gather` 并行执行，显著缩短总耗时
- **智能等待**：使用 `wait_for_url`、`wait_for_selector`、`wait_for_function` 替代固定 `time.sleep` 轮询
