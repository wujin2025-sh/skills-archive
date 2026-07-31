---
name: project-schedule
description: "批量查询多个需求编号，在后台并行获取它们的所有 Story 详情及进度信息，然后合并生成一个带 HTML 单元格合并效果的项目进度表（HTML & Markdown 格式）。支持传入多个以空格分隔的需求编号。"
allowed-tools:
  - Bash
  - Read
  - Write
---

# 项目进度表生成器

## Overview

该 Skill 能够批量、并行地对多个需求编号（如 R2603130062 R2603110056）进行详细查询，从金融科技平台提取所有关联的 Story 状态、各系统负责人及交付排期，自动生成格式美化、带有需求编号单元格合并的项目进度跟踪表。支持输出为自包含的 HTML 表格文件以及 Markdown 文本。

## When to Use

- 用户提供了多个需求编号，要求整理一份统一的项目进度表用于邮件发送或干系人汇报。
- 触发词：进度表、项目进度、批量查询、生成进度表、合并表格。

## Usage

执行脚本，传入一个或多个以空格分隔的需求编号或史诗编号：

```bash
.venv/bin/python scripts/project_schedule_generate.py <需求ID_或_史诗ID_1> <需求ID_或_史诗ID_2> ... [--project 项目名称] [--output_html html路径] [--output_md md路径]
```

### 需求看板可视化

执行脚本，传入单个需求编号以生成精美看板长图及网页：

```bash
.venv/bin/python scripts/visualize_demand.py <需求ID>
```

#### 可视化产物说明
- `visualize_<需求ID>.html`：自包含的可视化网页。
- `visualize_<需求ID>.png`：高分辨率看板截图长图。

### 参数说明

- **需求ID/史诗ID**（至少一个）：以空格分隔的需求编号（如 R2603130062）或史诗编号（如 PG202204-0236）列表。如果传入史诗编号，系统将自动连接大宽表并提取出该史诗下所有关联的需求编号。
- `--project`：项目名称（默认："交易结算核心历史数据及接口迁移项目"）
- `--output_html`：生成的 HTML 表格保存路径（默认：`{日期}-进度-{项目名称}.html`）
- `--output_md`：生成的 Markdown 表格保存路径（默认：`{日期}-进度-{项目名称}.md`）
- **自动同步**：Markdown 格式文件生成时，脚本将自动在 `/Volumes/Macintosh HD_Data/obsidian/100_Projects/进度跟踪/` 目录下同步写入一份 `{日期}-进度-{项目名称}.md`。

### 环境要求与凭证配置

- **凭据配置**：其他用户使用前，可以在 Skill 目录下的 `config.json` 中配置自己的平台登录 `username`（明文工号）和密码。
  - **明文配置**：可以直接在 `config.json` 里的 `"password"` 字段配置您的明文密码。
  - **加密配置 (推荐)**：为了防止分享/复制 Skill 给别人使用时泄漏密码，可以运行以下命令交互式输入并加密密码：
    ```bash
    python scripts/encrypt_pwd.py
    ```
    它会将您的密码加密为密文写入 `password_encrypted` 字段，并清除明文 `password` 字段。
- Python 虚拟环境 `.venv/` 中需安装 `playwright`
- 项目根目录下存在公用的 session 文件 `.fintech_session.json`
- 并行最大并发数默认不限制（通过 asyncio.gather 并行执行）

### 工作流程

1. 启动脚本，解析输入的多个需求 ID。
2. 并行调用 `scripts/req_query.py` 子进程对每个需求执行查询，抓取最新的 Story 明细并输出为中间 Markdown 文件 `result_<需求ID>.md`。
3. 自动扫描并解析生成的所有 `result_<需求ID>.md` 文件，利用正则表达式提取出各个需求及其 Story 的结构化数据：
   - 需求编号、标题、级别、当前状态、期望上线时间
   - Story 编号、任务标题、涉及系统、开发负责人、SIT 负责人、测试/开发状态、计划交付时间
4. 对提取的交付时间与当前系统时间（2026-06-10）进行比对，若未完成且交付时间已过，自动将其风险状态标记为 `⚠️ 高 (已逾期)`；已结束的任务标记为 `✅ 已完成`。
5. 自动生成自包含、带有 `rowspan` 单元格合并的 HTML 进度表（默认保存为 `project_schedule.html`），可直接用浏览器打开或复制进邮件中发送。
6. 自动生成对应的 Markdown 格式的进度表（默认保存为 `project_schedule.md`）。

## 注意事项

- 依赖于同级目录下的 `scripts/req_query.py` 脚本执行底层查询，请确保两个脚本均正常打包。
- 该 Skill 会自动在后台以并发形式执行 Playwright 浏览器，请确保网络及 Fintech 平台 session 可达。
