---
name: spb-export
description: |
  国泰海通 fintech 平台 SPB 版本发布自动化工具。从平台自动导出 Excel，按计划生产排期和版本排期筛选，生成主文件、增量报告、备份，自动清理历史版本文件，全量+增量双模式执行并以升序且无注释符号导出 Task编号及其它 10 项模板处理输出 TXT。
  触发词：SPB、导出、版本排期、计划生产排期、集中交易平台持续建设、SPB_V2.2.19、auto_spb_export、jzjy、20260xxx。
agent_created: true
---

# SPB & CSZX 版本发布自动化导出

## 概述

自动化完成国泰海通 fintech 平台「集中交易平台持续建设项目」（SPB/jzjy）与「参数中心持续建设」（CSZX/jygl）的版本发布数据导出与模板处理工作。

## 触发条件

当用户提及以下关键词时使用本技能：

- 版本号格式为 `20260xxx`（8 位数字）且涉及 SPB、集中交易、参数中心或版本排期
- 要求导出、抓取、筛选 fintech 平台数据
- 提及 SPB_V2.2.19、jzjy 目录或 cszx、jygl 目录
- 要求生成 CLI / DLL / Table / Proc / Init 等模板处理报告

## 功能特征与优化

1. **高效无头模式 (Playwright Headless Mode)**:
   - 全流程运行于无浏览器界面的 Headless 模式下，节约系统资源，并集成了图片、媒体与字体请求拦截器，大幅提高页面加载与文件下载的速度。
   - 内置 Chromium 启动异常自动降级机制，若 Chrome 启动失败，将自动降级使用默认 Chromium。

2. **安全凭据保护 (Credentials Decryption)**:
   - 代码中无明文密码。脚本内置 `decrypt_password()` 逻辑，在执行时自动读取本机密钥文件 `~/.workbuddy/.meeting_skill_key` 并通过 cryptography (Fernet) 解密出密码，确保密码安全。

3. **双模式过滤与增量对比**:
   - 自动备份上一版本。每次运行会与备份的主文件进行比对，若检测到新增 Task 则将其单独记录至 `_upt.xlsx` 增量报告并生成对应的增量模板文件 `upt_excel_output.txt`。

4. **模板处理输出特征**:
   - **Task编号 详细映射**：升序且去除了注释前缀，自动生成包含经办人工号与名称的映射详情。
   - **ProcAdd 账号后缀**：在 `ProcAdd` 列对应的 `proc_list` 中，生成的账号名称尾部自动加上 `_new`（如 `shilibinJZJYPT-T202606586_new`）。
   - **备注与升级备注 Task前缀**：`升级备注` (UpgradeRemark) 与 `备注` (Remark) 部分的每一行自动在首部添加其对应的 `Task编号` 并留空双制表符（如 `CSZXCXJS-T202601392      在17：00前提前升级`），以便溯源。

## 使用方法

### JZJY (集中交易/SPB)
- 脚本路径: `jzjy/auto_spb_export.py` (技能脚本副本在 `scripts/auto_spb_export.py`)
- 运行指令 (计划生产排期 = 版本排期):
  ```bash
  python auto_spb_export.py 20260710
  ```
- 运行指令 (计划生产排期 与 版本排期 不同):
  ```bash
  python auto_spb_export.py 20260710 20260710_upt
  ```

### CSZX (参数中心)
- 脚本路径: `jygl/auto_jygl_export.py`
- 运行指令:
  ```bash
  python auto_jygl_export.py 20260724
  ```

## 输出文件

| 文件 | 说明 |
|------|------|
| `{BASE_VERSION}_{版本号}.xlsx` | 筛选后主文件 |
| `{BASE_VERSION}_{版本号}_upt.xlsx` | 增量变动报告（仅包含新增 Task） |
| `{BASE_VERSION}_{版本号}_backup.xlsx` | 上一版本备份 |
| `excel_output.txt` | 全量模板处理结果 |
| `upt_excel_output.txt` | 增量模板处理结果（有新增数据时生成） |
