---
name: wujin-demand-filter
description: "根据输入的计划生产排期日期，筛选大宽表中需求受理人含吴进的需求列表。共享大宽表本地热缓存（.sheet_rows_cache.pkl），命中热缓存时 0.17s 秒级响应，支持 API 及 Playwright 智能多层兜底。"
agent_created: true
allowed-tools:
  - Bash
  - Read
  - Write
---

# 计划生产排期下吴进需求筛选技能 (wujin-demand-filter)

⚡ **极速性能**：接入 `gtht-skills` 的大宽表共享热缓存 (`~/.local/share/gtht/.sheet_rows_cache.pkl`)。命中热缓存时仅需 **0.17 秒** 即可完成秒级筛选与 Markdown / 卡片 HTML 汇总呈现。

---

## 📌 触发场景

- 当用户询问：“筛选吴进的需求排期”、“查询吴进在某天的上线计划/排期需求”时触发。
- 触发词：吴进排期、筛选吴进需求、吴进需求排期、wujin-demand-filter。

---

## 🚀 使用方法

执行筛选命令（建议设置 `BypassSandbox: true`）：

```bash
# 1. 优先使用 gtht-skills 热缓存/极速脚本 (0.17s 响应)
python3 "/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/gtht-skills/gtht-demand-fetch/scripts/schedule_fast.py" --prewarm

# 2. 运行本地筛选脚本
.venv/bin/python filter_wujin_demands.py <计划生产排期日期> -t [--output result.md] [--html]
```

### 参数说明

- **计划生产排期日期**（必填）：标准格式（`YYYY-MM-DD`，如 `2026-07-24`）或简写格式（`YYYYMMDD`，如 `20260724`）。
- `-t` / `--table-only`（强烈推荐）：仅向终端输出纯干净表格内容，无日志干扰。
- `--output` / `-o`：指定 Markdown 结果文件的输出路径。
- `--html`：同时生成卡片式 HTML 可视化文件。

---

## ⚙️ 多级加速与防御工作流

1. **Layer 1 (共享热缓存 0.17s)**：读取 `~/.local/share/gtht/.sheet_rows_cache.pkl`，按 `planProdLineDate` 与 `acceptanceUser` 秒级匹配；
2. **Layer 2 (API 增量刷新 2-3s)**：热缓存过期或检测到数据变动时，通过 API 免浏览器获取增量；
3. **Layer 3 (Playwright 无头登录兜底)**：鉴权过期时自动无头登录补全 Session；
4. **Layer 4 (物理导出兜底)**：极端情况下导出表格并用 Python 数据引擎解析。

---

## 📊 最佳输出策略

- **极速干净输出**：直接发起 `run_command` 执行脚本（带 `-t` 选项）；
- **输出格式**：终端直接呈现标准 Markdown 汇总表格，无需任何冗余的前后解说文字。
