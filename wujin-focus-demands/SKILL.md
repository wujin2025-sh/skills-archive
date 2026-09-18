---
name: wujin-focus-demands
description: 根据大宽表数据，提取吴进名下的重点关注需求，并自动同步追加到腾讯文档「重点需求」子表。支持大宽表 API 高速匹配、本地缓存兜底以及通过
  tencent-docs MCP 与腾讯文档进行双向通信。
disable: false
---


# 吴进重点需求提取与同步技能

## Overview

在金融科技平台中，提取受理人含 `吴进` 且 `重点关注`（keyFocus）为 `是` 且 `需求状态` 不为 `已上线` 的需求，与在线腾讯文档进行比对。自动删除腾讯文档中已上线的存量需求，并把缺少的重点需求追加写入到腾讯文档 `https://docs.qq.com/sheet/DVGtPSXpzWU1zYXNi?tab=ku4w5u` 的 `重点需求` 子表中。

## When to Use

- 当用户提出“同步吴进的重点需求”、“提取吴进重点需求到腾讯文档”、“同步重点关注需求”等指令时触发。
- 触发词：吴进重点需求、重点关注需求、wujin-focus-demands。

## Usage

执行同步脚本即可：

```bash
/Volumes/Macintosh\ HD_Data/WorkBuddy/需求管理/.venv/bin/python /Volumes/Macintosh\ HD_Data/WorkBuddy/需求管理/get_focus_demands.py
```

### 功能特点

1. **自动清理上线需求**：自动识别腾讯文档中已经是“已上线”或者在宽表中最新状态更新为“已上线”的需求行，并从表格中自动删除。使用 `sheet.delete_dimension(dimension_type="ROWS")` 进行可靠的行删除，**切勿使用 `sheet.operation_sheet` + `deleteRow()`**（该方式存在已知静默失败限制：`deleteRow may have silently failed`，腾讯文档 MCP 返回 error code 999 但脚本无法感知，导致已上线需求残留）。
2. **自动去重比对**：读取腾讯文档已有的记录，差量找出新产生的重点需求进行追加。
3. **高保真单元格超链接**：写入腾讯文档时，会对需求详情 URL 进行高保真超链接配置（调用 `sheet.set_link`），让用户可在文档中直接点击打开 Fintech 详情页。
4. **高速 API 及缓存兜底**：大宽表数据的拉取首先尝试使用平台高速 API。如果鉴权失效或网络不通，会自动读取 `/Volumes/Macintosh HD_Data/WorkBuddy/需求管理/.table_cache.json` 进行本地兜底，确保在任何情况下脚本均能正常工作。
5. **mcporter 代理自动注入**：`run_mcp_command` 已内置 `NODE_USE_ENV_PROXY=1` + 系统 Wi-Fi 代理注入（自动探测 `networksetup -getwebproxy Wi-Fi`，兜底 `http://172.16.0.11:3128`）。原因：公司网络封锁 `docs.qq.com` 直连，且 Node fetch 默认不读代理环境变量；浏览器能访问是因为走系统 Wi-Fi 代理，而命令行需要显式注入。若换网络环境后失败，可用 `MCPORTER_PROXY` 环境变量显式指定代理地址。

## 字段映射关系

追加写入腾讯文档的列对齐格式如下：
- **A列**：史诗编号（例如：`PG202204-0267`）
- **B列**：需求编号（例如：`R2603060001`）
- **C列**：需求链接（例如：`https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId=Rxxxx&templateId=8888&flag=1`，配置超链接）
- **D列**：需求名称
- **E列**：进度（对应大宽表的 `demandStatus`，如 `UAT自测中`）
- **F列**：计划排期（转换为 `YYYYMMDD` 格式，如 `20260807`）
- **G列**：备注（对应大宽表的 `beizhuText`）
