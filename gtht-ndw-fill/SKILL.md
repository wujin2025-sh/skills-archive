---
name: gtht-ndw-fill
description: 国泰海通科技平台（fintech.gtht.com.cn）需求分析非开发工作量 (NDW / 价值量) 智能评估与独立登记技能。 支持结合
  `ba-to-dev` 需求分析结论根据系统复杂度智能评估价值量（人月），并在科技平台进行极速 API 直连登记（≤0.5s，幂等防重）。 强制前置校验 Story
  拆分状态，默认状态为「已完成」(status=2)，按半月工作日自动推断周期，并自动关联经办人主管评估人（周尤珠-106881）。 同时支持**版本排期/版本发布工作量登记**
  （项目管理类 taskType=2，无需求关联）：输入 `20261009版本预排期`(默认0.3) / `20261009版本排期`(默认0.2) 自动登记
  【版本排期】标题 + 集中交易系统 + 关联人不变；输入 `参数中心20260918版本`(默认1.0/交易参数管理后台系统) /
  `集中交易20260918版本`(默认2.5/集中交易系统) 自动登记【版本发布】标题 + 集成发布后缀。 触发词：登记价值量、价值量评估、填写价值量、NDW填写、评估价值量、需求分析工作量、ba-to-dev价值量、版本排期登记、版本预排期登记、版本发布登记、参数中心20260918版本、集中交易20260918版本。
disable: false
---


# 国泰海通需求分析价值量评估与登记技能 (gtht-ndw-fill)

结合需求复杂度与 `ba-to-dev` 分析结论，智能评估需求分析师 (BA) 的非开发工作量（NDW - Non-Developer Work / 价值量人月），并在国泰海通科技平台（fintech.gtht.com.cn）进行极速 API 直连登记。

> ⚡ **核心原则与规范**：
> - **【完全独立】**：所有依赖（`session.py`、`config.py`、`ndw_fill.py`）均内置于本技能目录，保持独立运行与集中管理；
> - **【默认已完成】**：非开发工作状态**默认为「已完成」(`status: 2`)**；
> - **【Story 前置强核验】**：登记前自动检查该需求下是否已拆分所属 Story。**若未拆分 Story，强制拦截跳过**，防止流程倒挂；
> - **【半月周期自动推断】（2026-10-14 优化：周期 = 登记日所在半区的完整区间）**：
>   - **上半月登记（1~15日）**：周期 = **当月首个工作日 ~ 当月15日**（15日为周末则取之前最近工作日），如 `2026-10-14登记` → `2026-10-01 ~ 2026-10-15`；
>   - **下半月登记（16~月末）**：周期 = **下半月首个工作日 ~ 当月末工作日**，如 `2026-10-16登记` → `2026-10-16 ~ 2026-10-30`；
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

> **🎯 MD 笔记属性优先（2026-10-28 用户固化）**：若本地需求分析 MD 的 Front Matter 已填写 `ndw`，**优先取 MD 中的价值量值**（最高优先级，优先于 `--value` 显式参数），无需再手动传 `--value`（如 `20261015-R2609220085-….md` 中 `ndw: 0.8` → 直接 `ndw_fill.py R2609220085 --yes` 即按 0.8 登记）。仅当 MD 未填 `ndw` 时才按 `--value` 或下方模型智能推断。

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
   * **主系统 (`ndw_system`)**：**优先读取 MD 评审纪要第 3 项【各系统改造功能】中 `(1)` 首个系统全称**（本组实际改造系统，如「(1) 集中交易系统：」→ 取「集中交易系统」）；若第 3 项无系统或无法解析，回退至第 2 项【改造范围】首个系统。显式传入 `--system` 参数；**严禁依赖脚本默认推断**（`stories[0]` 可能取到他组系统如「君弘APP客户端子系统」，与 MD 改造范围不一致）。
3. **极速 API 登记**（⚠️ **必须用 venv python**，脚本依赖 `requests`，base managed python 未安装会报 `ModuleNotFoundError: No module named 'requests'`）：
   ```bash
   /Users/wujin/.workbuddy/binaries/python/envs/default/bin/python3 ~/.workbuddy/skills/gtht-ndw-fill/scripts/ndw_fill.py <req_id> --value <价值量> --system "<MD各系统改造功能首个系统全称>"
   ```
   > 💡 **安全实践**：提交前先加 `--dry-run` 验证全链路（自动登录 + Story 前置校验 + 评估人查询 + payload 构造），确认无异常后再去掉 `--dry-run` 实际落库，秒级且零风险。
   > 🚀 **极速预授权**：若已确认参数无误，可带 `--yes` 单次进程直接落库（如 `ndw_fill.py <req_id> --value 0.5 --system "集中交易系统" --yes`），跳过 dry-run 展示与确认轮，质量护栏不变（见「⚡ 性能优化」）。
   > 📌 **所属系统来源规则（2026-11-09 固化，11-09 修订）**：**所属系统优先取自 MD 评审纪要第 3 项【各系统改造功能】中 `(1)` 首个系统全称**（本组实际改造系统，排除了改造范围中的他组系统）；若第 3 项无法解析，回退至第 2 项【改造范围】首个系统。显式传 `--system` 参数；**禁止依赖脚本 `stories[0]` 默认推断**（实测 `stories[0]` 可能返回他组系统如「君弘APP客户端子系统」，与 MD 改造范围不符）。跨系统需求若需按「吴进创建的 Story」口径统计，请用 `--my-story <Story编号>` 指定（见下方「🎯 吴进创建 Story 口径」），价值量评估按该 Story 统计，但所属系统仍以 MD 各系统改造功能首个系统为准（除非 `--my-story` 与 `--system` 同时传入时以 `--system` 为准）。
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
| `--system` | 否 | 所属系统名（**默认取 MD 评审纪要第 3 项【各系统改造功能】`(1)` 首个系统全称**，回退至第 2 项【改造范围】首个系统；须显式传入；未传时脚本按 `stories[0]` 推断，可能不准） | MD各系统改造功能首个系统 |
| `--my-story` | 否 | **吴进创建的 Story 编号**（如 `R2609110103-2`）：价值量评估与所属系统均按该 Story 统计 | 全部 Story |
| `--batch` | 否 | 批量登记字符串，格式 `"R26xxxxxxx:0.3,R26xxxxxxx:0.4"` | 空 |
| `--schedule` | 否 | 排期日期 `YYYYMMDD`：工作量周期=排期所在月首个工作日 ~ 排期日（排期对齐登记） | 半月推断 |
| `--by-schedule` | 否 | 自动从需求详情读取排期（wishDate>launchTime>esDuedate）推算周期，读不到回退半月推断 | 半月推断 |
| `--version-schedule` / `--vs` | 否 | **版本排期工作量登记**：输入如 `20261009版本预排期`(默认0.3) / `20261009版本排期`(默认0.2)，系统=集中交易系统，类别=项目管理 | - |
| `--ignore-story` | 否 | 忽略 Story 拆分前置校验强行登记 | `False` |
| `--force` | 否 | 强制删除旧记录并重新创建 | `False` |
| `--dry-run` | 否 | 仅模拟校验，不实际提交落库 | `False` |
| `--yes` / `-y` / `--auto` | 否 | 预授权直接落库：单进程完成 查→校验→提交，跳过 dry-run 展示与确认轮（仅命令显式 opt-in 启用） | `False` |

---

## 🎯 吴进创建 Story 口径（`--my-story`，2026-09-21 新增）

**背景**：跨系统需求下通常拆分多条 Story（分属不同系统、不同负责人），但价值量只应统计**吴进（受理人）自己创建的那条 Story** 所对应的工作，而非需求下全部 Story。

**规则**：
- **价值量评估**：仅按吴进创建的 Story 评估——配合测试类单系统 Story 默认 `0.2`，其余单系统默认 `0.3`（不再因需求整体跨系统而按 `0.5` 评估）；
- **所属系统**：取吴进创建 Story 的 `systemName`（如 R2609110103 中吴进创建 R2609110103-2 → 所属系统=集中清算系统），而非 `stories[0]` 或标题关键字推断；
- **标题前缀**：跨系统需求仍按整体判定加【跨系统】前缀（标题层面反映需求全貌，与价值量/所属系统口径解耦）。

**判定吴进创建的 Story**：`get_stories` 返回的 Story 对象**不含创建人字段**（`userId/userName` 为需求提出人），需通过 `get_story_list(reqUser=125360)` 过滤——能查到的 Story 即吴进相关（配合测试 Story 通常由受理人吴进创建），据此确定 `--my-story` 传参。

```bash
# 示例：R2609110103 吴进创建 R2609110103-2（集中清算·配合测试）→ 所属系统=集中清算系统
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python3 ~/.workbuddy/skills/gtht-ndw-fill/scripts/ndw_fill.py R2609110103 --my-story R2609110103-2 --value 0.2 --yes
```

> ⚠️ **注意**：`--my-story` 与 `--system` 同时传入时，以显式 `--system` 为准；未传 `--my-story` 时保持原口径（取 stories[0] 或标题推断）。

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
- **周期（版本排期固定上半月）**：开始时间=**当月第一个工作日**，结束时间=**当月15日**（15日为周末则取之前最近工作日），如 9月填写 → `2026-09-01 ~ 2026-09-15`；可加 `--schedule YYYYMMDD` 按排期日期推算覆盖；
- **其他不变**：经办人 `050599`(吴进-125360)、主管评估人 `周尤珠-106881`、状态**已完成**(2)；
- **幂等防重**：按标题精确匹配，已存在符合规范（含评估人/正确周期/价值量/状态）的记录则跳过，不重复登记；
- **参考历史记录**：`TR2606090003`/`TR2607230027`（【排期】…项目管理，taskType=2、relateType=2、无 demandId）。

---

### 模式四：版本发布工作量登记（项目管理类，无需求关联）

登记「版本发布」类非开发工作量（如各系统集成发布的人工工作量），**不依赖需求编号**，直接输入系统名+版本日期文本即可自动登记：

```bash
# 参数中心集成发布登记（默认价值量 1.0，系统=交易参数管理后台系统）：
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python3 ~/.workbuddy/skills/gtht-ndw-fill/scripts/ndw_fill.py --version-release "参数中心20260918版本"

# 集中交易集成发布登记（默认价值量 2.5，系统=集中交易系统）：
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python3 ~/.workbuddy/skills/gtht-ndw-fill/scripts/ndw_fill.py --vr "集中交易20260918版本"

# 落库前预览校验（不提交）：
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python3 ~/.workbuddy/skills/gtht-ndw-fill/scripts/ndw_fill.py "参数中心20260918版本" --dry-run

# 💡 位置参数自动识别：不带 --version-release/--vr 时，非 R 开头的参数若能解析为版本排期/版本发布文本亦自动分流
```

#### 登记要素映射

| 输入文本 | 非开发工作名称 | 类别(taskType) | 所属系统 | 价值量 |
| :--- | :--- | :--- | :--- | :---: |
| `参数中心20260918版本` | 【版本发布】参数中心20260918版本集成发布 | 项目管理(2) | 交易参数管理后台系统 | **1.0** |
| `集中交易20260918版本` | 【版本发布】集中交易20260918版本集成发布 | 项目管理(2) | 集中交易系统 | **2.5** |

- **解析规则**：正则 `(参数中心|集中交易)(\d{8})版本`，支持 `20260918` / `2026-09-18` / `2026/09/18` 及中间含空格；任务标题 = `【版本发布】{输入文本}集成发布`；
- **价值量默认值**：参数中心 **1.0** / 集中交易 **2.5**（可 `--value` 显式覆盖）；
- **周期（版本发布固定上半月）**：开始时间=**当月第一个工作日**，结束时间=**当月15日**（15日为周末则取之前最近工作日），如 9月填写 → `2026-09-01 ~ 2026-09-15`；可加 `--schedule YYYYMMDD` 按排期日期推算覆盖；
- **其他不变**：经办人 `050599`(吴进-125360)、主管评估人 `周尤珠-106881`、状态**已完成**(2);
- **幂等防重**：按标题精确匹配，已存在符合规范（含评估人/正确周期/价值量/状态）的记录则跳过，不重复登记；
- **实现说明**：与模式三共用 `_submit_project_workload` 通用内核（taskType=2、relateType=2、无 demandId），模式三分流逻辑保持原有 `parse_version_schedule` 不变（2026-09-28 架构重构，dry-run 双模式验证通过）。

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

### 优化 4：HTTP 内网直连优先（2026-11-04，最大提速项）
- **背景**：系统代理对 fintech.gtht.com.cn 基本不可用（必 ReadTimeout 20s）。旧逻辑「先走代理、超时 20s 后再降级直连」令每个 API 白等 20s+，登记链 5 API ≈ 100s+（R2610270069 首登实测 ~95s）。
- **修复**：`session.py _http_request` 默认 `trust_env=False + verify=False` 直连（<1s），仅直连异常（罕见）才回退系统代理；**与 kjptai MCP `post()` 禁代理 / proposed-schedule-confirm NO_PROXY 同源决策**。
- **运行须知**：✅ **无需再设 `NO_PROXY=fintech.gtht.com.cn`**（脚本已内置直连）；token 有效时全程 <3s。
- **附带**：`get_stories` 查询失败不再静默吞错（改 stderr 告警），杜绝「代理超时→空列表→误判未拆分 Story」类误拦截。

### 优化 5：幂等快速通道（2026-11-04）
- `fill_ndw` 在 `get_stories` 之后**立即** `get_existing_ndw`，命中有符合规范记录（taskType=1 含评估人 + 正确半月周期 + 同状态）直接返回 skip，**免去 evaluator/demand_detail 2 次 API**，重复登记实测 **0 秒**；
- 仅默认半月周期场景启用（`--schedule`/`--by-schedule` 排期登记走原全流程）；`--force` 跳过本通道；后续缺陷纠偏块复用同一 `existing`，**不再二次查询**。

**预期**：总 API ~10 → ~6 → 首次登记 5 API/≈3s（token 有效）；**重复登记 2 API/0s**；token 失效重登 +Playwright ~15~25s（8h 复用一次）；用户交互 1 → 0（`--yes`）。

---

## 💬 对话交互示例

| 用户口令 | 技能处理动作 |
|---|---|
| 「**帮我登记刚才需求分析的价值量**」 | 自动校验需求是否已拆分 Story，提取 `req_id` 与推荐价值量，执行 `ndw_fill.py` 秒级完成「已完成」状态登记 |
| 「**为 R2608030112 填写价值量 0.3**」 | 执行：`ndw_fill.py R2608030112 --value 0.3` 完成登记 |
| 「**评估一下这个需求的价值量**」 | 分析需求改造范围与联测系统，给出推荐人月并询问是否立即登记 |
| 「**登记 20261009版本预排期 价值量**」 | 识别为版本排期登记，执行：`ndw_fill.py --version-schedule "20261009版本预排期"`（【版本排期】/项目管理/集中交易系统/0.3） |
| 「**登记 20261009版本排期**」 | 执行：`ndw_fill.py --vs "20261009版本排期"`（【版本排期】/项目管理/集中交易系统/0.2） |
| 「**登记 参数中心20260918版本**」 | 识别为版本发布登记，执行：`ndw_fill.py --version-release "参数中心20260918版本"`（【版本发布】…集成发布/项目管理/交易参数管理后台系统/1.0） |
| 「**登记 集中交易20260918版本**」 | 识别为版本发布登记，执行：`ndw_fill.py --vr "集中交易20260918版本"`（【版本发布】…集成发布/项目管理/集中交易系统/2.5） |
