---
name: wujin-focus-demands
description: 根据大宽表数据，提取吴进名下的重点关注需求，并自动同步到腾讯文档「重点需求」子表（同一史诗需求集中连续排列，史诗编号列按组自动合并单元格，整表无变化零写入幂等）。支持大宽表 API 高速匹配、本地缓存兜底以及通过
  tencent-docs MCP 与腾讯文档进行双向通信。
disable: false
---


# 吴进重点需求提取与同步技能

## Overview

在金融科技平台中，提取受理人含 `吴进` 且 `重点关注`（keyFocus）为 `是` 且 `需求状态` 不为 `已上线` 的需求，并与在线腾讯文档进行整表同步：以「史诗编号优先」对全部记录（存量+新增）分组重排，同一史诗的需求集中连续排列，并对 A 列（史诗编号列）按连续区间自动合并单元格；已上线需求经全量重写自然剔除。写入目标：腾讯文档 `https://docs.qq.com/sheet/DVGtPSXpzWU1zYXNi?tab=ku4w5u` 的 `重点需求` 子表。整表无变化时零写入（幂等）。

## When to Use

- 当用户提出“同步吴进的重点需求”、“提取吴进重点需求到腾讯文档”、“同步重点关注需求”等指令时触发。
- 触发词：吴进重点需求、重点关注需求、wujin-focus-demands。

## Usage

执行同步脚本即可：

```bash
/Volumes/Macintosh\ HD_Data/WorkBuddy/需求管理/.venv/bin/python /Volumes/Macintosh\ HD_Data/WorkBuddy/需求管理/get_focus_demands.py
```

### 功能特点

1. **自动清理上线需求（全量重写剔除）**：自动识别腾讯文档中已经是“已上线”或者在宽表中最新状态更新为“已上线”的需求，**通过全量覆盖写重排时自然剔除**（不占用单独删除步骤）；当新内容行数小于旧表行数时，用 `sheet.delete_dimension(dimension_type="ROWS")` 从底往顶清理残留尾部行，**切勿使用 `sheet.operation_sheet` + `deleteRow()`**（该方式存在已知静默失败限制：`deleteRow may have silently failed`，腾讯文档 MCP 返回 error code 999 但脚本无法感知，导致已上线需求残留）。
2. **史诗分组排序与自动去重**：读取腾讯文档已有记录，构建「存量 + 宽表重点」完整记录列表后，按 **史诗编号优先** 排序（同一史诗集中连续，无史诗排最后；组内按计划排期升序，未排期排最后；最后按需求编号升序）。存量行保留（防误删人工记录），宽表重点数据覆盖/补全进度、排期、史诗字段，新需求自动纳入；A-G 全列从 row=1 覆盖写入实现重排。
3. **高保真单元格超链接**：写入腾讯文档时，会对需求详情 URL 进行高保真超链接配置（调用 `sheet.set_link`），让用户可在文档中直接点击打开 Fintech 详情页。
4. **高速 API 及缓存兜底**：大宽表数据的拉取首先尝试使用平台高速 API。如果鉴权失效或网络不通，会自动读取 `/Volumes/Macintosh HD_Data/WorkBuddy/需求管理/.table_cache.json` 进行本地兜底，确保在任何情况下脚本均能正常工作。
5. **mcporter 代理自动注入**：`run_mcp_command` 已内置 `NODE_USE_ENV_PROXY=1` + 系统 Wi-Fi 代理注入（自动探测 `networksetup -getwebproxy Wi-Fi`，兜底 `http://172.16.0.11:3128`）。原因：公司网络封锁 `docs.qq.com` 直连，且 Node fetch 默认不读代理环境变量；浏览器能访问是因为走系统 Wi-Fi 代理，而命令行需要显式注入。若换网络环境后失败，可用 `MCPORTER_PROXY` 环境变量显式指定代理地址。
6. **史诗列合并单元格**：对 A 列按排序后的连续相同史诗区间执行 `sheet.merge_cell` 合并（合并结果示例 `A2:A13`），同一史诗整组只保留左上角值，形成按史诗分组的干净视觉区块；写入前先解聚旧合并单元格（`sheet.get_merged_cells` + `sheet.unmerge_cell`），保证每次重排后合并区间与最新数据一致。⚠️ 坐标语义：`merge_cell` 的 `start_row/end_row` 为 **0-based** 行索引（实测：请求 `start_row=1` → 合并结果为第 2 行起 `A2:A13`），与 `get_cell_data/set_range_value/delete_dimension/unmerge_cell` 一致。
7. **幂等零写入**：重排前执行**合并感知**的逐行比对（行数、需求编号、史诗区间首行值、进度、计划排期；A 列区间内行期望为空），与腾讯文档当前内容完全一致时直接返回零写入，避免全量重写耗时。

## 字段映射关系

追加写入腾讯文档的列对齐格式如下：
- **A列**：史诗编号（例如：`PG202204-0267`；同一史诗连续多行按区间合并单元格，仅区间首行显示值）
- **B列**：需求编号（例如：`R2603060001`）
- **C列**：需求链接（例如：`https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId=Rxxxx&templateId=8888&flag=1`，配置超链接）
- **D列**：需求名称
- **E列**：进度（对应大宽表的 `demandStatus`，如 `UAT自测中`）
- **F列**：计划排期（转换为 `YYYYMMDD` 格式，如 `20260807`）
- **G列**：备注（对应大宽表的 `beizhuText`）
