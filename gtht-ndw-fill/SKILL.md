---
name: gtht-ndw-fill
description: 国泰海通科技平台（fintech.gtht.com.cn）需求分析非开发工作量 (NDW / 价值量) 智能评估与独立登记技能。 支持结合
  `ba-to-dev` 需求分析结论根据系统复杂度智能评估价值量（人月），并在科技平台进行极速 API 直连登记（≤0.5s，幂等防重）。 强制前置校验 Story
  拆分状态，默认状态为「已完成」(status=2)，按半月工作日自动推断周期，并自动关联经办人主管评估人（周尤珠-106881）。 同时支持**版本排期工作量登记**
  （项目管理类 taskType=2，无需求关联）：输入 `20261009版本预排期`(默认0.3) / `20261009版本排期`(默认0.2) 自动登记
  【版本排期】标题 + 集中交易系统 + 关联人不变。 触发词：登记价值量、价值量评估、填写价值量、NDW填写、评估价值量、需求分析工作量、ba-to-dev价值量、版本排期登记、版本预排期登记。
disable: false
---


# 国泰海通需求分析价值量评估与登记技能 (gtht-ndw-fill)

结合需求复杂度与 `ba-to-dev` 分析结论，智能评估需求分析师 (BA) 的非开发工作量（NDW - Non-Developer Work / 价值量人月），并在国泰海通科技平台（fintech.gtht.com.cn）进行极速 API 直连登记。

> ⚡ **核心原则与规范**：
> - **【完全独立】**：所有依赖（`session.py`、`config.py`、`ndw_fill.py`）均内置于本技能目录，保持独立运行与集中管理；
> - **【默认已完成】**：非开发工作状态**默认为「已完成」(`status: 2`)**；
> - **【Story 前置强核验】**：登记前自动检查该需求下是否已拆分所属 Story。**若未拆分 Story，强制拦截跳过**，防止流程倒挂；
> - **【半月周期自动推断】**：
>   - **上半月填写（1~15日）**：开始时间 = **当月首个工作日**（如 `2026-08-03`），完成时间 = **填写日 + 5天**（如 `2026-08-19`）；
>   - **下半月填写（16~月末）**：开始时间 = **下半月首个工作日**（如 `2026-08-17`），完成时间 = **当月末工作日**（如 `2026-08-31`）；
> - **【主管评估人自动带出】**：经办人采用平台用户编号 `050599`（前端自动回显为 `吴进-125360`），系统自动通过 `/getEvaluatorInfo` 关联主管并回显为 **`周尤珠-106881`**；
> - **【API 极速直连】**：打后端 REST API（`task-service/nonDevTask/addNonDevTask`）秒级完成登记（≤0.5s）。

---

## 📌 目录架构与独立依赖

本技能完全自包含在 `~/.workbuddy/skills/gtht-ndw-fill/` 目录下：

```bash
~/.workbuddy/skills/gtht-ndw-fill/
├── SKILL.md                 # 技能规范与使用说明文档
└── scripts/
    ├── ndw_fill.py          # 非开发工作量核心登记脚本
    ├── ndw_stat.py          # NDW 价值量统计脚本（全量拉取+按状态/月份/系统/需求汇总）
    ├── session.py           # 平台 API 会话与自动鉴权
    └── config.py            # 凭据与全局环境配置
```

---

## 📊 价值量统计（ndw_stat.py）

统计当前经办人名下已登记的全部非开发工作量（任务接口 `getNonDevTaskList` 全量翻页，实测返回记录均为吴进-125360）：

```bash
# 全量统计（按状态/月份/系统/需求明细汇总）
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python3 \
  ~/.workbuddy/skills/gtht-ndw-fill/scripts/ndw_stat.py

# 输出原始 JSON（含每条记录全字段，供二次加工/导出）
... ndw_stat.py --json
```

- 统计口径：`taskType==1`（需求分析），价值量取 `reapplicationTaskValue`（人月）；
- 分页策略：默认 pageSize=100 逐页翻取至 total，上限 50 页；
- 无需指定经办人：接口按登录用户返回，实测 276 条全部为吴进-125360，无需 `--assign` 过滤。

---

## 📊 价值量 (人月) 推荐评估模型

当需求分析文档中未显式指定价值量时，系统根据需求的改造规模、涉及系统数量及复杂度进行智能评估：

| 需求规模与特征 | 涉及系统与复杂度表现 | 默认/推荐价值量 (NDW) |
| :--- | :--- | :---: |
| **多系统改造 / 跨系统联动（重点）** | **涉及 2 个及以上系统改造**（如：低延时+集中交易、集中交易+集中清算、柜台+参数中心等） | **默认 `0.5`**（复杂级可评估至 `0.6`~`0.8+`） |
| **标准单系统需求 / 功能新增 / 接口调整** | 1 个改造系统，含标准业务逻辑、接口或参数修改 | **默认 `0.3`** |
| **小型 / 缺陷修复 / 纯配置修改** | 1 个改造系统，无外围联测，单表字段增减或前端微调 | **`0.1` ~ `0.2`** |


---

## 🚀 两种主要使用模式

### 模式一：`ba-to-dev` 需求文档自动化联动（最常用推荐）

当用户完成 `ba-to-dev` 需求分析并生成 Markdown 文档后，或用户说「登记价值量」、「填写价值量」时：

1. **自动读取需求 Markdown**：优先读取当前对话或 `/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析/` 目录下最新修改的需求 Markdown 文档。
2. **提取与计算**：
   * **`req_id`**：读取 Front Matter `req_id: R26xxxxxxx` 或标题中的需求编号；
   * **价值量 (`ndw`)**：若已指定则直接采用，未指定则根据系统复杂度智能评估（如 `0.3`）；
   * **主系统 (`ndw_system`)**：根据 `改造范围` 首个系统确定。
3. **极速 API 登记**（⚠️ **必须用 venv python**，脚本依赖 `requests`，base managed python 未安装会报 `ModuleNotFoundError: No module named 'requests'`）：
   ```bash
   /Users/wujin/.workbuddy/binaries/python/envs/default/bin/python3 ~/.workbuddy/skills/gtht-ndw-fill/scripts/ndw_fill.py <req_id> --value <价值量>
   ```
   > 💡 **安全实践**：提交前先加 `--dry-run` 验证全链路（自动登录 + Story 前置校验 + 评估人查询 + payload 构造），确认无异常后再去掉 `--dry-run` 实际落库，秒级且零风险。
   > 🚀 **极速预授权**：若已确认参数无误，可带 `--yes` 单次进程直接落库（如 `ndw_fill.py <req_id> --value 0.5 --yes`），跳过 dry-run 展示与确认轮，质量护栏不变（见「⚡ 性能优化」）。
   > 📌 **跨系统归属说明**：脚本自动取 `stories[0]` 的归属系统为价值量主系统，跨系统需求（如低延时+集中交易）只记首个 Story 的主系统，属正常行为，非漏登记。
   > 🏷️ **标题前缀规则（2026-09-02 新增）**：登记时自动为任务标题加系统类型前缀——
   > - **单系统需求**（1 个改造系统 / 非跨系统）→ 标题前新增 **【单系统】**（如 `【单系统】集中交易系统...`）；
   > - **跨系统需求**（≥2 个系统 / 多 Story / 多系统价值量）→ 标题前新增 **【跨系统】**（既有逻辑）；
   > - 标题已带 `【单系统】`/`【跨系统】` 前缀时不重复叠加。

---

### 模式二：命令行 / 对话直接登记

用户显式给出需求编号和目标价值量（支持单笔或批量）：

```bash
# 单笔登记示例（必须用 venv python）：
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python3 ~/.workbuddy/skills/gtht-ndw-fill/scripts/ndw_fill.py R2608030112 --value 0.3

# 批量登记示例：
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python3 ~/.workbuddy/skills/gtht-ndw-fill/scripts/ndw_fill.py --batch "R2608030112:0.3,R2608100032:0.3"

# 落库前先预览校验（不提交）：
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python3 ~/.workbuddy/skills/gtht-ndw-fill/scripts/ndw_fill.py R2608030112 --value 0.3 --dry-run
```

#### 参数说明表

| 参数 | 必填 | 格式与说明 | 默认值 |
|---|---|---|---|
| `<demand_id>` | **是** | 需求编号，如 `R2608030112` | - |
| `--value` / `-v` | **是** | 申请的需求分析价值量 (人月)，如 `0.3` | `0.3` |
| `--status` | 否 | 状态代码：`2`(已完成) \| `1`(未完成) | **`2` (已完成)** |
| `--system` | 否 | 所属系统名（未填按需求标题与模块智能推断） | 自动匹配 |
| `--batch` | 否 | 批量登记字符串，格式 `"R26xxxxxxx:0.3,R26xxxxxxx:0.4"` | 空 |
| `--schedule` | 否 | 排期日期 `YYYYMMDD`：工作量周期=排期所在月首个工作日 ~ 排期日（排期对齐登记） | 半月推断 |
| `--by-schedule` | 否 | 自动从需求详情读取排期（wishDate>launchTime>esDuedate）推算周期，读不到回退半月推断 | 半月推断 |
| `--version-schedule` / `--vs` | 否 | **版本排期工作量登记**：输入如 `20261009版本预排期`(默认0.3) / `20261009版本排期`(默认0.2)，系统=集中交易系统，类别=项目管理 | - |
| `--ignore-story` | 否 | 忽略 Story 拆分前置校验强行登记 | `False` |
| `--force` | 否 | 强制删除旧记录并重新创建 | `False` |
| `--dry-run` | 否 | 仅模拟校验，不实际提交落库 | `False` |
| `--yes` / `-y` / `--auto` | 否 | 预授权直接落库：单进程完成 查→校验→提交，跳过 dry-run 展示与确认轮（仅命令显式 opt-in 启用） | `False` |

---

### 模式三：版本排期工作量登记（项目管理类，无需求关联）

登记「版本排期」类非开发工作量（如版本预排期/排期的人工工作量），**不依赖需求编号**，输入版本排期文本即可自动登记：

```bash
# 预排期登记（默认价值量 0.3）：
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python3 ~/.workbuddy/skills/gtht-ndw-fill/scripts/ndw_fill.py --version-schedule "20261009版本预排期"

# 排期登记（默认价值量 0.2）：
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python3 ~/.workbuddy/skills/gtht-ndw-fill/scripts/ndw_fill.py --vs "20261009版本排期"

# 落库前预览校验（不提交）：
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python3 ~/.workbuddy/skills/gtht-ndw-fill/scripts/ndw_fill.py --version-schedule "20261009版本预排期" --dry-run
```

#### 登记要素映射（对齐《非研发工时.md》规范）

| 输入文本 | 非开发工作名称 | 类别(taskType) | 所属系统 | 价值量 |
| :--- | :--- | :--- | :--- | :---: |
| `20261009版本预排期` | 【版本排期】20261009版本预排期 | 项目管理(2) | 集中交易系统 | **0.3** |
| `20261009版本排期` | 【版本排期】20261009版本排期 | 项目管理(2) | 集中交易系统 | **0.2** |

- **解析规则**：正则 `(\d{8})版本(预排期|排期)`，支持 `20261009` / `2026-10-09` / `2026/10/09` 及中间含空格；
- **其他不变**：经办人 `050599`(吴进-125360)、主管评估人 `周尤珠-106881`、状态**已完成**(2)、周期半月自动推断（可加 `--schedule YYYYMMDD` 按排期日期推算）；
- **幂等防重**：按标题精确匹配，已存在符合规范（含评估人/正确周期/价值量/状态）的记录则跳过，不重复登记；
- **参考历史记录**：`TR2606090003`/`TR2607230027`（【排期】…项目管理，taskType=2、relateType=2、无 demandId）。

---

## ⚡ 性能优化（功能质量不变，2026-08-28 落地）

原两段式流程需 2 次 Bash 进程，dry-run 与落库各自完整跑校验链，导致 `get_stories`/`get_evaluator_from_platform`/`get_demand_detail`/`get_existing_ndw` 共 ~6 次**重复 API**（总 ~10 次）。

### 优化 1：dry-run 计划缓存复用（两段式落库省 ~4 次重复 API）
- dry-run 通过时把校验结果（`evaluator`/`demand_info`/`payload`）+ `cached_at` 写入 `/tmp/ndw_<demand_id>_plan.json`；
- 落库进程读取缓存：未过期（≤30 分钟）且 `stories_count` 一致则跳过 `get_evaluator_from_platform` 与 `get_demand_detail`（2 次 API）；
- **强制保留**：`get_stories`（Story 前置强校验，防删除倒挂）与 `get_existing_ndw`（幂等防重）每次必查；过期/Story 数变化自动重查；
- 落库 API 6 → 2，总 ~10 → ~6。

### 优化 2：`--yes/--auto` 预授权（单进程跳确认轮）
- 命令显式带 `--yes`：单进程内 查→校验→提交，零重复 API + 0 轮确认；
- 默认安全模型不变：不带 `--yes` 仍「先 `--dry-run` → 确认 → 落库」；`--yes` 仅 opt-in；
- 质量护栏全保留：Story 前置、幂等、评估人实时查询、dry-run 预览（默认）、`--force` 重建；
- ⚠️ 边界：跳过确认轮，但 NDW 仅记本人工作量、可 `--force` 重建，风险低于 story-split 评估通知他人。

### 优化 3：去重 re-query
- 落库后优先从 `addNonDevTask` 响应取 `taskNo`，取不到再 `get_existing_ndw` 一次（兼容后端结构）。

**预期**：总 API ~10 → ~6；Bash 进程 2 → 1（`--yes`）；用户交互 1 → 0（`--yes`）。

---

## 💬 对话交互示例

| 用户口令 | 技能处理动作 |
|---|---|
| 「**帮我登记刚才需求分析的价值量**」 | 自动校验需求是否已拆分 Story，提取 `req_id` 与推荐价值量，执行 `ndw_fill.py` 秒级完成「已完成」状态登记 |
| 「**为 R2608030112 填写价值量 0.3**」 | 执行：`ndw_fill.py R2608030112 --value 0.3` 完成登记 |
| 「**评估一下这个需求的价值量**」 | 分析需求改造范围与联测系统，给出推荐人月并询问是否立即登记 |
| 「**登记 20261009版本预排期 价值量**」 | 识别为版本排期登记，执行：`ndw_fill.py --version-schedule "20261009版本预排期"`（【版本排期】/项目管理/集中交易系统/0.3） |
| 「**登记 20261009版本排期**」 | 执行：`ndw_fill.py --vs "20261009版本排期"`（【版本排期】/项目管理/集中交易系统/0.2） |
