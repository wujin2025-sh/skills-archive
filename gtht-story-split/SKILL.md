---
name: gtht-story-split
description: '国泰海通科技平台（fintech.gtht.com.cn）需求 Story 极速自动拆分与技术评估发起技能（纯 MCP 版）。

  完全通过 kjptai 科技平台 MCP 协议访问（服务端鉴权，无需本机登录态、无需浏览器、无需网页抓取、无需任何 Python 脚本）。

  按需求编号调用 mcp__kjptai__query_requirement 获取需求要素、mcp__kjptai__query_requirement_flow
  获取流程/可执行操作/存量 Story（幂等检查），

  再调用 mcp__kjptai__create_story 在需求下逐条创建 Story

  （两段式确认：prepare 返回 READY_TO_CONFIRM → 用户确认 → confirmed 提交；系统模板套用、Story 名称=需求名称/【配合测试】前缀、业务验收属性推断、父需求描述拷贝、

  所属系统标签/二级需求类型/是否影响灰度升级等扩展属性填写），

  拆分完成后调用 mcp__kjptai__start_technical_evaluation 发起技术评估（同样两段式确认）。

  可选：mcp__kjptai__split_story_to_tasks(storyNo=...) 把单个 Story 进一步拆成 Task 草稿。

  支持自动解析 `ba-to-dev` 产出的需求分析 Markdown 文档（提取需求编号、改造范围、联测涉及系统、灰度影响与业务验收推断），

  或直接按需求编号与系统清单进行拆分。

  触发词：拆分Story、拆Story、Story拆分、自动拆分Story、发起技术评估、新增Story、ba-to-dev拆分、拆Task。

  '
disable: false
---


# 国泰海通 Story 自动化拆分技能（纯 MCP 版）

自动按需求评审结论或 `ba-to-dev` 产出的需求 Markdown 文档，在国泰海通科技平台（fintech.gtht.com.cn）中为目标系统拆分所属 Story，并自动发起技术评估。

> ⚡ **性能与可靠性**：
> - **MCP 直连（唯一方式）**：完全通过 `kjptai` 科技平台 MCP 工具完成 Story 拆分与属性填充，服务端持有科技平台登录态，无需本机 session、无需解密密钥、无需浏览器渲染；
> - **两段式令牌走工具通道（2026-08-28 实测）**：`create_story` 的 prepare **直接经 DeferExecuteTool 返回完整 `mcpContinuation`（含 `confirmationToken`，Agent 可见）**，无需 `kjptai_prepare.py` 子进程（该脚本仅作 `start_technical_evaluation` 的兜底——当其 prepare 不直出令牌时使用）；
> - **极速路径（2026-08-28 固化，功能不变）**：① ToolSearch 信任已知 `mcp__kjptai__*` 工具名（调用报"未找到"才回退 ToolSearch）；② 模式A 有 ba-to-dev MD 时**跳过 `query_requirement`**，要素从 MD 取，仅 `query_requirement_flow` 做闸门+幂等；③ **N 条 Story prepare 在单条消息内并行**；④ 本地 MD + memory 收敛单次写入；典型 3 系统需求从 ~15 次往返压到 ~10 次；
> - **Step 6 技术评估「先检查、等指令」**：创建完 Story 后**不自动发起评估**，先回查落库 + `query_technical_evaluation_progress` 幂等检查，再询问用户，明确同意后才 prepare+提交；
> - 若 kjptai MCP 工具不可用，提示用户检查 **kjptai 连接器**信任状态。

---

## ⚡ 性能优化（2026-08-28 实测固化，功能不变）

典型 3 系统需求（R2608210053 同类）往返从 **~15 次压缩到 ~10 次**，墙钟显著下降：

| # | 动作 | 原往返 | 优化后 |
|---|---|---|---|
| 0 | ToolSearch 加载工具 | 1 次 | **0 次**：信任已知 `mcp__kjptai__*` 工具名，仅调用报"未找到"时回退 ToolSearch |
| 1 | Step 1+2+3 查询 | 3 次（requirement/flow/story探索） | **1 次**：模式A 有 MD 时仅 `query_requirement_flow`（闸门+幂等，要素从 MD 取）；无 MD 时并行 `query_requirement`+`flow` |
| 2 | Step 4 prepare | 3 次（跨轮串行+脚本子进程） | **3 次并行（1 消息）** + 提交后 re-prepare×2（串行，因 updateTime 前移）；**走工具通道直出令牌，弃用 kjptai_prepare.py 子进程** |
| 3 | 提交 | 3 次 | 3 次（confirmed=true + 工具通道令牌） |
| 4 | Step 5 回查 | 1 次 | **0~1 次**：与 Step 6 检查（`query_technical_evaluation_progress`）**并行**——`create_story` 提交成功已返回完整 Story（含扩展属性），回查可用 Step 6 的 `query_technical_evaluation_progress` 一并覆盖（其含 Story 全字段）；仅当用户不发起评估时才单独 `query_requirement_flow` 回查 |
| 5 | Step 6 检查+发起 | 无条件 | `query_technical_evaluation_progress` 幂等 → **询问+令牌预取并行（1 消息）** → 用户同意后直接提交 → **回查可省**（提交返回 SUCCESS 即确认落库，不再额外确认，省 1 次往返） |

> 规则：**不牺牲功能与安全**——两段式确认保留（`--yes` 仅命令显式 opt-in 时跳过，落库参数完全一致）；幂等（flow stories）保留；回查双保险保留；模板负责人强制映射保留；工号双体系注意保留。仅合并重复调用、并行 prepare、去脚本子进程、去冗余查询。
>
> 🚀 **`--yes` / `--auto` 预授权（opt-in，安全边界降低）**：命令显式带 `--yes`（如 `/gtht-story-split R26xxxxxxx --yes`）时，Step 4 的 3 条 Story 准备+提交全自动连跑（不再等用户"确认"），Step 6 发起评估**仍须用户明确同意**（对外通知动作，不纳入预授权）。默认不带 `--yes` 时仍走两段式确认。
>
> ⏱️ **极速路径（2026-10-14 新增，R2609280016 实测固化）**：**单系统需求**（最常见，如 R2609280016）Story 拆分仅 3 个 MCP 调用（flow 闸门 → prepare 直出令牌 → submit）且**无需 re-prepare**；确认摘要时回复 **「确认并评估」**（二合一授权，见 Step 4/Step 6），拆分提交后**直接发起技术评估（不再二次询问）**——全程用户仅 **1 次确认、对话 2 轮**（发指令 + 确认）。**多系统需求**（3 Story 级）因服务端 updateTime 并发控制，提交阶段必须串行（submit1→re-prepare2→submit2→re-prepare3→submit3），墙钟约 +5~10s，属服务端硬约束**不可并行**（re-prepare 依赖上一条提交完成后的新 updateTime）。
>
> 🔗 **跨技能全流程连跑入口（2026-10-14 新增）**：当由 `/gtht-accept-review` **全流程连跑**模式移交进入本技能时（用户已在评审确认时**一次授权**「拆 Story + 技术评估」），**免查 flow**——直接复用 accept-review 评审阶段已获取的 `query_requirement_flow` 结果（statusName/stories[]/receiver 均为评审后最新）作为 Step 1+2+3 闸门与幂等依据，**省 1 次 MCP 往返**；需求要素（优先级/改造范围/灰度）仍须从 ba-to-dev MD 提取（flow 不承载要素）；随后按 Step 4 create_story prepare→提交（**不再二次询问**，授权已在评审确认时获取）→ Step 6 start_technical_evaluation prepare→提交（技术评估授权同样已在评审确认时获取，遵循业务规则 #10 两段式原则——一次确认覆盖多写操作授权，非零确认）。**移交结果缺失/过期（跨会话）时才回退重新 `query_requirement_flow`**。
>
> ⚡ **级联探测极速路径 + 404 熔断（2026-11-04 R2610270069 20 轮实验实证修正）**：① **ID 字典收录系统（集中交易/集中清算/参数中心/低延时/交易参数管理后台等）prepare 免级联探测、一次到位**——全套直传 `tId`+`projectId`（名称或 option value）+`systemId`（**必须 option value**，查 ID 字典），**不触发**服务端 `getSystems` 调用；② **表外系统**：先传 `tId`+`projectId` → NEEDS_INPUT options 提取 systemId option value 回填，**1 次往返拿齐**；③ **报 404 → 先查当前参数是否带 `isEffectGrayUpgrade="1"`+`grayUpgradeRelateSystem` 非空**——是则**服务端 getSystems 路由缺失 bug**，改传 `isEffectGrayUpgrade="0"` 先建 Story 或 UI 手动拆（换参数/换 ID/调序均无效，J/K/L 三连 404 实证），最多 1 次「projectId → options 提取」标准重试后熔断报告，**严禁无限换参盲试**；④ **systemId 传名称 → Project 标 invalid（非 404）**，改用 option value 即恢复（实验4/5 vs 6/20）。
>
> 🚀 **一键拆分编排 `split_stories.py`（2026-11-05 R2610290057 提速固化）**：拆分慢的主因 = ①工具通道 prepare 大响应（数百 KB fields+options）进对话逐条消化；②手工拼 values 人员字段传纯工号触发「Confirmed values changed」失败重试；③flow 480K 大响应进对话。**一键脚本把 flow 闸门+幂等 → 并行 prepare（线程池）→ 串行提交（含 re-prepare）合并进单个进程**，大响应留在进程内，一次 run_command 完成：
> ```
> # --dry-run：flow 闸门+幂等+并行 prepare+确认摘要（不提交零副作用，产物落盘 /tmp/kjptai_story_*_prepare.json）
> python3 split_stories.py --demandId R26xxxxxxx --stories '[{key,label,summary,args:{prepare参数全集}}]' --dry-run
> # 提交：幂等跳过=exit 2；失败重试可直接复用 dry-run 产物
> python3 split_stories.py --demandId R26xxxxxxx --stories '同前' [--verify]
> ```
> 实测 R2610290057 dry-run（2 条 Story 全部幂等 SKIP）**3.2s**；提交链路复用 accept-review 新版 kjptai_prepare（无状态 JWE 直连+禁代理）与 submit_stories 串行提交、values 双层回传服务端规范化全集，根治「Confirmed values changed」与重复握手。**旧路径 `kjptai_prepare.py` 子进程（gtht-story-split/scripts 5.4KB 版，有握手无禁代理）已弃用**，一律用 accept-review/scripts 下的新版。

---

## 📌 架构与依赖

- **访问方式（唯一）**：仅通过 `kjptai` MCP 协议。由 Agent 在对话中直接调用 MCP 工具（工具名前缀 `mcp__kjptai__`）。**不调用任何 REST API、不运行任何脚本、不使用浏览器**。
- **前提条件**：`kjptai` 连接器已信任启用，且当前会话已注册需求/Story 类工具（21 个，含 `create_story`、`query_requirement` 等）。若 `ToolSearch` 搜不到，需检查：
  1. `~/.workbuddy/mcp.json` 中 `kjptai` 指向 **`https://fintech.gtht.com.cn/kjptai/api/mcp`**（X-Platform-Id: `kjpt_prod_...`）——若指向 `devopsai/api/mcp` 只会有 5 个流水线工具；
  2. 修改后**重启/新建会话**并重新信任 kjptai 连接器；
  3. **ToolSearch 信任已知工具名（2026-08-28 优化）**：默认直接调用 `mcp__kjptai__*` 工具（schema 稳定），仅当调用返回"工具未找到"时才用 `ToolSearch` 刷新 schema，以实际注册参数为准。

### 核心 MCP 工具清单

| MCP 工具 | 用途 | 关键参数 |
|---|---|---|
| `mcp__kjptai__query_requirement` | 需求详情+前置校验 | `demandId`（R 开头完整编号） |
| `mcp__kjptai__query_requirement_flow` | 流程与可执行操作（建 Story 前必查） | `demandId` |
| `mcp__kjptai__query_story` | 已有 Story 幂等检查（**兜底**，优先用 flow 的 stories） | `demandId` |
| `mcp__kjptai__create_story` | **创建 Story（两段式确认）** | `demandId`+`summary`+业务字段+`confirmed` |
| `mcp__kjptai__start_technical_evaluation` | 发起技术评估（两段式确认） | `demandId` |
| `mcp__kjptai__split_story_to_tasks` | （可选）Story→Task 草稿 | `storyNo` |
| `mcp__kjptai__query_user` | 仅查当前认证用户（不接受查他人） | — |

---

## 🎯 使用模式

### 模式 A：解析 ba-to-dev 需求文档（推荐）
用户给出需求编号或 `ba-to-dev` 产出的 Markdown 文档时：
1. 若为文档路径，先读取文档，从【需求分析】/【改造范围】/【联测涉及系统】小节提取：需求编号、改造范围系统清单（**拆分对象，须先过滤非本组负责系统**——他组/厂商系统如互联网融资系统、互联网三方交易中台系统、君弘APP等不拆，见业务规则 #3）、联测涉及系统（**仅白名单系统拆配合测试 Story**，见业务规则 #3）、灰度影响、业务验收推断；
2. 若为需求编号（`R26xxxxxxx`），直接进入 Step 1+2+3。

### 模式 B：命令行式（需求编号+系统清单）
用户直接说「对 R26xxxxxxx 拆 Story，集中交易改造，集中清算配合测试」时，直接进入 Step 1+2+3。

---

## ⚙️ 执行流程

### Step 1+2+3：一次查询，完成校验+幂等检查（合并执行，2026-08-28 优化）
- **模式A（有 ba-to-dev MD 文档，推荐）**：**仅调用 `mcp__kjptai__query_requirement_flow(demandId="R26xxxxxxx")` 一次**——其 `boardName`/`stories[]` 已覆盖闸门（状态/可执行操作/存量 Story 幂等），需求要素（优先级、改造范围、业务验收推断等）从已读取的 MD 文档提取，**跳过 `query_requirement`**（省 1 次往返）；
- **模式B（纯需求编号，无 MD）**：**并行调用** `query_requirement` 与 `query_requirement_flow`（**同一条消息内发出，不串行**），一次性拿全要素 + 流程态；
- **模式C（跨技能复用，🔗 accept-review 全流程连跑移交，2026-10-14 新增）**：由 `/gtht-accept-review` 连跑移交时**不查 flow**——直接采用 accept-review 评审阶段已获取的 `query_requirement_flow` 结果（statusName/stories[]/receiver 均为评审后最新）完成本步闸门与幂等检查，**省 1 次 MCP 往返**；需求要素从 MD 提取；仅当移交结果缺失/过期（跨会话）时才重新 `query_requirement_flow`；
- 三种模式都从 `query_requirement_flow` 结果拿全：

1. **前置硬闸门**（模式B 来自 `query_requirement`；模式A 来自 `query_requirement_flow` 的 `boardName` + 已读 MD 文档）：
   - **P1 需求状态**：`boardName` 须为「讨论中/待受理/待拆分」等可拆状态，已上线/已终止/草稿不可拆；
   - **P2 受理人/提交部门**：确认本需求归属（受理人、共同受理人、提交部门）；
   - **P3 评审前置**：确认需求已完成评审（有评审纪要/结论）才允许拆 Story；
   - 提取需求要素：优先级（P0-P4）、所属组/实施工程/系统/模块、是否需要开发/SIT/UAT/设计走查/业务验收、开发/SIT/UAT/业务验收负责人（模式A 从 MD 提取）。
2. **可执行操作校验**（来自 query_requirement_flow）：确认当前用户可执行操作集合含「创建 Story」，不可用则停止并提示。
3. **逐系统幂等检查**（来自 query_requirement_flow 的 `stories[]`，2026-08-21 实测比 query_story 实时准确）：对「改造范围」内**每个系统逐一比对**已有 Story：
   - 已存在同系统 Story → **跳过该系统**，继续检查下一个；
   - 仅对「未存在 Story 的系统」进入 Step 4 创建。
   - `query_story` **仅在 flow 无 stories 字段时兜底调用**（其按 demandId 过滤存在索引口径问题，可能误报"未查询到"）。

> ⛔ **硬闸门失败即停**：任一前置不满足，向用户说明原因并停止，不得强行拆分（防孤儿 Story）。

### Step 4：逐条创建 Story（两段式确认，核心）
**仅对 Step 1+2+3 幂等检查判定为「未存在 Story」的改造范围系统创建改造类 Story**（改造范围须已过滤**非本组负责系统**，见业务规则 #3——他组/厂商系统不拆，由他组自行拆分）。
对「联测涉及系统」：**仅在涉及白名单系统（集中交易、低延时、集中清算、参数中心、三方存管）时自动拆分配合测试 Story**；其他系统（如集中营运）一律不拆 Story，仅在报告/纪要中记录其联测配合关系。

对每个**待创建系统**，构造 `create_story` 参数：

| 参数 | 取值规则 |
|---|---|
| `demandId` | 需求编号（必填） |
| `summary` | Story 名称（2026-08-21 修订）：改造类=**需求名称**（与父需求同名，如「【低延时两融】上海董监高文件数据导入的优化需求」）；配合类=**`【配合测试】`+需求名称**（仅联测白名单系统自动创建，见业务规则 #3/#5） |
| `systemId`/`systemModuleId`/`projectId`/`tId` | **级联方向 = team(tId)→project(projectId)→system(systemId)**（2026-11-04 20 轮实验修正）：**先传 `tId` + `projectId`**（tId/projectId 传**名称**或 option value 均可，例如 tId=「交易技术组」、projectId=「集中交易平台持续建设项目」）→ 服务端返回 NEEDS_INPUT 且 options 含该 project 下 **system options → 提取 `systemId` 的 option value（长 ID 权威值）回填**再 prepare。⚠️ **`systemId` 必须传 option value，严禁传名称**：名称虽回显 `[ready]` 但服务端内部 project→system 归属校验失败（表现为 **Project 被标 invalid**，实验4/5 vs 实验6/20）；⚠️ **`systemId` 严禁传 demand.groupId 等短 ID**（如 37 系 R2610270069 的 groupId=信用，非系统 ID，曾误导排查）；表内系统直接全套装 option value 直传免探测（见业务规则 #4）；**getSystems 404 与 systemId 传参无关**（见 Step 4 修正：真正触发点是灰度关联系统校验） |
| `priority` | 需求级别 P0-P4 |
| `isHaveDev`/`isHaveTest`/`isHaveUat`/`isDesignWalkthrough`/`isHaveBus` | 1/0，按需求要素与系统角色推断；⚠️ **配合测试类「是否需要开发」同样选「是」=1**（`isHaveDev` 不设 0，2026-10-12 用户纠正）；⚠️ **UAT 需要测试：`isHaveUat` 一律选「是」=1**（⛔ 不设 0，2026-10-12 用户手工修改 Story 后固化：创建时若设 0，服务端虽可能联动置 1 但不可依赖，须显式传 1）；⚠️ **设计走查：`isDesignWalkthrough` 一律选「否」=0**（⛔ 不设 1，2026-10-14 用户固化：走查=否时无需 Designer，同时不传 `designerId`） |
| `devManagePersonId`/`testManagePersonId`/`uatUserId` | **一律按业务规则 #4 模版映射表的默认负责人填写**（模版 devHeader/testHeader/uatHeader），禁止用评审研发人员或近期 Story 惯例替代；⚠️ **配合测试类同样必须填 `devManagePersonId`**——用该系统模版默认开发负责人（如集中清算→周哲博-015880），**不得留空**（2026-10-12 用户要求固化）；⚠️ **人员三字段一律传「姓名-工号」完整格式**（如 `周哲博-015880`），**严禁传纯工号**——服务端按「姓名-工号」规范化，纯工号（`110091`）会与规范化全集不一致触发 `Confirmed values changed` 重试（2026-11-05 R2610290057 实测） |
| `designerId`/`businessAcceptor` | **设计师不填**（`isDesignWalkthrough=0` 时一律不传 `designerId`，2026-10-14 用户固化）；业务验收人=需求提出人（服务端解析） |
| `description` | Story 富文本描述：**拷贝父需求描述**（`descSourceType=1`），可追加本系统改造要点。⚠️ **必须显式传 `description` 字符串**（即使 `descSourceType=1`）——否则首次 prepare 返回 `NEEDS_INPUT`（missingFields:["description"]）需补填后重新 prepare，增加 1 轮往返（2026-10-14 R2609160118 实测）；改造类 Story 传父需求背景+本系统改造点，配合类/清算类传对应系统清算逻辑描述 |
| `systemLabelId` | **所属系统标签**（扩展属性，随 `values` 传）：两融/质押业务 → `335`（场内信用交易）；其他 → `333`（场内现货交易）。详见业务规则 #11 |
| `bchildTypeCode` | **二级需求类型**（扩展属性）：功能 → `"1000021"`。详见业务规则 #11 |
| `isEffectGrayUpgrade` | **是否影响灰度升级**（扩展属性）：按评审纪要「灰度上线关注」判定，`1`/`0`。详见业务规则 #11 |
| `values` | 扩展属性（systemLabelId/bchildTypeCode/isEffectGrayUpgrade）随此传；续跑/重试时用相同参数重新 prepare 即可（服务端重新级联解析），无需回传上次 normalizedValues——如需引用已解析工号，可从确认摘要「业务参数」JSON 读取 |

**两段式确认协议（工具通道版：prepare 直出令牌，2026-08-28 实测，弃用脚本）**：
1. **并行 prepare（单消息）**：对全部「待创建系统」在**同一条消息内并行**调用 `create_story`（不传 `confirmed`）——工具通道直接返回每条的 `mcpContinuation`（含 `confirmationToken` + `expectedUpdateTime` + `requestId` + 规范化 `submitArguments`，Agent 可见，无需脚本/HTTP 重放）。汇总各条 normalizedValues 工号后**一次性展示确认摘要表**（系统 / 开发 / SIT / UAT / 标签）；
   > 旧路径 `kjptai_prepare.py` 子进程已弃用（`create_story` prepare 工具通道即可直出令牌）；该脚本仅保留作 `start_technical_evaluation` 的兜底（见 Step 6）。
2. **用户确认（`--yes` 时跳过）**：默认等待对话中**明确确认**；命令带 `--yes` 时直接进入提交（落库参数与两段式完全一致）。
   > 💡 **二合一授权（2026-10-14 新增）**：确认摘要展示后可回复 **「确认」**（仅拆分）或 **「确认并评估」**（拆分 + 随后自动发起技术评估）——后者等价于对 Step 6 发起评估的**明确同意**，拆分提交后直接预取令牌提交评估、**不再二次询问**（详见 Step 6），省 1 轮用户确认（典型单系统需求墙钟约省 30~60s）。
> 💡 **编号快速确认（2026-10-14 新增，用户要求「回复 1、2 方便快速」）**：确认摘要末尾固定展示 **「回复 **1**=仅拆分（确认）；**2**=拆分并发起技术评估（确认并评估）」**，用户回复单数字 `1`/`2` 等价对应「确认」/「确认并评估」，减少打字负担；摘要末尾同时注明「回复其他内容=重新展示摘要核对参数」。
   > 🔗 **跨技能移交时（2026-10-14 新增）**：若拆分授权已在 accept-review **全流程连跑**的评审确认时一并获取，本步**直接执行 Step 4 prepare→提交**、不再展示确认摘要等待二次确认（用户仅评审确认时已明确授权拆分）；仅当用户明确「仅评审/仅到评审为止」时，本步按两段式询问。
3. **确认提交（串行，因 updateTime 前移）**：用户确认后逐条提交——首条携带 `confirmed=true` + 其 `confirmationToken`/`expectedUpdateTime`/`requestId` 提交；**每条提交成功后需求 `updateTime` 前移，后续条必须重新 prepare 取新令牌再提交**（re-prepare 同样走工具通道，单条消息即可）。典型 3 条：submit1 → re-prepare2 → submit2 → re-prepare3 → submit3。
   > 📋 **提交参数模板（2026-11-04 R2610270069 三条全绿实证，防 `Confirmed values changed`）**：`arguments = {**base_args, "confirmed": True, "confirmationToken": token, "expectedUpdateTime": update, "requestId": rid, "_meta": {"sessionId": sid}}`，其中
   > `base_args = {**prepare_args, **submit_values}` 且 **`base_args["values"] = submit_values`**（`submit_values` = 本次 prepare 返回的服务端 `submitArguments.values` 规范化全集）——**双重覆盖**：顶层平铺字段 + 嵌套 `values` 均以服务端全集为准，唯一例外保留 `demandId`（服务端全集无 demandId 时补回）。**首条可用 prepare 时已保留的令牌直接提交；后续条必须同参数 re-prepare 取新三件套**（requestId 须取 re-prepare 服务端新生成值，仅 confirmationToken 相同≠已 re-prepare）。实测：3 条 Story 全流程（prepare 并行 + submit1→re-prepare2→submit2→re-prepare3→submit3）墙钟 **<60s**。
   > 🔌 **脚本直连（一键编排主路径，2026-11-05 提速固化；原「回退」语义升级）**：当工具通道 prepare 大响应（数百 KB fields+options）进对话拖慢节奏、或需批量执行/幂等重试时，**直接用 `scripts/split_stories.py` 一键编排**——`--stories` JSON 由 Agent 从上方参数表构造（`key`/`label`/`summary`/`args`=prepare 参数全集），单进程完成 flow 闸门+幂等 → 并行 prepare（线程池）→ 串行提交（含自动 re-prepare），`--dry-run` 演练零副作用、产物落盘 `/tmp/kjptai_story_*_prepare.json` 可复用，幂等全部跳过=exit 2。底层复用 `scripts/submit_stories.py`（自动扫描产物→首条缓存令牌→后续条自动 re-prepare→values 双层回传模板，`--dry-run` 预检）与 accept-review 新版 `kjptai_prepare.py`（无状态 JWE 直连+内置禁代理+会话缓存 5min TTL）；真实提交经 2 需求验证（R2610270069 三系统 prepare 并行+全命中 `{"created":true}` <60s；R2610290057 dry-run 2 条幂等 SKIP 3.2s）。工具通道不可用（ToolSearch 无 create_story）时同走本路径。旧版 `gtht-story-split/scripts/kjptai_prepare.py`（5.4KB，有 initialize 握手、无禁代理）**已弃用**。
4. **提交后回查**：全部 Story 建完后统一回查一次 `query_requirement_flow` 验证（Step 5）。

> ⚠️ **多条 Story 不得批量跳过确认**（默认模式）：每条系统都须出现在确认摘要表并经用户确认；`--yes` 仅命令显式 opt-in 时跳过。
>
> ⚠️ **re-prepare 硬约束**：上一条提交使 `updateTime` 前移、旧令牌失效，后续条务必 re-prepare（同参数，工具通道直出新令牌），严禁复用旧令牌提交（会报 expectedUpdateTime 不匹配）。
>
> ⚠️ **异常说明**：某条 prepare 返回 `NEEDS_INPUT`（参数不全/名称未转 ID）时，按业务规则 #4 补全参数重跑该条；其余条不受影响。
>
> 💡 **单 Story 场景（2026-09-02 补充）**：改造范围仅 1 个系统时，prepare → 确认 → 提交即可，**无需 re-prepare**（无 updateTime 前移问题），提交后直接进入 Step 5 回查。
>
> ⚠️ **令牌时效与过期重试（2026-09-16 实测新增）**：`confirmationToken` 存在时效——prepare 后跨轮次确认（用户思考/回复间隔较长）会失效，提交报「确认令牌已过期，请重新准备并确认操作」。处理流程：① 先 `query_requirement_flow` 确认需求状态未变（stories[] 为空即未落库、参数未变）；② 同参数重新 prepare 取新令牌提交即可，**无需再次询问用户**（业务参数完全一致，用户已确认过该操作）。实测：R2609160070 首次提交令牌过期（Ihu9Ip0…）→ 重 prepare 新令牌（_Hg-Ejts…）一次成功。
>
> ⚠️ **提交参数完整性——必须携带 `expectedUpdateTime`（2026-10-14 R2609280016 实测 P0）**：提交请求（`confirmed=true`）必须携带**同一次 prepare** 返回的 `submitArguments.expectedUpdateTime`，与 `confirmationToken`、`requestId` **三者一体**提交，缺一不可——只带 `confirmationToken`+`requestId`+`confirmed`+`values` 会被服务端以 `NEEDS_INPUT` 拒绝（`missingFields: ["expectedUpdateTime"]`，提示「缺少：expectedUpdateTime」）。`expectedUpdateTime` 不可省略、不可猜测、不可跨 prepare 复用，必须取自**本次最新一次 prepare** 的 `submitArguments`。
>
> ⚠️ **提交失败恢复路径（令牌/requestId/expectedUpdateTime 三者一体，2026-10-14 R2609280016 实测 P1）**：提交被拒（令牌过期 / 缺参 / NEEDS_CONFIRMATION）时按序恢复：① 先 `query_requirement_flow` 校验幂等——需求状态未变（`boardName` 仍为可拆状态、`stories[]` 为空即未落库、业务参数一致）才继续；② 同参数**重新 prepare**；③ 用**本次重新 prepare 服务端新生成**的 `requestId` + `confirmationToken` + `expectedUpdateTime` 三者一体提交。⚠️ **判据=requestId 是否本次 prepare 新生成**——`confirmationToken` 是内容确定性哈希（同一状态内容结果相同），**不能作为「已重新 prepare」的判据**；复用旧 requestId/旧令牌必被拒。用户已确认过相同业务参数时**无需再次询问**，直接重 prepare 提交。实测：R2609280016 二轮提交缺 `expectedUpdateTime` 被拒（仍用旧 requestId）→ 重新 prepare 后新三件套（requestId=3ae03058…）一次提交 `{"created":true}` 成功。
>
> ⚠️ **提交 values 必须逐字等于服务端 `submitArguments.values`（normalizedValues，P0）**：`create_story` 提交（`confirmed=true`）时 `values` **必须原样回传本次 prepare 返回的服务端规范化全集（完整字段、类型一致）**，否则 EXECUTE 阶段报 **`Confirmed values changed; prepare again`**。⚠️ **服务端规范化结果因需求/版本而异，一律以本次返回的全集为准、严禁凭旧例自行删字段**：① 旧例 R2609210085（2026-10-28）服务端曾丢弃 `bchildTypeCode`；② 新实证 **R2610270069（2026-11-04 三条 Story 一次全绿）服务端 `submitArguments.values` 明确保留 `bchildTypeCode:"1000021"`**——直接原样全集回传（含 bchildTypeCode）提交一次 `{"created":true}` 成功；③ **`isEffectGrayUpgrade` 类型被规范化为字符串**——传 int `0` 返回 `"0"`，提交须用字符串。**最稳妥做法（2026-11-04 实证模板）**：提交 `base = {**args, **submitValues}` 且 `base["values"] = submitValues`（嵌套 values 同时替换为规范化全集，顶层平铺字段亦用全集覆盖），不自行增删/改类型。

> ⚠️ **级联探测 + getSystems 404 熔断（2026-11-04 R2610270069 20 轮实验修正 P0，防盲目换参）**：
> - **级联方向 = team→project→system，systemId 必须用 option value**：prepare 遇 NEEDS_INPUT 时**先传 `tId` + `projectId`（名称或 option value 均可）** → 服务端返回 NEEDS_INPUT 且 `questions[].options` 含该 project 下 **system options（`value`=systemId option value 长 ID）** → 自动提取回填 `systemId` 后再 prepare。**`systemId` 严禁传名称或短 ID**——名称虽回显 `[ready]` 但归属校验失败（Project 标 invalid），非 404；
> - **getSystems 404 真正触发点 = 灰度关联系统校验（实验 J/K/L 三连 404 实证）**：`values.isEffectGrayUpgrade="1"` 且 `values.grayUpgradeRelateSystem` **非空**（无论传存量 ID 数组/名称/本需求 ID，全部 404）→ 服务端内部调 `api/pdmCmdb/getSystems` 校验关联系统 → **该 REST 接口路由缺失（Spring 404），系服务端 bug，非传参可解**。**识别口诀**：报错含 **`getSystems`/`api/pdmCmdb/getSystems`/HTTP 404** 且当前参数带 `isEffectGrayUpgrade=1`+关联系统 → 判定服务端故障，立即熔断停止换参，向用户报告「服务端 `getSystems` 接口故障，需平台修复或用 UI 手动拆分」；**唯一可行绕法**：`isEffectGrayUpgrade="0"` 先建 Story（实验 I 正常）→ 建好后平台 UI 补灰度，或 UI 手动拆；**最多仅允许 1 次**「projectId → options 提取 systemId」标准重试，其余一律熔断；
> - **旧结论已推翻（勿再引用）**：①「flow 上下文存量系统=唯一绿洲」——实验 J 存量系统 ID（顶点两融 15613696414889GKY6）同样 404；②「systemId 名称传参触发 404」——名称导致的是 Project invalid 而非 404；③「换参数/调序可解」——404 与 systemId 传参无关，改参数无效；
> - **速判口诀**：`Project: <empty> [invalid]` → 检查 systemId 是否传了名称（改用 option value）；报 404 且带灰度=1+关联系统 → 停，报告服务端故障；`systemId=37` 类短 ID 是 demand.groupId 混淆，不是系统 ID → 停。

### Step 5：回查双保险
全部提交后回查核对（**优先用 `query_requirement_flow`**，其 `stories` 数组实时准确；`query_story` 按 demandId 过滤存在索引口径问题，可能误报"未查询到"）：
- 核对创建的 Story 数与预期一致、状态正常（新建后应为「待同步/待确认、未发起评估」）；
- 核对扩展属性三件套：`systemLabelName`（系统标签）、`bchildTypeCode`（二级需求类型）、`isEffectGrayUpgrade`（灰度升级）与业务规则 #11 取值一致；
- 核对属性开关：`isDesignWalkthrough=0`（设计走查一律否，2026-10-14 固化）、无 `designerId`（未传 Designer）；
- 核对**开发/UAT 属性**：`isHaveDev=1`、`isHaveUat=1`（UAT 需要测试，2026-10-12 用户固化）——若为 0 须报告并提示平台编辑该 Story（服务端可能因业务验收人联动置 1，但不可依赖）；
- 不一致则向用户报告差异并定位原因。
- ⚡ **并行合并（2026-09-10 新增）**：`create_story` 提交成功已返回完整 Story（含扩展属性三件套、负责人、系统），**Step 5 回查可并入 Step 6 检查**——直接调用 `query_technical_evaluation_progress`（其 `stories[]` 含全字段，可同时完成 Step 5 回查 + Step 6 幂等检查），**省 1 次 `query_requirement_flow` 往返**；仅当用户明确不发起评估时才单独 `query_requirement_flow` 做 Step 5 回查。

### Step 6：发起技术评估（先检查 → 询问用户 → 用户同意才发起，2026-08-28 优化）
**默认不自动发起**；且**即使命令带 `--yes`，本步仍须用户明确同意**（评估会通知各负责人，属对外动作，不纳入预授权）。创建完 Story 并回查后，按以下顺序：

1. **检查（幂等 + 就绪）**：调用 `mcp__kjptai__query_technical_evaluation_progress(demandId="R26xxxxxxx")`：
   - 若**已发起过评估**（story 已有 `itEvaluationStatusName` / completed=true）→ **跳过**，告知用户「评估已发起」，流程结束；
   - 若未发起 → 确认 Step 5 回查通过（Story 齐全、状态正常）后，进入第 2 步。
2. **询问用户 + 令牌预取（并行，2026-09-16 优化）**：**若 Step 4 用户已回复「确认并评估」（即已明确同意），跳过本步询问，直接进入预取+提交**；否则向用户报告「Story 已就绪（N 个），评估尚未发起」，**明确询问是否现在发起技术评估**；**同时**（同一条消息内、不等用户回复）调用 DeferExecuteTool `start_technical_evaluation`（不传 `confirmed`）prepare——若工具通道直出 `confirmationToken` 则直接使用；若不直出（同 accept-review 的 review/accept 现象），回退运行 `scripts/kjptai_prepare.py --tool start_technical_evaluation --args '{"demandId":"R26xxxxxxx","reloadEvaluateMessage":"0"}'` 提取令牌。一步返回确认摘要（评估人、范围、待评估 Story 列表）+ 令牌参数；
   > ⚡ **令牌预取收益**：prepare 与用户思考确认并行执行，用户同意后**直接提交**，省 1 次串行 prepare 往返（墙钟约 5~10s）。令牌无 updateTime 依赖风险（本步前无其他写操作，令牌不会失效）。
3. **提交**：用户明确同意后，携带 `confirmed=true` + `confirmationToken` + `expectedUpdateTime` + `requestId` + `_meta.sessionId` 提交；
4. **回查（可省，2026-09-10 优化）**：`start_technical_evaluation` 提交成功返回 `SUCCESS` 即已落库，**默认不再额外调用 `query_technical_evaluation_progress` 确认**（省 1 次往返）；仅当用户要求确认或需向用户展示评估后看板状态时，才回查确认：`allCompleted=true` 且各 Story 进入「待开发/SIT/UAT测试评估」看板（2026-08-21 实测：发起后 story `itEvaluationStatusName`=待开发/SIT测试评估（无UAT）或 待开发/SIT/UAT测试评估（有UAT），开发/SIT/UAT completed 均=true）。

> ⛔ **禁止未经询问直接发起技术评估**——评估会通知各负责人，属对外动作，必须先经用户明确同意（业务规则 #10），`--yes` 不覆盖本步。令牌预取仅是「提前 prepare 备好令牌」，**提交动作仍须用户同意后执行**。

### Step 6.5：拆分完成后提醒排期修改与价值量登记（2026-09-02 新增）
**Story 拆分（及技术评估）完成后，必须主动向用户提醒后续收尾动作**：
1. **排期修改提醒**：提示「Story 已拆分/评估完成，如需设置计划生产排期，可使用 `/adjust-plandate <需求编号> <YYYYMMDD>` 一键修改」；
2. **价值量登记提醒**：同步提示「如需登记非开发工作量（NDW/价值量），可使用 `/gtht-ndw-fill <需求编号>` 一键评估登记」；
3. **触发时机**：Step 5 回查通过后、或 Step 6 技术评估发起完成后，作为收尾提示一次性输出；
4. **不强推**：仅作提醒，不擅自调用 `/adjust-plandate` 或 `/gtht-ndw-fill`（排期与价值量均属业务确认动作，须用户明确发起）；用户明确要求时才执行。
5. **MD 文件 status 状态同步（2026-09-10 新增，R2609090040 沉淀）**：Story 拆分 + 技术评估完成后，若对应 `ba-to-dev` 需求分析 MD 文档存在，**主动提醒用户同步更新 Front Matter 的 `status` 状态**（`待拆分` → `技术评估中`），并新增 `story: [S2609100xxx]` 字段记录本次拆分的 Story 编号，保持本地 MD 与平台看板状态一致。用户明确要求时同步更新（如「md 文件 status 同步更新」）；不强推、不擅自改写用户未确认的字段。

### Step 7（可选）：Story → Task 草稿
用户明确要求「拆 Task」时，调用 `mcp__kjptai__split_story_to_tasks(storyNo="S26xxxxxxx")` 生成 Task 草稿；仅当用户说「创建单个 task」时用 `create_task`。

---

## 📐 业务规则（强制）

1. **前置硬闸门**：P1 状态/P2 归属/P3 评审任一不满足即停，防孤儿 Story；
2. **幂等**：已有同系统 Story 跳过创建，不重复拆；
3. **拆分范围=改造范围+联测白名单**：改造范围系统一律创建改造类 Story；「联测涉及系统」**仅当涉及白名单系统（集中交易、低延时、集中清算、参数中心、三方存管）时才自动拆分配合测试 Story**，其他系统（如集中营运）一律不拆 Story，仅记录联测配合关系；⛔ **「交易参数管理前台系统」豁免拆分（2026-10-15 用户固化，R2609220085 实测）**：改造范围即使出现该系统，**不创建独立 Story**——前台系统为后台系统的界面层（参数/办理端 web 界面，不承载独立业务逻辑），其改造随「交易参数管理后台系统」Story 一并评估；⛔ **「非本组负责系统」豁免拆分（2026-11-05 用户固化，R2610290057 实测）**：改造范围/联测涉及系统中出现的**他组负责系统**（如互联网融资系统、互联网三方交易中台系统、君弘APP交易大智慧子系统、顶点两融交易系统等厂商/他组系统）**一律不创建 Story**——由他组自行拆分，本技能仅处理**本组负责系统**（集中交易/低延时/集中清算/参数中心等，判定依据=评审纪要标注的系统归属，对齐 ba-to-dev P0 规则19「非本组系统改造描述不展开」），其改造/联测配合关系在报告与纪要中记录即可；实证：R2610290057 评审纪要【改造范围】含互联网融资系统（对应「富易和君弘客户端更换新跳转地址」），用户明确「**互联网融资系统 非我组系统，不需要拆 story**」，仅拆集中交易系统（改造类）+ 集中清算系统（联测配合测试类）两条 Story；**用户明确指示某改造范围系统不拆分时以用户指示为先**（用户指示＞改造范围）;
4. **系统→模版映射（强制）**：按改造范围系统套用对应模版，模版决定 `systemId`/`projectId`/`tId`/`systemModuleId`/开发/SIT/UAT 负责人 的取值，禁止自行改用其他系统变体、禁止用评审研发人员替代模版默认负责人：

| 改造范围系统 | 套用模版 | `systemId` 实际取值 | 所属组 | 实施工程 | 系统模块 | 开发负责人(底层工号) | SIT 负责人(底层工号) | UAT 负责人(底层工号) | 验证状态 |
|---|---|---|---|---|---|---|---|---|---|
| 低延时交易系统 | **低延时信创域** | `低延时交易系统(大集中-信创域)`（**不是** 信创域2） | — | NGTP持续建设 | 现货交易模块 | 刘勇明-014611 | 杜军辉-024090 | 刘慧雨-028581 | ✅已实建 |
| 低延时交易系统 | **低延时创新域** | `低延时交易系统（创新域）` | 交易技术组 | NGTP持续建设 | 两融交易模块 | 刘勇明-014611 | 刘牧青-028643 | 聂章艳-025996 | ✅已实建(R2608070169) |
| 集中交易系统 | **集中交易系统** | `集中交易系统` | — | 集中交易平台持续建设项目 | 两融模块 | 胡玲杰-014013 | 高健-026249 | 李萍萍-017417 | ✅已实建 |
| 交易参数管理后台系统 | **交易参数管理后台系统** | `交易参数管理后台系统` | 交易技术组 | 参数中心持续建设 | 业务模块 | 胡玲杰-014013 | 高健-026249 | 丁伟-022028 | ✅已实建(R2608210053) |
| 客户登记管理系统 | **客户登记管理系统** | `客户登记管理系统` | 清算技术组 | 集中清算平台持续建设项目 | 中间件 | 孙茂文-待回查 | 茆莹莹-待回查 | 刘青-待回查 | ⚠️待回查底层工号 |
| 集中清算系统 | **集中清算系统** | `集中清算系统` | 清算技术组 | 集中清算平台持续建设项目 | 经纪分区 | 周哲博-015880 | 曾娟-035764 | 刘青-016379 | ✅已实建(R2608070169) |
| 低延时全局风控系统 | **低延时全局风控系统** | `低延时全局风控系统` | 交易技术组 | 低延时全局风控域持续建设 | 风控模块 | 刘勇明-014611 | 杜军辉-117790 | 刘慧雨-124577 | ⚠️待首次实建回查底层工号 |
| 全业务实时资产计算中心系统 | **全业务实时资产计算中心系统** | `全业务实时资产计算中心系统` | 清算技术组 | 实时资产计算中心持续建设 | 资产核心 | 杨志华-待回查底层(New 111473) | 茆莹莹-待回查底层(New 117966) | —（UAT自测=否） | ⚠️待首次实建回查底层工号（2026-10-23 截图更新：实施工程/系统模块有变） |

> ⚠️ **低延时创新域系统名称统一（2026-10-20 用户指示）**：低延时创新域系统名称**统一使用 `低延时交易系统（创新域）`（全角括号）**，**严禁再出现/选择「两融创新域」字样**（旧称 `低延时交易系统(两融创新域)` 已废弃）；拆分 Story、填写 systemId 字典、评审纪要/需求文档引用时一律用新名称，勿与「低延时交易系统(大集中-信创域)」混淆（括号内为「创新域」三字，无「两融」前缀）。

   > 🔀 **低延时交易系统「信创域 vs 创新域」分流规则（2026-09-02 修订）**：两个模版**系统标签都是 `335`(场内信用交易)**，易混淆，**必须按「运行域」分流，严禁仅凭业务关键词默认套用**：
   > | 判定依据 | 套用模版 | 适用场景 |
   > |---|---|---|
   > | 需求运行在 **98 创新域**（内容涉及 **「个微」/「98」/「G1」** 任一关键词，或明确标注「创新域」「两融柜台节点」） | **低延时创新域** → `低延时交易系统（创新域）` | 98 创新域（与 EOA/upt_order 中的「98 创新域」对应），**系统模块=两融交易模块** |
   > | 其余（默认 **95 信创域**，含债券质押式融资回购、融资额度控制、使用率/负债率等两融/信用业务） | **低延时信创域** → `低延时交易系统(大集中-信创域)` | 95 信创域 |
   >
   > ⚠️ **关键纠正（2026-09-02 实测 R2609020049）**：**业务是否属两融/信用（如标题含「融资」「两融」「保证金」「维保」）不是选创新域的依据**——债券质押式融资回购、融资额度控制等两融/信用业务**默认运行在 95 信创域**，须用信创域模版。**只有明确运行在 98 创新域（个微两融节点）的需求才用创新域模版**。
   >
   > 负责人组合完全不一样：信创域=刘勇明/杜军辉/刘慧雨，创新域=刘勇明(同)/刘牧青/聂章艳。**首次拆分时**若 ID 字典尚未实建回查「创新域」级联 ID，必须先经用户确认或回查存量 Story 补全（systemId/projectId/tId/systemModuleId/底层工号）后再 prepare，**严禁用「低延时信创域」的 ID 字典套到「创新域」Story 上**（systemId 指向不同实例）。
   >
   > 🔒 **分流兜底（2026-09-02 修订）**：① 需求内容**同时命中**「个微」/「98」/「G1」多个关键词——仍按「创新域」处理（关键词同源，无冲突）；② 需求内容**未命中**「个微/98/G1」关键词，**即使业务明显属两融/信用（如含「融资」「两融」「保证金」「维保」）** → **一律按「信创域」处理**（两融/信用业务默认 95 信创域，不落入创新域）；③ 完全无法判定时**停止并询问用户**，禁止默认套用任一域。
   >
   > 🔒 **域判定最高优先级规则（2026-10-08 修订，R2609140034 实测沉淀）**：**拆分对象与模板域判定以「用户指示 / 评审纪要『改造范围：』」为最高权威**，**MD 全文关键词仅为参考、严禁作为创新域判定依据**：
   > - **MD 中「xx 域」字样（如「仅 96/98 域账号」「85/95/集中交易」）多为业务描述语**——用于描述灰度范围 / 存量运行域，**不是**该系统运行于创新域的依据；即使命中「98」/「G1」关键词，只要评审纪要「改造范围：」标注的系统为低延时交易系统且用户明确「不涉及创新域 / 按改造范围拆分」，**一律套用「低延时信创域」模版**；
   > - **判域顺序**：① 用户明确指示（「按改造范围拆分」「不涉及创新域」等）＞ ② 评审纪要「改造范围：」标注的系统 ＞ ③ 需求运行域明确标注（创新域/信创域）＞ ④ 业务关键词（仅参考）；**上一级有结论即停止，不再依赖下一级关键词**；仍存疑时停止询问用户，禁止默认套用任一域；
   > - **实测案例（R2609140034，P4）**：需求正文含「仅 96/98 域账号新算法、85/95/集中交易老算法」（灰度范围描述）→ 按关键词曾误判「创新域」；用户纠正「根据评审纪要改造范围拆分，不涉及创新域」→ 改套「信创域」模版（低延时交易系统(大集中-信创域)，刘勇明/杜军辉/刘慧雨）创建 **S2610080018** 成功。

   > 🔀 **同业务跨节点/域复刻的 Story 拆分（2026-09-10 新增，R2609090045 沉淀）**：当需求识别为「同业务跨节点复刻落地」（如 R2609090045 低延时个微两融QFII 复刻 R2603270061 低延时两融QFII交易节点，均属「担保物转出不冻结持仓」，标题核心词一致）时：
   > - **模版严格按「运行域」分流，严禁照搬源节点负责人**：命中「个微/98/G1」→ 创新域模版（刘勇明/刘牧青/聂章艳）；未命中 → 信创域模版（刘勇明/杜军辉/刘慧雨）。**跨域复刻 ≠ 同负责人**——不同运行域负责人组合不同，必须按本需求所属域模版填，不得沿用源节点 Story 的负责人（即使业务一致）；
   > - **改造范围/风控口径对齐源节点**：参考源节点已上线 Story（R2603270061 → S2604080063、S2604200073）的改造范围与业务验收口径，确保复刻节点功能与源节点一致不遗漏；
   > - **描述标注复刻关系**：在 Story `description` 标注「复刻自 R2603270061（已上线·大集中-信创域），实现方案/风控口径对齐复用」，供研发参考（与 ba-to-dev 规则 11 关联需求引用一致）；
   > - **扩展属性三件套**：两融/信用业务 → `systemLabelId=335`（场内信用交易），与源节点一致。

   > 🔀 **「低延时全局风控系统」模版分流规则（2026-09-07 固化）**：需求内容涉及 **「GRC」**（全局风控/Global Risk Control）关键词 → 套用「**低延时全局风控系统**」模版，**不再走低延时交易系统模版**（业务虽属低延时但归属系统不同：交易系统做订单，全局风控做限额/阻断/监控）。**适用场景**：交易风阻断控制、低延时全局风控域改造等。
   > - 负责人：开发=刘勇明（与信创域同开发）、SIT=杜军辉（New 117790）、UAT=刘慧雨（New 124577）——SIT/UAT 工号与信创域**底层 024090/028581 不一致**（实际是同一组人但截图显示 New 工号，底层待回查）。
   > - 与「低延时交易系统(大集中-信创域)」**开发负责人同为刘勇明**，**严禁混用**：两者 systemId 指向不同实例，SIT/UAT 也不同。
   > - **首次实建前**需回查存量 GRC Story（涉及「GRC」关键词的需求）补全 systemId/projectId/tId/systemModuleId 及 SIT/UAT 底层工号。

   > 模版负责人数据源（纯 MCP）：调用 `query_requirement_flow` 读取**存量 Story** 的级联字段（systemId/projectId/tId/systemModuleId/devHeaderName/testHeaderName/uatUserName）**回查验证**；首次使用某系统的模版映射需经用户确认后固化到本表（2026-08-21 实测：R2608110058 存量 Story 提供低延时/集中交易真实级联 ID；**客户登记管理系统字段来自 2026-08-21 截图：技术研发部/清算技术组/集中清算平台持续建设项目/中间件/资金清算；开发负责人=孙茂文-117238、SIT负责人=茆莹莹-117966、UAT负责人=刘青-110436**；**集中清算系统字段来自 2026-09-01 截图：技术研发部/清算技术组/集中清算平台持续建设项目/经纪分区（模块 ID 11000162，截图文本 `经纪分区&&11000162`）/资金清算；开发负责人=周哲博-110091、SIT负责人=曾娟-113932、UAT负责人=刘青-110436**；**交易参数管理后台系统字段来自 2026-08-28 用户截图（展示 New 工号）+ R2608210053-3 实建回查（底层工号）：技术研发部/交易技术组/参数中心持续建设/业务模块/场内交易产品管理标签(369)；开发负责人=胡玲杰(底层014013/New108495)、SIT负责人=高健(底层026249/New120642)、UAT负责人=丁伟(底层022028/New115790)；级联 ID 从 R2608070010 存量 Story 回查验证，底层工号经 R2608210053-3 实建确认**）；**低延时交易系统（创新域）字段来自 2026-09-01 截图：技术研发部/交易技术组/NGTP持续建设/两融交易模块/场内信用交易；开发负责人=刘勇明-108980、SIT负责人=刘牧青-124581、UAT负责人=聂章艳-120199；适用场景=需求运行在 98 创新域（内容涉及「个微」/「98」/「G1」关键词之一；与「低延时交易系统(大集中-信创域)」95 信创域按「运行域」互斥分流，**两融/信用业务默认信创域**）**；**低延时全局风控系统字段来自 2026-09-07 截图：技术研发部/交易技术组/低延时全局风控域持续建设/风控模块/交易风险阻断控制（系统标签=交易风险阻断控制，**与场内现货/信用不同**，新字典待确认）；开发负责人=刘勇明-108980、SIT负责人=杜军辉-117790、UAT负责人=刘慧雨-124577（均为 New 工号，底层待回查）；适用场景=需求内容涉及「GRC」（全局风控/交易风险阻断）关键词；与低延时交易系统**严禁混用**（systemId/工号组合不同）。**用户未特别指定时，开发/SIT/UAT 负责人一律按本表模版默认值填写；仅业务验收人（businessAcceptor）按需求提出人填写。
   > ⚠️ **ID/工号传参原则（2026-09-01 修订）**：`systemId`/`projectId`/`tId`/`systemModuleId`/各负责人字段**优先传服务端 ID 值**；传平台显示名称是否可解析**因系统而异**（集中清算系统支持名称解析；低延时系统传名称会触发 NEEDS_INPUT 返回可选列表）。**最稳妥**：先按下方 ID 字典传 ID；字典未收录或解析失败时，用名称触发服务端返回可选级联列表，再取正确 ID 回填。**负责人字段一律传底层工号**（`create_story` 自动映射 New 工号；截图/回查显示的 New 工号不可直接传）。下方为实测 ID 字典：
   >
   > | 系统 | systemId | systemModuleId | projectId | tId | 开发(底层/New) | SIT(底层/New) | UAT(底层/New) | 系统标签 | 验证来源 |
   > |---|---|---|---|---|---|---|---|---|---|
   > | 低延时交易系统(大集中-信创域) | 164325248684900500 | 11000143 | 8b9c3ba71c974aeeb2 | a13fc2ddba0d446b86 | 刘勇明-014611/108980 | 杜军辉-024090/待回查 | 刘慧雨-028581/待回查 | 335 | R2608110058 |
   > | 低延时交易系统（创新域） | 158674333006900117 | 10000427 | 8b9c3ba71c974aeeb2 | a13fc2ddba0d446b86 | 刘勇明-014611/108980 | 刘牧青-028643/124581 | 聂章艳-025996/120199 | 335 | R2608070169 |
   > | 集中交易系统 | 142891263425277DZ1 | 10000192 | 1666659084248A2RIE | a13fc2ddba0d446b86 | 胡玲杰-014013/108495 | 高健-026249/120642 | 李萍萍-017417/111399 | 335 | R2608110058+R2609020047 |
   > | 交易参数管理后台系统 | 1585110383611MMQ3P | 10000385 | 3e11ea634e4a4a7ba1 | a13fc2ddba0d446b86 | 胡玲杰-014013/108495 | 高健-026249/120642 | 丁伟-022028/115790 | 369 | R2608210053 |
   > | 客户登记管理系统 | 待回查 | 待回查 | 待回查 | 待回查 | 孙茂文-待回查/117238 | 茆莹莹-待回查/117966 | 刘青-待回查/110436 | 358 | 截图 |
   > | 集中清算系统 | 1539073197362VTA7L | 11000162 | 16666895075975O7TS | 1316414976140JJU42 | 周哲博-015880/110091 | 曾娟-035764/113932 | 刘青-016379/110436 | 358 | R2608070169 |
   > | 低延时全局风控系统 | 待回查 | 待回查 | 待回查 | 待回查 | 刘勇明-014611/108980 | 杜军辉-024090/117790 | 刘慧雨-028581/124577 | 交易风险阻断控制(待确认ID) | 截图(待实建回查) |
   > | 全业务实时资产计算中心系统 | 待回查 | 待回查(资产核心) | 待回查 | 1316414976140JJU42(清算技术组) | 杨志华-待回查底层/111473 | 茆莹莹-待回查底层/117966 | —(UAT自测=否，不传uatUserId) | 境内现货估值(待确认ID) | 截图(2026-10-23，待实建回查) |
   >
   > - **全业务实时资产计算中心系统（2026-10-23 用户截图更新，覆盖 2026-10-22 旧版）**：产品版本=`2022年融资融券持中后台综建设`、产品模块=`信用中台`、所属部门=`技术研发部`、所属组=`清算技术组`、所属系统=`全业务实时资产计算中心系统`、实施工程=`实时资产计算中心持续建设`（⚠️ 2026-10-23 由「全业务实时资产计算中心」更新）、所属系统标签=`境内现货估值`（**新字典值，ID 待首次实建回查**）、所属系统模块=`资产核心`（⚠️ 2026-10-23 由「实时查询服务」更新，ID 待回查）、二级需求类型=`功能`(1000021)、需求级别=P3；属性开关（2026-10-22 截图二）：`isHaveDev=1`（开发负责人=杨志华，New 111473）、`isHaveTest=1`（SIT 负责人=茆莹莹，New 117966）、**`isHaveUat=0`（UAT自测=否，不传 `uatUserId`）**、`isDesignWalkthrough=0`（不传 `designerId`）。⚠️ **该系统为「UAT=否」系统级例外，覆盖规则 #5「isHaveUat 一律=1」默认值**（用户截图明确为准）；开发/SIT 负责人显示为 New 工号，**底层工号首次实建前须回查存量 Story 或由 `create_story` 服务端映射**。
   > - ⚠️ **ID 全直传免 getSystems（2026-11-04 实证）**：上表已收录系统的 `systemId` 均为**从存量 Story 回查的权威长 ID**（集中交易=142891263425277DZ1、集中清算=1539073197362VTA7L、交易参数管理后台=1585110383611MMQ3P 等），prepare 时**直接全套直传**（`tId`+`projectId`+`systemId`+`systemModuleId`）可**完全不触发**服务端 `getSystems` 调用（该接口 2026-11-04 起持续 404）；**表外新增系统**：严禁直接传名称/猜测 ID，按 Step 4「级联探测」——先传 `projectId` 长 ID → NEEDS_INPUT options 提取 systemId 权威值回填；**厂商系统（顶点两融交易系统等，不在本表）**：仅当 flow 上下文已有存量 Story（`stories[]` 命中，如顶点两融 15613696414889GKY6）时可正常解析（getSystems 故障下唯一绿洲），否则按 404 熔断分支处理（报告+可重跑脚本，不盲试）。
   > - `tId` 取值对照：交易技术组=`a13fc2ddba0d446b86`（低延时/集中交易/交易参数管理共用）；清算技术组=`1316414976140JJU42`（集中清算系统、全业务实时资产计算中心系统共用）。
   > - `businessAcceptor`（业务验收人）：**必须传需求提出人的真实工号（staffId）**，**严禁误用提交人工号（如 110287）或受理人工号**——否则 prepare 报 NEEDS_INPUT。**传参策略（2026-09-02 实测）**：**优先传提出人工号**，**传姓名会触发 NEEDS_INPUT**（返回可选列表且常无需求提出人）；传工号后服务端自动解析为底层工号。已确认提出人工号映射：王恒=`015804`（staffId 109936）、金渤文=`019055`、杜伟毅=`034393`。
>   > **NEEDS_INPUT 可选列表自动收集（2026-09-02 新增）**：`create_story` 返回 NEEDS_INPUT 时，`questions[].options` 含业务验收人候选（`value`=底层 workNo、`metadata.workNo`/`staffId` 双工号），须**自动提取该列表并入业务验收人工号字典**（供后续需求复用），再按需求提出人回填 `businessAcceptor`。典型：R2609020047 传"王恒"触发列表（无王恒），改传 staffId `109936` 解析为底层 `015804`。
   > - 扩展属性默认值：`systemLabelId=335`(场内信用交易)、`bchildTypeCode=1000021`(功能)、`isEffectGrayUpgrade=0`。
   > - **级联 systemModuleId 自动收集**：prepare 返回 NEEDS_INPUT 且缺 `systemModuleId` 时，从返回的可选级联列表中自动匹配「系统模块」名称并取 ID 回填；若匹配失败，将该列表展示给用户确认。
   > - **新系统模版映射**经用户确认后追加到本表；待回查项首次使用前先回查存量 Story 或经用户确认补全。
5. **Story 名称=需求名称**：改造类 Story 名称直接取**父需求名称**（不再用「系统名+改造」）；配合类=`【配合测试】`+需求名称；⚠️ **配合测试类「是否需要开发」同样选择「是」=`isHaveDev=1`**（⛔ 2026-10-12 用户纠正：**不设 0**，拆分配合测试 Story 时该字段同样选「是」），`devManagePersonId` 按业务规则 #4 模版映射填该系统默认开发负责人（如集中清算→周哲博-015880）必填；⚠️ **所有 Story（含配合测试类）「是否需要UAT」一律选「是」=`isHaveUat=1`**（⛔ 2026-10-12 用户手工修改固化：UAT 需要测试，不设 0）；**配合类 Story 仅对联测白名单系统（集中交易、低延时、集中清算、参数中心、三方存管）创建**，白名单外系统（如集中营运）不拆；⚠️ **设计走查一律「否」=`isDesignWalkthrough=0`、`designerId` 不填**（2026-10-14 用户固化，走查=否时无需 Designer）；
6. **模板套用**：工程/系统/模块/人员按需求模板与系统配置级联推导，不手写死值；
7. **父描述拷贝**：Story 描述默认拷贝父需求描述，保证上下文完整；
8. **单次单需求**：一次只处理一个需求，防扩大化；
9. **回查双保险**：提交后必须回查核对；
10. **两段式确认 + Step 6 需用户明确指令**：所有写操作（create_story / start_technical_evaluation）必须先 prepare 展示确认摘要，用户对话中明确确认后提取令牌提交，禁止擅自落库；**发起技术评估属对外动作（通知各负责人），创建完 Story 后默认不发起，必须先向用户报告检查结果并询问，用户明确同意后才 prepare+提交**；**requestId/令牌复用规则（2026-10-08 新增，R2609140034 实测沉淀）**：正式提交返回 `NEEDS_CONFIRMATION` 时，**必须提取服务端最新返回的 `submitArguments.requestId` 与 `confirmationToken` 原样复用**——旧 requestId 已过期无效（曾致提交被拒），同一次提交超时重试也必须复用原 requestId（服务端 `retryRule="Reuse the same requestId for retries"`）；R2609140034 提交时曾用旧 requestId `1916ed1f-...` 被拒，换服务端新返 `ef7959d6-...` 后成功；**提交参数三件套（2026-10-14 追加，R2609280016 实测）**：提交须携带**同一次 prepare** 返回的 `expectedUpdateTime` 与 `requestId`、`confirmationToken` **三者一体**，缺 `expectedUpdateTime` 被拒（服务端 `NEEDS_INPUT`「缺少：expectedUpdateTime」）；重新 prepare 后必须用**本次新生成的 requestId** 提交——判据=requestId 是否本次新生成（令牌是内容哈希不可作判据）；**二合一确认（2026-10-14 追加）**：用户明确回复「确认并评估」即同时授权拆分提交与随后发起技术评估两个写动作（评估属对外通知仍须用户明确同意，但可在同一确认中一并授权，不违背本规则两段式原则）；
11. **Story 属性填写（所属系统标签 / 二级需求类型 / 是否影响灰度升级，2026-08-21 实测固化）**：`create_story` 标准 schema 不含这三个字段，作为扩展属性写入 `values`（或 prepare 后由用户在平台确认），平台侧字段名与取值：

    | 平台字段 | 含义 | 取值规则 | 已知字典值 |
    |---|---|---|---|
    | `systemLabelId` | 所属系统标签 | 需求业务属于**两融、质押** → 填「场内信用交易」；**客户登记管理系统 / 集中清算系统** → 填「资金清算」（2026-08-21 / 2026-09-01 截图确认）；**其他** → 填「场内现货交易」 | 335=场内信用交易、333=场内现货交易、369=场内交易产品管理、337=经纪交易接入、**358=资金清算**、576=模拟交易、429=监管报送（字典可从 `query_requirement_flow` 返回的存量 Story `systemLabelName` 字段聚合回查，纯 MCP） |
    | `bchildTypeCode` | 二级需求类型 | 默认填「功能」（开发改造类 Story） | 1000021=功能 |
    | `isEffectGrayUpgrade` | 是否影响灰度升级 | **依据 ba-to-dev 需求文档【评审纪要】中「灰度上线关注」结论**：为「是/有影响」→ `1`；为「否/无」→ `0` | 0/1 |

    > `isEffectGrayUpgrade=1` 时须一并填写 `grayUpgradeRelateSystem`（灰度升级涉及系统）与 `grayUpgradeRemarks`（灰度说明，取评审纪要原文）；`0` 时**两者不传**（留空省略，2026-11-04 R2610270069 三条全绿实证：灰度=0 且不传关联系统字段 → 一次成功，无 getSystems 404）。
    > 📌 **灰度取值 = 解析 ba-to-dev MD 评审纪要第 7 项「灰度上线关注」自动填写（2026-11-04 用户固化）**：第 7 项为「是/有影响」→ `isEffectGrayUpgrade="1"`；为「否/无」→ `"0"`；从 MD 提取而非用户口头/其它来源推断（本需求 R2610270069 评审纪要 7=否 → 灰度=0）。
    > 回查口径：`query_requirement_flow` 返回的 `stories[]` 中核对 `systemLabelName`/`bchildTypeCode`/`isEffectGrayUpgrade` 三字段。
12. **执行后自省与优化点输出（每次执行必做，对齐 ba-to-dev 规则 16 / gtht-accept-review 规则 17）**：每次实际执行 `/gtht-story-split` 完成 Story 拆分/技术评估后，在最终回复中**必须新增「🔧 本技能优化点」小节**，主动输出本次执行暴露的优化点，持续驱动技能迭代。输出采用四段式模板：
    - **① 执行摘要**：本次执行总耗时、拆分的 Story 数、执行的写操作（create_story / start_technical_evaluation）与状态流转（如 待拆分→待同步+技术评估）；
    - **② 优化点清单**：以表格 `# | 类别 | 优化点 | 影响 | 优先级 | 状态` 输出，类别覆盖——**性能**（MCP 往返次数、并行 prepare、ToolSearch 缓存、单 Story 免 re-prepare、模式A skip query_requirement）、**准确性**（模版映射/工号双体系、NEEDS_INPUT 级联收集、扩展属性三件套、幂等检查、回查双保险）、**流程**（Step 6 先询问再发起评估、Step 6.5 收尾提醒、单次单需求）；**仅输出「待落地」优化点**（已落地的不再重复提示）；
    - **③ 优先级定义**：`P0`=本次即可落地、收益显著；`P1`=需工程化改造；`P2`=体验/流程优化；
    - **④ 状态标注**：`已落地`=本次已采用；`待落地`=已提出待实施。**「已落地」的优化点不进入清单展示**（已生效，无需再提示），仅保留「待落地」项。
    - 优化点须**基于本次实际执行情况**输出，避免空泛套话；若本次执行已足够高效，如实标注「本次执行高效，无显著优化点」。
13. **execute 代码内 mcpContinuation 精简提取（2026-11-09 R2611050089 实测沉淀，防截断丢失）**：`create_story` / `start_technical_evaluation` 的 prepare 响应含大量嵌套结构（`normalizedValues` + `workflowDefinition` + `workflowTrace` + `stepContract`，合计数百 KB），`execute` 代码返回完整结果时**易被截断**，导致 `mcpContinuation` 丢失、被迫重新 prepare（浪费 1 轮往返）。**正确模式**：
    ```javascript
    // ❌ 错误：返回完整 prepareResult（易截断）
    return prepareResult;

    // ✅ 正确：只提取提交所需字段
    const mc = prepareResult?.mcpContinuation || prepareResult?.data?.mcpContinuation;
    if (!mc) return { status: prepareResult?.data?.status, topKeys: Object.keys(prepareResult||{}), dataKeys: prepareResult?.data ? Object.keys(prepareResult.data) : [] };
    const submitResult = await tools.kjptai.create_story({ ...mc.submitArguments, confirmed: true });
    return { submitStatus: submitResult?.status || submitResult?.data?.status, submitResult };
    ```
    **核心原则**：prepare 后**立即在同一 execute 代码块内提取 `mcpContinuation.submitArguments` 并提交**，不返回完整 prepare 响应到对话；仅当提取失败（无 mcpContinuation）时才返回调试信息（topKeys/dataKeys）。
14. **预授权一步模式（2026-11-09 R2611050089 实测沉淀，省 1 轮往返）**：当用户已在确认摘要时**明确预授权**（回复 `2`="拆分并发起技术评估"）且 prepare 返回 `missingFields=[]`、`normalizedValues` 与预期完全一致时，**同一轮 execute 代码块内完成 prepare → 检查 normalizedValues → submit**，无需再展示摘要等待二次确认。**适用条件**：① 用户已明确回复 `1`/`2` 预授权；② `missingFields=[]`；③ `normalizedValues` 中系统/人员/标签等关键字段与模版映射表一致（Spot check 3 个字段即可：systemName/devManagePerson/systemLabelName）。**不适用**：用户未预授权（首次展示摘要）、`missingFields` 非空、`normalizedValues` 与预期不符（需向用户展示差异）。
15. **query_requirement_flow 精简提取（2026-11-09 R2611050089 实测沉淀，token 降 ~60%）**：`query_requirement_flow` 返回约 53KB 嵌套 JSON（含 9 个 `availableActions` 完整对象，每个含 buttonId/buttonType/roleId/size/sort 等 10+ 字段），**execute 代码返回时只提取决策所需 3 个关键字段**：
    ```javascript
    // ✅ 精简提取模式
    const data = flowResult?.data?.data || flowResult?.data || {};
    return {
      boardName: data.demand?.boardName,
      stories: (data.stories || []).map(s => ({ storyNo: s.storyNo, summary: s.summary, status: s.status, systemName: s.systemName })),
      hasStartTechEval: (data.availableActions || []).some(a => a.buttonName === "发起技术评估"),
      hasCreateStory: (data.availableActions || []).some(a => a.buttonName === "新建story")
    };
    ```
    **禁止**返回完整 `availableActions` 数组（9 个完整对象 ~3KB token）；仅提取 `buttonName` 做布尔判断即可。
16. **拆分→评估链式执行（2026-11-09 R2611050089 实测沉淀，省 2 轮往返）**：用户回复 `2`（拆分+评估）时，**单系统场景**在**一个 execute 代码块内链式完成全部 4 步**：
    ```javascript
    // 链式执行模板（单系统，用户已预授权 2）
    // Step 1: create_story prepare → submit
    const prep = await tools.kjptai.create_story({ ...args });
    const mc = prep?.mcpContinuation || prep?.data?.mcpContinuation;
    const sub = await tools.kjptai.create_story({ ...mc.submitArguments, confirmed: true });
    // Step 2: query_requirement_flow 确认 Story 落库
    const flow = await tools.kjptai.query_requirement_flow({ demandId });
    // Step 3: start_technical_evaluation prepare → submit
    const evalPrep = await tools.kjptai.start_technical_evaluation({ demandId });
    const evalMc = evalPrep?.mcpContinuation || evalPrep?.data?.mcpContinuation;
    const evalSub = await tools.kjptai.start_technical_evaluation({ ...evalMc.submitArguments, confirmed: true });
    return { storyStatus: sub?.status, evalStatus: evalSub?.status, stories: flow?.data?.data?.stories?.map(s=>s.storyNo) };
    ```
    **适用条件**：① 单系统 Story（无 re-prepare 串行约束）；② 用户已预授权 `2`；③ `create_story` submit 返回 SUCCESS。**不适用**：多系统 Story（需串行 re-prepare，无法链式）；用户回复 `1`（仅拆分，不发起评估）。
17. **本地 MD Front Matter 一次性替换（2026-11-09 R2611050089 实测教训，防误删）**：更新需求 MD 文档的 Front Matter 时（如 `status` / `story` / `updated` 字段），**用一次 edit 替换整个 `---` 块**，**禁止逐行增删**（逐行 edit 易因 oldString 匹配范围不当导致相邻字段被误删，R2611050089 实测：3 次 edit 才正确更新 front matter，第 2 次 edit 误删了 status/story 行）。**正确模式**：
    ```javascript
    // ✅ 一次性替换整个 front matter 块
    edit({ oldString: "---\nreq_id: R26xxxxxxx\n...全部旧字段...\n---", newString: "---\nreq_id: R26xxxxxxx\n...全部新字段...\n---" })
    // ❌ 禁止：逐行增删（易误删相邻字段）
    edit({ oldString: "status: 旧状态\n---", newString: "status: 新状态\nstory: S26xxx\n---" })
    ```

---

## 🚨 注意事项

- **端点必须为 `kjptai/api/mcp`**（需求平台，X-Platform-Id `kjpt_prod_...`）；指向 `devopsai/api/mcp` 时只有 5 个流水线工具，需求工具不可用；
- 改 `mcp.json` 后需**重启/新建会话**并重新信任 kjptai 连接器；
- **ToolSearch 信任已知工具名（2026-08-28 优化）**：默认直接调用 `mcp__kjptai__*` 工具，仅调用报"未找到"时才用 `ToolSearch` 刷新 schema；
- `query_user` 仅能查当前认证用户，其他人员由 `create_story` 按姓名/工号传参、服务端解析；
- 本技能为**纯 MCP（令牌走工具通道）**：查询/校验/提交全部走 MCP 工具；`create_story` prepare 工具通道直出 `mcpContinuation` 令牌，无需脚本；`kjptai_prepare.py` 仅作 `start_technical_evaluation` 的兜底（当其 prepare 不直出令牌时）；模版/字典数据源来自 MCP 存量回查；工具不可用时提示检查连接器，不尝试其他 HTTP/REST 绕过。
- **级联 systemModuleId 自动收集（2026-09-01 新增）**：prepare 时若传的 `systemModuleId` 不匹配目标系统、服务端返回 `NEEDS_INPUT` 并附带可选列表，须**自动解析该列表**，按「系统模块名称」匹配预期模块取 ID 回填，再重新 prepare；若列表无可匹配项，将可选列表展示给用户确认。典型场景：低延时创新域传 `11000143`（信创域模块）不匹配，服务端返回可选列表中含「两融交易模块=10000427」。
