# ba-to-dev × biz-logic-query 共性基线（Single Source of Truth）

> **用途**：两个技能共用的规范**只在本文件维护**。`sync_shared.py apply` 会把每个 `<!-- SHARED:<id> START/END -->` 块推送到两份 `SKILL.md`，保证技能被加载时内嵌完整规范、无外链依赖。
> **禁止**：直接在任一 `SKILL.md` 内手工编辑共性块（下次 `apply` 会被覆盖）。共性改动一律先改本文件。
> **范围**：`ba-to-dev`（BA 需求→研发文档）、`biz-logic-query`（业务逻辑问答+证据链）。其他技能可引用，但不纳入强同步。
> **版本**：v1.0 / 2026-11-13 / 维护者：吴进

---

### authority_sources｜权威源注册表

<!-- SHARED:authority_sources START -->
### 🔗 权威源注册表（两技能共用，DB-First）

| 检索域 | 权威源 | 路径 / 命令 | 口径 |
| :--- | :--- | :--- | :--- |
| L0 需求依赖反查 | `demand_dep_find.py` | `~/.workbuddy/skills/ba-to-dev/scripts/demand_dep_find.py <需求号> [概念...]` | 本地需求 MD 全库反查；反查词用**业务概念**，禁用 `ipoavl` 等特化字段名 |
| L1 接口/功能号契约（**首选**） | **fwzl-mcp**（服务治理 MCP） | `mcp__fwzl-mcp__functionQueryServiceByKeyWord` / `queryServiceParameterByFuncCode` / `queryParentFunction` / `queryChildFunction`；端点为 `https://sg.gtht.com.cn/api/v1/mcp/byApplication/fwzlMcpServer/mcp`（streamable_http，无需浏览器/登录态） | **默认首选**：按功能号/关键字查存在性、基本信息（功能号/名称/类型/所属系统/负责人）、出入参(IN/OT/HD)、调用链；本地库未收录的纯数字功能号也可命中；判定存在只用 `functionQueryServiceByKeyWord`（查不到仅=未收录，不反证不存在） |
| L1 本地接口知识库（**兜底**） | SQLite | `/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/rules-raw/.interface_store.db`（`interfaces` / `interface_fields`） | **仅当 fwzl-mcp 不可用（401/403/网关不可达/工具未加载）或未命中时**：毫秒级 3257 接口/82421 字段明细；**参数/菜单类概念**（如「融资规模设置」「净资本比例」）在 `name/code/description` 常 0 命中，须改按 `table_name` 回查（→ S24 信用交易规模参数 `creditscale`），不得退化成「融资」等泛词做同族扩展 |
| L1.4 接口号↔菜单双向反查库（**2026-11-20 新增**） | `menu_interface_query.py` + SQLite | 脚本 `~/.workbuddy/skills/ba-to-dev/scripts/menu_interface_query.py`；源 `/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/rules-raw/菜单调用接口汇总.md`；索引 `.menu_interface.db`（首次自动建，源更新自动重建） | **接口↔前台菜单双向反查**：①接口→菜单（`--code`/`--extract`，供 ba-to-dev 评审纪要第 4 项「前端界面」）；②菜单→接口（`--menu <名>` / `--menu-extract "<原文>"` 出完整去重接口号清单，供后续 fwzl-mcp 检索/第 5 项接口交互）。718 Web 平台菜单/1.1 万调用，毫秒级。**体系边界**：仅覆盖 qyyx/Web 平台菜单（5 位业务代码）；集中清算/营运 C++ 柜台菜单（6 位功能号如 504015）、低延时功能号（739xxxx）属另一体系、无 ESB 接口号，改走 CBM；8 位综合理财号+外围号可反查，公共接口命中多菜单按业务语义筛选、泛词多命中用 `--menu <精确名>` 收敛。与 L1 fwzl-mcp **互补**（前者答"接口↔前台菜单功能号"，fwzl-mcp 答"接口入参出参/所属系统"） |
| L1.5 订阅矩阵库 | SQLite | 同目录 `.subscription_matrix.db`，见下方「订阅矩阵库」块 | 文件编号 → 输出系统 / 消费者方向 |
| L2 代码知识图谱 | `codebase-memory-mcp` | `~/.local/bin/codebase-memory-mcp cli` 或 MCP `search_code` / `get_code_snippet` / `trace_path` | 项目 `jzjy` / `dys` / `jzqs` / `grc` / `cszx`；**中文业务词 0 命中是常态**，改英文符号 + `--path-filter` |
| L3 数据库实证 | `dbq <profile>` | `/usr/local/bin/dbq`；profile `jzjy_sit` / `dys95` / `jzqs_sit` / `cszx_sit` / `jzqs_comm_sit` | `--table` / `--search-table` / `--sql`；**字典表真名 `run.dbo.dictindex` + `run.dbo.dictvalue`，不是 `t_dict`** |
| L4 业务规则 / 既有需求 | `openviking_mcp.py` | `~/.workbuddy/skills/openviking-query/openviking_mcp.py find\|glob\|read` | 必须 `NO_PROXY=csgl.gtht.com.cn,fintech.gtht.com.cn` |
| 系统名称清单 | `system_list.csv` | `/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/rules-raw/system_list.csv` | 中文全称；BA 正文写统称，括号域归属留给拆 Story 阶段 |
| 本地需求 MD | Obsidian | `/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析/` | 需求号优先本地三级检索，命中即 0 秒复用 |

**DB-First 优先级（P0）**：`dbq 直查 > 权威清单(system_list.csv / 接口库 / 订阅矩阵) > 代码图谱符号级溯源 > 需求原文`。凡**客观事实**（表名 / 字段名 / 字段类型 / 参数编码 / 系统中文全称 / 接口号 / 规则条文编号）必须先实证再落盘，**严禁「名字像 / 关键词像 / 函数名像」推断语义**。典型反例：`comm_secuid_total` 实为计数表（标准名称源是 `comm_stock.stkname`）、`zy_debts` 实为股票质押（非两融负债表）。

**路径约定**：`.chat/skills` 是指向 `.workbuddy/skills` 的软链接，改一处即生效；所有脚本一律只用 `~/.workbuddy/skills/` 下的版本，不用临时副本。
<!-- SHARED:authority_sources END -->

---

### evidence_grading｜证据可信度三态

<!-- SHARED:evidence_grading START -->
### 🔗 证据可信度三态与诚实原则（两技能共用）

每条结论 / 每条证据必须标注三态之一，**严禁混为一谈、严禁凭记忆编造**：

| 分级 | 含义 | 权威来源 |
| :--- | :--- | :--- |
| 🟢 **已实证** | 客观可查、可直接引用 | 接口库 / 订阅矩阵库 / `dbq` 表结构与 SQL / 需求 MD 原文 / 源码文件+行号 |
| 🟡 **可追溯** | 索引或语义命中，次可靠 | CBM `search_graph` / `trace_path` 调用链 / openviking `find` 命中 |
| 🔴 **待确认** | 未命中，需人工 / 研发确认 | 熔断结果，**严禁臆断补全** |

**诚实原则**：未检索到证据就如实标注「待确认」，绝不猜测系统行为；需求文档写「(具体实现以研发设计为准)」，问答结论写「未命中 / 需确认」。对齐 `ba-to-dev` P0#22 DB-First 与 P0#1 绝对忠于事实、`biz-logic-query`「证据链可信度分级（P0 铁律）」。

**落点**：`ba-to-dev` → 第四章审计「待确认事项」+ P0#26 数据流图箭头三态标注 + 图下「证据出处」；`biz-logic-query` → 证据链表格 `confidence` 列 + 结论段「仍待确认」清单。二者对同一事实的三态判定必须一致，出现冲突时以上表权威源优先级裁决。
<!-- SHARED:evidence_grading END -->

---

### clarification｜交互澄清协议

<!-- SHARED:clarification START -->
### 🔗 交互澄清协议（用户 2026-11-13 明确要求，两技能共用）

> 用户原话：「如遇到疑惑，可以随时向我咨询，以补充确认项，以便使得搜索关键词更精准」。
> **原则：仅在歧义 / 未命中时问，顺畅查询不打断；一次最多 3 问且必须给候选选项；答案必须回灌成检索参数，不得只记在对话里。**

**触发信号（任一命中即问）**：概念 0 命中 / 同族接口 ≥4 条或自动扩展 ≥12 条（短词多义）/ 中文概念未映射出英文标识符 / 代码层多域 0 命中或超时 / 本地需求库未命中 / 需求原文出现未核对的接口号或文件编号 / 业务规则口径冲突。

**回灌映射（拿到答案后必做）**：

| 用户补充的信息 | 回灌为 |
| :--- | :--- |
| 英文函数名 / 字段名 | 作为检索词重跑；补进 `KEYWORD_MAP` / `DB_KEYWORD_MAP` |
| 功能号 / 文件编号 | `biz_logic_query.py "<编号>" --code` 或 `interface_query.py <编号>` 核对 |
| 系统域 | `--project <域>` / `--projects a,b`；BA 侧写进改造范围 |
| 表名 / 搜表词 | `--db-table` / `--db-search-table "%xxx%"` |
| 需求号 | 作为 `question` 重跑 + `openviking glob "*<需求号>*"` |
| 「只要快」/「数据刚更新」 | `--fast` / `--refresh`（BA 侧 `--force` / `--remote` 强制平台原文覆盖） |

**已确认字典（用户当场确认，勿重复问）**：① 默认策略＝全量并行 + 缓存（证据链不打折，`--fast` 手动跳过深度域）；② 澄清时机＝仅歧义 / 未命中时；③ 默认系统域＝自动多域并行 `jzjy,dys,jzqs`。

**豁免**：`question` 精确等于已登记的 ≥5 字明确概念（如「指定合约还款」）时视为明确，展示同族概览但不触发澄清。

**场景差异（各自在本技能内展开，不属于共享块）**：`biz-logic-query` 以脚本 `--json` 的 `clarification` 数组非空为准；`ba-to-dev` 在需求原文歧义、系统域/编号未核对、业务规则口径冲突、评审纪要「无」判定无依据时发起，且澄清不得阻塞 Step 3 落盘（P0#16）。
<!-- SHARED:clarification END -->

---

### subscription_matrix｜订阅矩阵库

<!-- SHARED:subscription_matrix START -->
### 🔗 订阅矩阵库（文件编号 → 消费者，两技能共用权威源）

- **库**：`/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/rules-raw/.subscription_matrix.db`（与 `.interface_store.db` 并列）
- **脚本**：`~/.workbuddy/skills/biz-logic-query/scripts/subscription_matrix.py`
- **唯一数据源**：`文件接口明细/新一代文件交互接口订阅矩阵.xlsx`（Sheet1，文件 × 系统打勾矩阵，`√` = 订阅）。**原 xlsx 只读，绝不回写**；库可随时 `build` 重建（temp + 原子替换）。
- **命令**：`build` 重建｜`query <编号>` 消费者 + 实证｜`consumer <系统>` 反查｜`stats` 总览｜`sql "<SQL>"` 自由查询。
- **规模**：`files` 498 / `consumers` 18 / `subscriptions` 743 条 / `evidence` 14 条；接口库关联 492/498（98.8%）。视图 `v_file_consumers` / `v_a37_consumers`。
- **状态口径**：`🟢 矩阵原样`＝仅来自矩阵；`🟢 多源实证`＝另有接口库 / 源码 / dbq / 需求佐证；`🔴待确认`＝见 `evidence` 表。
- **A37 权威结论**：**唯一消费者 = 低延时交易系统(虚拟)**，输出系统 = 集中清算系统；反向 **Q49** 输出 = 低延时，消费者 = 集中清算系统 + 集中交易系统。已核销「源码注释接收方是集中交易」的口径差异。
- **联动**：`biz-logic-query` L1.5 `query_subscription()` 在命中文件编号时自动附加消费者证据；`ba-to-dev` P0#26 数据流图铁律⑥ 以本库判定**输出系统 / 消费者方向**，与 P0#9 接口核对、P0#22 DB-First 共同构成编号与方向的三重实证，不照抄需求原文。
<!-- SHARED:subscription_matrix END -->

---

### dataflow_diagram｜接口/文件数据流图

<!-- SHARED:dataflow_diagram START -->
### 🔗 接口/文件数据流图（两图分工，两技能共用口径）

| | 业务时序图 | 接口/文件数据流图 |
| :--- | :--- | :--- |
| 语法 | `sequenceDiagram` | `flowchart LR` |
| 视角 | 客户 → 系统，谁先谁后 | 系统 ↔ 系统通道 |
| 回答 | 各系统改了什么 | 走哪条接口/文件、承载什么字段、落在哪张表 |
| 触发 | 每份 BA 需求（`ba-to-dev` P0#6） | **仅含接口号 / 文件编号且已核对**（`ba-to-dev` P0#26）；无交互整节省略 |

**6 条绘制铁律**：① 节点**只画业务系统中文全称**（`system_list.csv`），DB 表 / 内存表 / 缓存只能写成节点内注记或箭头标签，严禁画成外部节点；② 每条箭头带**编号 + 中文名 + 方向（下发/回流/调用）**，编号必须经接口核对，未核对标 🔴 并写入第四章，**严禁编造编号与方向**；③ 标签补**字段承载**（如 `extstr 承载对手方股东账户`）与是否下发口径，「不下场」用图下文字注记、不画箭头；④ 三态标注 🟢/🟡/🔴，图下附「证据出处」（接口库 / 源码文件:行号 / dbq 库表 / 需求号）；⑤ `ba-to-dev` 中**只置于三（二）系统间协作段**，严禁进评审纪要（P0#4），不与五章「知识积累」重复；⑥ 编号、方向、字段以 **接口核对 + DB-First + 订阅矩阵库** 三重实证为准。

**落点**：`ba-to-dev` → 三（二）模板与 A37/Q49 范例（`validate_ba_md.py` R1–R9 不校验 Mermaid，加图不改变门禁）；`biz-logic-query` → 查到文件编号 / 接口族时，用会话可视化卡片呈现同一张图，编号与方向直接取订阅矩阵与接口核对结论。
<!-- SHARED:dataflow_diagram END -->

---

### sync_protocol｜共性同步协议（开发态规范，不注入运行态 SKILL.md）

> 2026-11-21 瘦身：本节仅在修改共性块时由开发者/维护者查阅，不再作为 `SHARED` 块同步注入两份运行态 `SKILL.md`（两份 `SKILL.md` 的章首提示已保留 `_shared/SHARED.md` 与 `sync_shared.py` 指针）。

### 🔄 共性同步协议（后续优化 SKILL 时必执行）

**共性项清单**（改动任一即视为「共性改动」，必须双技能同步）：

| # | 共性项 | 块 ID |
| :--- | :--- | :--- |
| 1 | 权威源路径 / profile / CBM 项目名 / 字典表真名 / DB-First 优先级 / 软链接约定 | `authority_sources` |
| 2 | 证据可信度三态与诚实原则 | `evidence_grading` |
| 3 | 交互澄清协议与已确认字典 | `clarification` |
| 4 | 订阅矩阵库路径 / 命令 / A37 结论 / 联动方式 | `subscription_matrix` |
| 5 | 接口/文件数据流图两图分工与 6 铁律 | `dataflow_diagram` |
| 6 | 业务概念 → 英文标识符 / 表名词映射、实测字典中的**跨技能通用结论**、共享脚本路径、复盘固化机制 | 见 `shared_registry.json` 的 `constants` |

**执行动作（智能体在任一次技能优化收尾时必做）**：

1. **判定**：本次优化是否触及上表任一项或 `constants` 中的共享常量？否 → 只改本技能，无需同步。
2. **改源**：改 `~/.workbuddy/skills/_shared/SHARED.md` 对应块（必要时同步 `shared_registry.json` 的 `constants`）。**不要直接改两份 SKILL.md 的共性块**。
3. **推送 + 校验**：
   ```bash
   P=/Users/wujin/.chat/runtimes/darwin-x64/python/versions/3.13.12/bin/python3
   S=~/.workbuddy/skills/_shared/sync_shared.py
   $P $S apply && $P $S check
   ```
   `apply` 自动备份并把块推送到两份 `SKILL.md`；`check` 有任何漂移返回退出码 1，**未通过不得结束本轮**。
4. **复盘留痕**：按「技能完成复盘机制」输出稳定性 / 质量 / 速度三维优化点，并把共性改动记入当天工作日志；单边特有改动（如 P0 编号、性能基线、实测映射细节）只记本技能，不推送。

**规则**：① 共性块内容两边**严格一致**（由 `check` 哈希比对保证），场景差异写在块外的本技能章节；② 单边新增的权威结论若对另一技能有价值（如新的文件编号消费者、新的字典真名），须提升为共性项并写进 SHARED.md；③ 新增第三个共用技能时，在 `shared_registry.json` 的 `targets` 追加后重跑 `apply --init`；④ 禁止用「复制粘贴」代替同步，禁止手工删改 `<!-- SHARED:... -->` 标记；⑤ **副本镜像**：`.chat/skills/biz-logic-query` 是独立真实目录（非软链接），其 `SKILL.md` 为独立副本 —— `apply` 自动把权威版镜像过去、`check` 校验逐字一致；`ba-to-dev` 已是软链接、`scripts/` 为硬链接，均无需处理；新增独立副本时登记到 registry 的 `mirrors`。

---

## 维护记录

| 日期 | 版本 | 变更 |
| :--- | :--- | :--- |
| 2026-11-13 | v1.0 | 初建：从 ba-to-dev / biz-logic-query 抽取 6 个共性块，建立 apply/check 机制；首次全量同步补齐 4 处漂移（澄清协议、订阅矩阵、数据流图、权威源/可信度分级） |
| 2026-11-13 | v1.1 | 发现 `.chat/skills/biz-logic-query/SKILL.md` 是独立旧副本（非软链接），新增 `mirrors` 镜像同步与逐字一致性校验；`scripts/` 为硬链接无需处理 |
