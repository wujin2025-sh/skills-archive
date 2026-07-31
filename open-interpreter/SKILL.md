---
name: open-interpreter
description: Open Interpreter 技能。一个可以让大语言模型（LLM）在你本地计算机上运行代码（Python, Bash, Shell 等）来完成任务的开源项目。当用户需要执行涉及本地系统控制、文件批量处理、自动化操作或提到 open-interpreter 时触发。
---

# Open Interpreter 技能

这个技能封装了著名的 GitHub 开源项目 `OpenInterpreter/open-interpreter`。该项目的源码已经下载至 `~/.workbuddy/skills/open-interpreter/repository`。

**Open Interpreter** 允许大语言模型在本地环境中直接执行代码（如 Python、JavaScript、Shell 等），从而实现各种自动化任务、系统配置、文件处理和数据分析。

## 一、作为助手如何使用它

作为一个具有运行终端命令 (`run_command`) 权限的 Agent，你**本身就具备类似 Open Interpreter 的能力**（即：编写代码、执行终端命令、查看结果并迭代）。
当用户请求“使用 open-interpreter 完成 XXX 任务”时，你可以直接利用你自带的工具（如 `write_to_file`, `run_command`）来编写脚本并在用户的机器上运行，从而完成自动化任务。

## 二、如何指导用户直接运行 Open Interpreter CLI

如果用户明确希望在终端中启动官方的 `interpreter` 交互式命令行，你可以指导他们进行安装和运行：

1. **环境准备**：建议用户使用 Python 虚拟环境（如 conda 或 venv）。
2. **安装**：
   ```bash
   pip install open-interpreter
   ```
3. **启动运行**：
   在终端输入：
   ```bash
   interpreter
   ```
4. **配置大模型**：
   在启动后，用户会被提示配置大模型的 API Key（如 OpenAI、Anthropic、本地模型等）。
   如果用户想直接使用特定的本地模型，可以使用：
   ```bash
   interpreter --local
   ```

## 三、典型应用场景示例

无论是用户自己运行 `interpreter` CLI，还是由你（Agent）代劳，这类工具擅长处理以下任务：
- **系统自动化**：自动整理桌面文件、批量修改文件名、调整系统设置（如深色模式）。
- **数据处理**：读取 Excel/CSV 文件，进行数据清洗、绘图，并保存结果。
- **Web 自动化**：编写脚本抓取网页信息，或通过 Playwright/Selenium 进行自动化测试。
- **环境配置**：一键安装开发依赖、配置特定的环境变量。

> **注意**：执行未知或生成的代码前，请务必确保代码是安全的，或者提醒用户审核代码。
