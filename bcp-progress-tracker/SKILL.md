---
name: bcp-progress-tracker
description: 集中交易历史数据bcp文件迁移专项项目进度提取和提醒邮件生成工具。触发词：BCP文件迁移、集中交易历史数据bcp文件、BCP进度跟踪、BCP提取。
---

# BCP Progress Tracker Skill (集中交易历史数据BCP文件迁移项目进度跟踪技能)

## 技能介绍
本技能用于快速下载集中交易历史数据bcp文件迁移的在线 Excel 电子表格，解析各下游系统的在用表及适配进度，生成本地 Obsidian Markdown 进度报告。
用户可在 Obsidian 中自由复核、修改邮件正文、收件人及抄送人信息。核对完成后，通过“发邮件”指令触发邮件自动起草流程，极速在 Coremail 草稿箱中保存草稿。

## 工作流与执行指令 (Workflow & Run Commands)

### 阶段一：进度提取与本地建档（执行 `/bcp-progress-tracker`）
当接收到 `/bcp-progress-tracker` 指令或用户要求提取 BCP 进度时，按顺序执行以下指令：
1. **下载在线电子表格**：
   ```bash
   python3 "/Volumes/Macintosh HD_Data/WorkBuddy/邮件发送/.agents/skills/bcp-progress-tracker/scripts/download_workbook.py"
   ```
2. **解析并编译为 Obsidian 报告**：
   ```bash
   python3 "/Volumes/Macintosh HD_Data/WorkBuddy/邮件发送/.agents/skills/bcp-progress-tracker/scripts/parse_workbook.py"
   ```
   *生成的文档位置：`/Volumes/Macintosh HD_Data/obsidian/100_Projects/进度跟踪/YYYYMMDD-进度-集中交易历史数据BCP文件迁移项目下游系统适配进度跟踪.md`*
3. **响应用户**：告诉用户已完成本地建档，引导其前往 Obsidian 进行审阅和修改。

---

### 阶段二：审阅确认与自动起草（执行 `发邮件`）
当用户完成 Obsidian 报告的复核并输入“发邮件”或“发送邮件”时：
1. **自动从 Markdown 解析邮件并起草**：
   执行以下脚本，它会自动寻找并读取 Obsidian 目录下最新修改的报告文件，解析出您调整后的主题、收件人、抄送人及正文，并调用 Playwright 代理在 Coremail 中保存为草稿：
   ```bash
   python3 "/Volumes/Macintosh HD_Data/WorkBuddy/邮件发送/.agents/skills/bcp-progress-tracker/scripts/draft_email_from_md.py"
   ```
   *(如果需要直接发送邮件而非存入草稿箱，可追加 `--send` 参数：`python3 .../draft_email_from_md.py --send`)*
2. **响应用户**：提示草稿保存成功，指出收发人员明细及最终生成路径。
