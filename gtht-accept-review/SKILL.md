---
name: gtht-accept-review
description: 国泰海通科技平台（fintech.gtht.com.cn）需求受理与完成评审一体化技能（纯 MCP 版，状态感知幂等）。 完全通过 kjptai
  科技平台 MCP 协议访问（服务端鉴权，无需本机登录态、无需浏览器、无需网页抓取）。 先查需求详情与流程状态，按状态分派：待受理 → 调用 accept_requirement
  受理（待受理→讨论中）； 已受理（讨论中）→ **跳过受理**，直接调用 review_requirement 完成评审（讨论中→待拆分）； 已评审（待拆分）→
  **跳过受理、跳过评审**，仅调用 add_requirement_review_minutes 新增会议纪要。 全程幂等：已受理不再受理、已评审不再评审，仅补充/更新会议纪要。
  共同受理人场景：当当前用户（吴进-125360）为需求「共同受理人」时，**无论需求状态如何**（待受理/讨论中/待拆分/开发中等），仅调用 add_requirement_review_minutes 新增会议纪要（不执行受理、不执行评审），纪要来源读取用户本地修改后的 md 文件。
  自动解析 `ba-to-dev` 产出的需求分析 Markdown 文档，提取需求编号、评审纪要正文、预计上线日期等要素， 构造评审参数（subdivisionType=普通业务功能、isService
  按业务域判定、title=需求名称_日期、 reviewDeliveryTime 从纪要预计上线日期提取、mettingSummary=纪要正文 HTML）。
  两段式确认协议：调用 prepare 后向用户展示摘要，用户在对话中明确确认后携带令牌完成提交（WorkBuddy
  客户端不渲染确认卡片，令牌不可见，须 HTTP 直连 kjptai MCP 提取）。 支持 `--yes`/`--auto` 预授权：
  命令显式携带时跳过对话确认自动提交（落库参数与两段式完全一致，默认仍两段式确认；`--yes` 同时跳过 Step 5 最终验证查询，信任提交成功响应）。 触发词：受理需求、受理、完成评审、完成需求评审、需求受理、accept-review、gtht-accept-review。
disable: false
---


# 国泰海通需求受理与完成评审技能（纯 MCP 版）

自动从 `ba-to-dev` 产出的需求 Markdown 文档中提取评审纪要等要素，在国泰海通科技平台（fintech.gtht.com.cn）中**按状态幂等推进**：待受理 → 受理（待受理→讨论中）；已受理 → 跳过受理，完成评审（讨论中→待拆分）；已评审 → 跳过受理+评审，**仅新增会议纪要**。全程不重复操作。

> ⚡ **性能与可靠性（2026-08-28 优化）**：
> - **访问方式（MCP 协议 + 令牌直连脚本）**：查询/校验/提交全部走 `kjptai` MCP 工具；但 `accept_requirement` / `review_requirement` 的 **prepare 经工具通道不直出 `confirmationToken`**（与 `gtht-story-split` 中 `start_technical_evaluation` 同现象：工具渲染层只显示 `content[0].text` 摘要，令牌藏在 `structuredContent.data` 不可见），**必须**用 `scripts/kjptai_prepare.py` HTTP 直连提取令牌——这是令牌提取的唯一可靠路径，勿尝试改为工具通道 prepare（否则丢令牌、提交失败）；
> - **状态感知幂等**：执行写操作前必查 `query_requirement_flow` 真实状态——已受理跳过受理、已评审跳过评审、已评审仅补纪要，杜绝重复确认交互；
> - **单 prepare 原则（省 1 次往返/写操作）**：prepare 阶段**只调一次** `scripts/kjptai_prepare.py` HTTP 直连（一步完成 prepare + 摘要打印 + 令牌/会话/requestId 提取并写入 `/tmp/kjptai_confirm_params.json`），用其打印的摘要向用户展示；**禁止**再在对话内用 MCP 工具重复 prepare。提交时读取 `/tmp` 文件携带**全部参数 + 令牌**，避免漏字段；
> - **补纪要默认自动提交（P0-1，2026-09-15）**：`add_requirement_review_minutes`（仅新增纪要、不推进状态、风险极低）场景 prepare 后**默认直接提交**，无需等待用户对话确认（当前最大耗时点=等待确认的交互轮次）；仅当用户显式要求先看摘要再确认时才两段式；
> - **合并查询（P0-2，2026-09-15）**：`query_requirement_flow` 返回已含 `updateTime`（R2609110107 实测确认），Step 3.5a 同步检测直接复用，不再单独调 `query_requirement`（省 1 次 MCP 往返）；
> - **提交响应信任（P1-4，2026-09-15）**：受理/评审/补纪要提交返回 SUCCESS 即信任落库成功，**默认不调 Step 5 验证查询**；仅在响应异常时才回查 `query_requirement_flow`（省 1 次往返）；
> - **`--yes` 预授权模式（省 2 轮用户交互）**：命令显式携带 `--yes`/`--auto`（如 `/gtht-accept-review R26xxxxxxx --yes`）时，跳过对话确认自动提交，落库参数与两段式完全一致；
> - **ToolSearch 缓存**：工具名稳定（`mcp__kjptai__*`），默认直接调用；仅在返回参数校验失败时才 `ToolSearch` 刷新 schema，省 1 次启动查询；
> - **两段式确认（默认）**：所有写操作先 prepare 展示摘要，用户在对话中明确确认后携带令牌提交，禁止擅自落库；
> - **令牌提取（HTTP 直连法，2026-08-21 实测 + 2026-08-28 校正）**：`confirmationToken` 在 MCP 响应 `structuredContent.data` 中，工具渲染层不显示；`accept`/`review` 必须 HTTP 直连 `kjptai_prepare.py` 提取（脚本不落盘令牌、仅写本机会话参数文件供提交复用）；
> - 若 kjptai MCP 工具不可用，提示检查 **kjptai 连接器**信任状态，无脚本回退。

---

## 📌 架构与依赖

- **访问方式（唯一）**：仅通过 `kjptai` MCP 协议。由 Agent 在对话中直接调用 MCP 工具（工具名前缀 `mcp__kjptai__`），**不调用任何 API/脚本**（令牌提取用 `scripts/kjptai_prepare.py` HTTP 直连，属 prepare 一环）。
- **前提条件**：`kjptai` 连接器已信任启用。若工具不可用，需检查：
  1. `~/.workbuddy/mcp.json` 中 `kjptai` 指向 **`https://fintech.gtht.com.cn/kjptai/api/mcp`**（X-Platform-Id: `kjpt_prod_...`）——若指向 `devopsai/api/mcp` 只会有 5 个流水线工具；
  2. 修改后**重启/新建会话**并重新信任 kjptai 连接器；
  3. **ToolSearch 懒加载**：默认信任已知工具名直接调用；仅当返回参数校验失败再 `ToolSearch` 加载 schema 刷新。

### 核心 MCP 工具清单

| MCP 工具 | 用途 | 关键参数 |
|---|---|---|
| `mcp__kjptai__query_requirement` | 需求详情+前置校验（模式 B 取要素用） | `demandId`（R 开头完整编号） |
| `mcp__kjptai__query_requirement_flow` | 流程与可执行操作（受理/评审前必查，状态分派唯一依据） | `demandId` |
| `mcp__kjptai__accept_requirement` | **受理需求（两段式确认）** | `demandId`（提交时携带令牌参数，见单 prepare 章节） |
| `mcp__kjptai__review_requirement` | **完成评审（两段式确认）** | `demandId` + 评审参数（提交时携带令牌参数，见单 prepare 章节） |
| `mcp__kjptai__add_requirement_review_minutes` | **仅新增会议纪要（两段式确认，不推进状态）** | `demandId` + `title`/`reviewType`/`summaryType`/`mettingSummary`（提交时携带令牌参数，见单 prepare 章节） |

### 单 prepare 原则（HTTP 直连令牌提取法，2026-08-21 实测 + 2026-08-28 合并优化）

**实测结论：WorkBuddy 客户端（官方/自定义模型均一样）不会渲染「请确认执行」确认卡片**。`confirmationToken` 位于 MCP 响应的 `structuredContent.data.confirmationToken`，而工具调用结果只渲染 `content[0].text` 摘要，令牌不可见。正确流程（prepare 仅 1 次）：

1. **Prepare（脚本 HTTP 直连，一步）**：运行 `scripts/kjptai_prepare.py --tool <toolName> --args '<argsJson>'`，脚本完成：
   - HTTP 直连 kjptai MCP（initialize → notifications/initialized → tools/call 同一工具同一参数）；
   - 打印确认摘要（`content[0].text`，供向用户展示）；
   - 提取 `confirmationToken` / `expectedUpdateTime`（= updateTime）/ `sessionId`（**优先 structuredContent 的 `_meta.sessionId`，fallback HTTP header 的 Mcp-Session-Id**）/ 新生成 `requestId`（UUID）；
   - 将上述 + **prepare 原参数 args** 写入 `/tmp/kjptai_confirm_params.json`。
2. **向用户展示摘要**（默认两段式需等待用户在对话中明确回复「确认」；`--yes` 模式跳过本步）。
3. **携带令牌提交（对话内 MCP 工具调用）**：读取 `/tmp/kjptai_confirm_params.json`，再次调用同一工具，附加 `confirmationToken` + `expectedUpdateTime` + `requestId` + `confirmed=true` + `_meta.sessionId`（文件中的 sessionId），并**原样携带 `args` 中全部业务字段**落库完成。

> ⚠️ **为何 prepare 必须走 `kjptai_prepare.py` 而非工具通道**：本会话实测（`accept_requirement` 经 `DeferExecuteTool` 工具通道 prepare 在错误态仅返文本错误、不返令牌）+ `gtht-story-split` 对 `start_technical_evaluation` 的实测结论（「同 accept-review 的 review/accept 现象」）均表明——`accept_requirement` / `review_requirement` 的 prepare 经 MCP 工具通道**不直出 `confirmationToken`**（工具渲染层只显示 `content[0].text` 摘要，令牌藏在 `structuredContent.data` 不可见）。因此这两个工具的令牌**只能**靠 `kjptai_prepare.py` HTTP 直连提取；若改为工具通道 prepare 会丢令牌、提交失败。第 1 点「改走工具通道、弃用脚本」对这两个工具**不可行**（平台机制限制，非技能短板），脚本必须保留。
> ⚠️ **禁止重复 prepare**：上一代流程在「工具通道 prepare 展示摘要」后又「HTTP 直连脚本 prepare 取令牌」，等于同一 prepare 调了 2 次（净多 1 次往返）。本版**只用脚本 prepare 一次**，摘要与令牌同源，杜绝冗余。
> ⚠️ **提交必须携带全部业务字段（实测强约束）**：`confirmed=true` 的提交调用必须**原样连同 `/tmp` 文件 `args` 中全部业务字段**（如 `subdivisionType`/`isService`/`title`/`reviewType`/`summaryType`/`mettingSummary`/`reviewDeliveryTime`/`technologySystemRelated`/`technologyReceiver` 等）一并传入。仅传 `demandId` + 令牌字段会被服务端当作「新一次 prepare」重新返回「还需要补充信息」，导致提交失败（该次未写库，复用原 `requestId` 补全字段重试即可）。脚本已自动保存 `args`，提交时直接展开即可避免漏字段。
> ⚠️ 令牌时效（服务端机制）：任何一次成功写库都会使需求 `updateTime` 前移，旧令牌随之失效（报「需求状态或内容已变化」）。受理与评审分属两个独立 prepare + 提交，各自提取各自令牌，互不影响。
> ⚠️ 幂等提示：重复 prepare 会生成多个新令牌，旧令牌不因新 prepare 失效；提交必须使用**最近一次** prepare 的令牌 + 该次响应的 sessionId。
> ⚠️ **requestId 以落盘文件为准（2026-09-16 实测）**：脚本 stdout 打印的 `mcpContinuation` 内嵌 `requestId`（服务端生成）与 `/tmp/kjptai_confirm_params.json` 落盘 `requestId`（脚本自生成 UUID）**可能不一致**。提交时**一律以落盘文件 `requestId` 为准**，忽略 stdout mcpContinuation 内嵌值（R2609160070 受理实测：mcpContinuation=311e668a…，落盘=7168f7f3…，以落盘值提交一次成功）。同一次提交超时重试仍复用落盘文件该值。

**`--yes` 预授权模式（2026-08-28 新增）**：
- 触发：用户命令显式携带 `--yes` 或 `--auto`（如 `/gtht-accept-review R26xxxxxxx --yes` / `受理 R26xxxxxxx --auto`）。
- 行为：Step 3a / Step 4b / Step 6a 的 prepare 执行后**不等待用户对话确认**，直接读取 `/tmp` 文件自动提交（落库参数与两段式完全一致）。
- **受理+评审连跑（`--yes` 核心提速点，2026-09-16 固化）**：需求处于「待受理」时，`--yes` 模式下 Step 3 受理提交成功后**自动继续 Step 4 评审 prepare + 提交**，全程零用户交互（受理与评审各自独立 prepare + 提交，令牌互不干扰，符合令牌时效规则）；一次命令完成 待受理→讨论中→待拆分 两跳。
- 安全边界：默认关闭，仅命令级显式 opt-in 生效；落库结果、状态流转、纪要内容与两段式确认**无任何差异**，功能质量不变。
- 不适用：终态需求（已上线/已终止/草稿）仍按硬闸门停止，不受 `--yes` 影响。

**`--merge` 合并确认模式（2026-09-16 新增，一次确认完成受理+评审）**：
- 触发：用户命令显式携带 `--merge`（如 `/gtht-accept-review R26xxxxxxx --merge`），或用户口语表达「受理并完成评审 / 受理评审一起做」且需求处于「待受理」。
- 行为：**仅需一次用户确认**——Step 3 受理 prepare 展示摘要时，同步向用户说明「确认后将自动继续完成评审」，用户确认后：受理提交 → **自动**评审 prepare → **自动**评审提交（复用用户本次授权，不再二次询问）。
- 与 `--yes` 的区别：`--yes` 零确认（受理+评审全自动）；`--merge` 一次确认（用户看见受理摘要后授权，评审复用授权）。
- 安全边界：评审参数（纪要正文/交付时间）构造规则与两段式完全一致，仅确认次数减少；若评审 prepare 返回 NEEDS_INPUT/缺字段（如纪要要素不完整），**自动回退两段式**，向用户展示评审摘要等待单独确认，不擅自提交残缺参数。
- 不适用：需求已受理（讨论中）时仅评审，正常两段式/`--yes` 即可，无合并必要。

---

## 🚀 使用模式

### 模式 A：解析 ba-to-dev 需求文档（推荐）

用户给出需求编号或 `ba-to-dev` 产出的 Markdown 文档时：

1. **自动定位需求文档（默认取最新 MD）**：优先读取 `/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析/` 目录下对应需求编号的 Markdown 文档；**若存在多份同编号文档（含草稿/备份），默认取 Front Matter `updated` 时间最新（或文件名日期最新）的一份作为纪要来源**，用户无需显式指定路径；仅当最新 MD 缺失或用户明确指定其他版本时才询问。
   - **共同受理人场景（纪要来源=用户本地修改后的 MD）**：当 Step 1 判定当前用户（吴进-125360）为需求「共同受理人」时，纪要来源**优先读取用户本地修改后的 md 文件**——识别顺序：① 用户显式指定的文件路径（最高优先）；② 需求分析目录下同编号 MD 中**用户最近实际编辑**的一份（文件系统 mtime 最新，或 Front Matter 含 `co_receiver` 字段/内容带用户手工修订痕迹——ba-to-dev 生成时平台无共同受理人则不含该字段，用户手工补充 `co_receiver` 即视为维护痕迹）；③ 兜底按规则 18 取最新 MD。**以用户本地内容为准**，不因平台 `updateTime` 更新而改用平台内容构造纪要；若无法定位用户本地修改版，向用户确认文件路径。
2. **提取要素（不调 query_requirement，省 1 次查询）**：
   * **`demandId`**：读取 Front Matter `req_id: R26xxxxxxx` 或标题/链接中的需求编号；
   * **需求名称**：文档标题或 Front Matter 中的需求名称；
   * **评审纪要正文**：截取 **`#### 评审纪要`**（或 `## 评审纪要`）小节下的**全量正文内容**（含沟通时间与人员、1~9 条目、末尾 `预计上线日期：YYYY年MM月上线` 行）；
   * **预计上线日期**：从纪要正文末行 `预计上线日期：YYYY年MM月上线` 提取；**「X月上线」按该月月末日处理**（如 `2026年10月上线` → `2026-10-31`），评审预计交付时间 = 月末日 − 14天（如 `2026-10-17`）；MD 若已写具体日期（如 `2026-10-16`）则直接 − 14 天，勿再推周末；
   * **isService 判定**：需求涉及交易、账户、资金、清算相关业务 → `"1"`；其他 → `"0"`。

### 模式 B：命令行式（需求编号直接指定，无 MD）

用户直接说「受理 R26xxxxxxx 并完成评审」「补纪要 R26xxxxxxx」且未提供 MD 文档时：
1. 调用 `query_requirement(demandId)` 取要素（状态、受理人、名称、优先级、所属系统）；
2. 评审参数从 `query_requirement` 返回推断，或提示用户补充；
3. 始终按 Step 2 状态分派表幂等推进（已受理跳过受理、已评审跳过评审、已评审仅补纪要）。

---

## ⚙️ 执行流程

### Step 1：查流程状态 → 状态分派（模式 A 仅查 flow，省 query_requirement）

- **模式 A（有 ba-to-dev MD）**：**只调用** `mcp__kjptai__query_requirement_flow(demandId)`，要素已从 MD 提取，不调用 `query_requirement`（省 1 次查询）。
- **模式 B（无 MD）**：先 `query_requirement(demandId)` 取要素，再 `query_requirement_flow(demandId)` 分派。

`query_requirement_flow` 返回确认：
- 当前需求状态（`requirement.status` / `requirement.statusName`）；
- 当前用户**可执行**的操作集合（受理需求 / 完成评审 / 新增纪要等）；
- 受理人信息（`receiver` / `coReceiver` 等字段，以实际返回为准）；
- **平台最新 `updateTime`**（`requirement.updateTime` 或顶层 `structuredContent.data.updateTime`，2026-09-15 实测确认存在）——供 Step 3.5a 同步检测复用，**避免再调 `query_requirement`**（P0-2 合并查询优化）。

**共同受理人判定（优先级最高，先于状态分派）**：
- 若当前用户（**吴进-125360**）为需求的「**共同受理人**」（`coReceiver` 字段含吴进），则**无论需求状态如何**（待受理/讨论中/待拆分/开发中等），**跳过受理、跳过评审**，直接进入 **Step 6 仅新增会议纪要**（`add_requirement_review_minutes`，不推进状态）；
- 纪要来源：**读取用户本地修改后的 md 文件**（优先用户显式指定文件，否则取需求分析目录下同编号 MD 中用户最近编辑的一份，识别规则见模式 A）；
- 若当前用户为需求「受理人」（`receiver`=吴进）或非受理人，则按下方状态分派表正常推进。

**按 `statusName` 分派（幂等核心，禁重复操作）**：

| 当前状态 | 受理 | 完成评审 | 会议纪要 | 后续动作 |
|---|---|---|---|---|
| `待受理` | ✅ 执行 | — | — | Step 3 受理 → Step 4 评审 → Step 5 验证 |
| `讨论中`（已受理未评审） | ⏭️ **跳过**（已受理） | ✅ 执行 | — | 直接 Step 4 评审 → Step 5 验证 |
| `待拆分`（已受理+已评审） | ⏭️ **跳过**（已受理） | ⏭️ **跳过**（已评审） | ✅ 执行 | 直接 Step 6 **仅新增会议纪要** |
| 已上线 / 已终止 / 草稿等终态 | ⛔ | ⛔ | ⚠️ 视可执行操作 | 向用户说明原因并停止（纪要如需补充另议） |

> ⛔ **硬闸门失败即停**：任一前置不满足（终态/无权限），向用户说明原因并停止。
> ⚡ **幂等铁律**：已受理（讨论中/待拆分）**严禁重复调用 `accept_requirement`**；已评审（待拆分）**严禁重复调用 `review_requirement`**——重复操作会触发服务端状态校验失败（「需求状态或内容已变化」），浪费一次确认交互。

### Step 3：受理需求（单 prepare + 两段式/`--yes`/`--merge`）

**前置条件（幂等跳过）**：仅当状态为「待受理」且当前用户可执行受理操作时才执行本步。若已处于「讨论中」/「待拆分」（已受理），**直接跳过本步**，不调用 `accept_requirement`。

#### 3a. Prepare（脚本一步取摘要+令牌）

运行（Bash，内网 HTTP 直连按需设 `BypassSandbox: true`）：

```bash
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python \
  /Users/wujin/.workbuddy/skills/gtht-accept-review/scripts/kjptai_prepare.py \
  --tool accept_requirement --args '{"demandId":"R26xxxxxxx"}'
```

脚本打印确认摘要（含需求编号、状态流转 待受理→讨论中、受理人）并写入 `/tmp/kjptai_confirm_params.json`。向用户展示摘要：
- **默认两段式**：等待对话中明确回复「确认」后进入 3b；
- **`--yes` 模式**：跳过等待，直接进 3b；
- **`--merge` 模式**：展示摘要时**同步说明「确认后将自动继续完成评审」**，等待用户一次确认后进入 3b，受理提交后**自动进入 Step 4 合并提交流程**（不再等待二次确认）。

#### 3b. 携带令牌提交（落库）

读取 `/tmp/kjptai_confirm_params.json`，调用 `mcp__kjptai__accept_requirement`，附加 `confirmationToken` + `expectedUpdateTime` + `requestId` + `confirmed=true` + `_meta.sessionId`（文件 sessionId），`args` 原样展开。受理成功（待受理→讨论中）。

> ⛔ 若用户拒绝确认（两段式/`--merge` 均适用），则本次受理不落库，可重新 prepare。

#### 3c. 受理成功 → 自动进入 Step 4（隐式验证 + 合并/连跑）

**不单独查询** `query_requirement_flow`。直接进入 Step 4 review prepare：
- **`--merge` 模式**：受理提交成功后**自动执行 Step 4b prepare**（用受理成功后的新状态 prepare 评审），prepare 返回后**自动执行 Step 4c 提交**（复用用户之前的一次授权），全程无需用户再次确认。**若评审 prepare 返回 NEEDS_INPUT/缺字段，自动回退两段式**，向用户展示评审摘要等待单独确认（不擅自提交残缺参数）。
- **`--yes` 模式**：受理提交成功后自动进入 Step 4b prepare → 自动 Step 4c 提交（零确认连跑）。
- **默认两段式**：受理提交后，展示受理成功结果，按正常流程进入 Step 4 等待用户指令。
- 若 review prepare 返回状态异常（仍待受理），回退查询核查。最终状态以 Step 5 条件验证为准。

### Step 3.5：评审前信息一致性双检（P1+P2 优化，2026-09-09）

> **背景**：R2609080068 实测评审纪要返工 3 次（改造范围/各系统改造功能/测试范围均被业务方纠正），根因是评审参数构造前未做「本地 MD 与平台信息一致性」及「纪要要素完整性」双检。本步在评审 prepare 前强制执行，杜绝返工。

#### 3.5a. 本地 MD 与平台信息同步检测（P2，合并查询优化 2026-09-15）

**目的**：避免本地 ba-to-dev MD 与平台最新需求内容漂移（本次 `--force` 时才发现平台已更新 V.7，本地还是旧版）。

- **优先复用 Step 1 的 `query_requirement_flow` 返回（省 1 次 MCP 往返）**：已实测确认 flow 返回含 `requirement.updateTime` 与顶层 `structuredContent.data.updateTime`（R2609110107 探测，2026-09-15），直接取该值作为平台最新 `updateTime`，**不再单独调用 `query_requirement`**；
- **仅当 flow 返回无 `updateTime` 字段时**（异常/缺字段），才回退调用 `mcp__kjptai__query_requirement(demandId)` 读取平台 `updateTime`；
- 对比本地 MD Front Matter 的 `updated` 字段（或文档头部的更新时间）与平台 `updateTime`；
- **若平台 `updateTime` 晚于本地 `updated`** → 提示用户本地文档已过期，建议先运行 `/ba-to-dev R26xxxxxxx --force` 刷新后再评审，**不要**基于过期文档构造评审参数；
- 若一致或本地更新 → 继续。

> ⚠️ **强制**：评审纪要正文（mettingSummary）必须与**平台最新版**需求内容一致。若检测到平台有更新而用户选择不刷新，须在纪要中标注「按本地 MD 版本，待与平台最新版核对」。

#### 3.5b. 评审纪要要素完整性 + 业务确认清单（P1）

**目的**：确保评审纪要的「改造范围」「各系统改造功能」「测试范围」与需求内容、业务方意图一致，避免返工。

**① 改造范围完整性检查**：`各系统改造功能` 中列出的系统，与需求内容（`二、需求内容`）提及的系统**一一对应**，无遗漏、无多余。尤其跨系统需求需逐一核对。

**② 各系统改造功能与需求内容一致性**：每条改造功能须能回溯到需求内容中的具体条款，且描述准确（如本次「回自有资金/回融券卖出资金」的分配逻辑，不能简写成「取消开关」）。

**③ 测试范围边界确认**：明确各系统**需要测试**与**无需测试**的场景（如本次集中清算系统仅测「固定回自有」场景）。若需求未明确测试边界，须在纪要「业务关注点」或与业务方确认后补充。

**④ 业务确认清单（提交前向用户展示，逐项确认）**：

```
□ 改造范围是否完整（含所有涉及系统，无遗漏/多余）？
□ 各系统改造功能是否与需求内容一一对应、描述准确？
□ 测试范围边界是否明确（哪些系统测哪些场景）？
□ 跨系统联动关系（参数/逻辑）是否已说明？
□ 灰度上线、联测涉及系统是否已按平台最新状态填写？
```

> **执行要求**：提交评审 prepare 前，向用户展示上述确认清单；任一事项存在疑义或与业务方意图不符，**先与业务方确认再提交**，避免评审落库后返工。

### Step 4：完成需求评审（单 prepare + 两段式/`--yes`/`--merge`）

**前置条件（幂等跳过）**：仅当状态为「讨论中」且当前用户可执行完成评审操作时才执行本步。若已处于「待拆分」（已评审），**直接跳过本步**，不调用 `review_requirement`，改走 Step 6 仅新增会议纪要。

> 🔗 **`--merge` 合并流程入口**：若由 Step 3c `--merge` 自动进入，本步跳过「等待用户指令」，直接执行 4a→4b→4c 连跑；若 4b prepare 返回 NEEDS_INPUT/缺字段，回退两段式等待用户单独确认。

#### 4a. 构造评审参数

从 ba-to-dev MD 文档提取并构造 `review_requirement` 参数：

| 参数 | 取值规则 | 示例 |
|---|---|---|
| `demandId` | 需求编号（必填） | `R2608110032` |
| `subdivisionType` | 一级需求类型，默认 `普通业务功能`（缺陷修复类填 `缺陷`） | `普通业务功能` |
| `isService` | 是否营运需求：需求涉及**交易、账户、资金、清算** → `"1"`；其他 → `"0"` | `"1"` |
| `title` | 评审会议主题：`{需求名称}_{YYYYMMDD}`（今日日期） | `融资负债减免功能优化_20260821` |
| `reviewDeliveryTime` | 评审预计交付时间 `YYYY-MM-DD`：MD `预计上线日期` 按**月末日**处理（如 `2026年10月上线` → `2026-10-31`）再 **− 14 天** | `2026-10-17` |
| `mettingSummary` | 评审纪要正文（富文本 HTML）：截取 MD 中 `#### 评审纪要` 小节全量正文，Markdown → HTML 转换（`**加粗**` → `<strong>`） | `<p>2026年08月11日经与...</p>...` |
| `summaryType` | 纪要类型：`"2"` = 富文本（默认） | `"2"` |
| `reviewType` | 评审结果：默认 `评审通过`（不传时服务端默认选择评审通过，禁止猜测内部编码） | `评审通过` |
| `technologySystemRelated` | 是否交易技术系统相关：`"1"`/`"0"`（可选，按需求涉及系统判定） | `"1"` |
| `technologyReceiver` | 交易技术系统受理人（可选，按需求要素填写） | — |

> 💡 **prepare 返回的规范化编码值可直接用于提交（2026-09-16 实测）**：prepare 响应 `mcpContinuation.submitArguments.values` 中，服务端会把中文枚举值规范化为内部编码——`reviewType`「评审通过」→ `f54fbe2e327e4ee68d`、`subdivisionType`「普通业务功能」→ `15610859709344UP19`，并自动补 `importantDemand` 等默认字段。**提交时直接复用这些规范化值**（无需还原中文），R2609160070 评审实测一次成功。若 prepare 未返回某字段（如 `technologyReceiver` 未填），提交时也无需补。

**reviewDeliveryTime 计算规则**：
1. 从 MD 纪要末行提取 `预计上线日期：YYYY年MM月上线`（如 `2026年10月上线`）；
2. **「X月上线」按该月月末日处理**（如 `2026年10月上线` → 发布日 `2026-10-31`）；
3. 评审预计交付时间 = 月末日 **− 14 天**（如 `2026-10-31` − 14天 = `2026-10-17`）；
4. 若 MD 已写具体日期（如 `2026-10-16`），直接 − 14 天，勿再推周末。

**mettingSummary HTML 转换规则**：
- 截取 `#### 评审纪要` 到 `---` 分隔线或下一章节标题之间的全量正文；
- **每条「标题：」与「内容」必须分行显示**：标题行独立一个 `<p>`，内容另起一个 `<p>`（如 `<p>1. <strong>需求补充说明</strong>：</p><p>无</p>`）；严禁把 `标题：内容` 塞进同一个 `<p>`，否则平台渲染会把标题和内容挤在同一行；
- 子条目（`①`/`②`/`(1)`）各占一个 `<p>`，保留缩进（`&nbsp;`）；
- `**加粗**` → `<strong>`；末行 `预计上线日期：YYYY年MM月上线` 是纪要正文的一部分，**严禁遗漏**。

**mettingSummary 完整 HTML 模板**（严格按此结构拼装，末尾必须含 `预计上线日期` 行）：

```html
<p>YYYY年MM月DD日经与<strong>部门A</strong>人员A和<strong>部门B</strong>人员B沟通评审通过</p>
<p>1. <strong>需求补充说明</strong>：</p>
<p>无</p>
<p>2. <strong>改造范围</strong>：</p>
<p>系统A，系统B</p>
<p>3. <strong>各系统改造功能</strong>：</p>
<p>&nbsp;&nbsp;(1) 系统A：</p>
<p>&nbsp;&nbsp;&nbsp;&nbsp;① 功能点一。</p>
<p>&nbsp;&nbsp;&nbsp;&nbsp;② 功能点二。</p>
<p>4. <strong>前端界面</strong>：</p>
<p>无</p>
<p>5. <strong>接口交互</strong>：</p>
<p>无</p>
<p>6. <strong>业务参数</strong>：</p>
<p>无</p>
<p>7. <strong>灰度上线关注</strong>：</p>
<p>否</p>
<p>具体以后续实际开发评估为准。</p>
<p>8. <strong>联测涉及系统</strong>：</p>
<p>系统C</p>
<p>9. <strong>业务关注点</strong>：</p>
<p>&nbsp;&nbsp;(1) 关注点一。</p>
<p>预计上线日期：计划 YYYY年MM月</p>
```

> ✅ **自检清单**：构造完 mettingSummary 后检查——① 首行含沟通时间与人员；② 含 1~9 全部条目；③ **末尾含 `预计上线日期：...` 行**（与 MD 纪要末行一致）；④ 标题/内容分行。任一项缺失即补全后再进入 4b prepare。

#### 4b. Prepare（脚本一步取摘要+令牌）

将 Step 4a 全参数构造为 JSON，运行：

```bash
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python \
  /Users/wujin/.workbuddy/skills/gtht-accept-review/scripts/kjptai_prepare.py \
  --tool review_requirement --args '{"demandId":"R26xxxxxxx","subdivisionType":"普通业务功能","isService":"1","title":"需求名称_20260821","reviewDeliveryTime":"2026-09-04","mettingSummary":"<p>...</p>","summaryType":"2","reviewType":"评审通过"}'
```

脚本打印评审摘要（含评审结果、一级需求类型、是否营运需求、预计交付时间、纪要正文预览）并写入令牌文件。向用户展示：
- **默认两段式**：等待对话明确确认后进入 4c；
- **`--yes` 模式**：跳过等待，直接进 4c；
- **`--merge` 模式（由 Step 3c 自动进入）**：**不等待用户确认**，直接进 4c（复用受理时的一次授权）；若 prepare 返回 NEEDS_INPUT/缺字段，回退两段式等待用户单独确认。

> ⚠️ **参数完整性校验**：服务端会一次性返回所有缺失字段和条件必填项。若 prepare 返回缺失字段提示，补充后重新 prepare（脚本重写 `/tmp` 文件）。

#### 4c. 携带令牌提交（落库）

读取 `/tmp/kjptai_confirm_params.json`，调用 `mcp__kjptai__review_requirement`，附加令牌字段 + `confirmed=true` + `_meta.sessionId`，**`args` 全字段原样展开**（含 `subdivisionType`/`isService`/`title`/`reviewType`/`summaryType`/`mettingSummary`/`reviewDeliveryTime`/`technologySystemRelated`/`technologyReceiver`）。评审通过（讨论中→待拆分）。

> ⛔ 若用户拒绝确认（两段式），则本次评审不落库，可重新 prepare。

### Step 5：验证评审完成（条件验证，P1-4 优化 2026-09-15）

- **提交响应即信任（默认，省 1 次往返）**：受理/评审 submit 返回 **SUCCESS/「请求成功」/「评审已完成」** 即视为落库成功，**默认不调用** `query_requirement_flow` 验证（服务端提交成功必有状态流转，多次实测无失败先例）；落库结果以平台为准，后续如需复核可手动查询。
- **仅异常时验证（条件触发）**：仅在提交响应**异常/非 SUCCESS**（如报「需求状态或内容已变化」、超时、网络错误）时，才调用 `query_requirement_flow` 核查真实状态并决定是否重试（重试复用原 requestId）。
- **`--yes` 模式**：与默认一致（信任提交成功响应），行为无差异。

> ⏭️ 若 Step 2 分派时即已处于「待拆分」（跳过了 Step 3/4），本步验证可省略，直接进入 Step 6。

### Step 6：仅新增会议纪要（已受理+已评审的兜底动作）

**适用场景**：
1. 需求已完成评审（状态=待拆分），本次**不再受理、不再评审**，仅需补充/更新评审会议纪要；
2. 用户明确指定「仅新增会议纪要」；
3. **当前用户为需求「共同受理人」**（Step 1 判定，**无论需求状态如何**，仅补纪要、不推进状态）。

> ⚡ **补纪要默认自动提交（P0-1，2026-09-15）**：本步所有场景（含共同受理人）均走 `add_requirement_review_minutes`，该操作**不推进状态、风险极低**，prepare 展示摘要后**默认直接提交**（等价 `--yes`），**无需等待用户对话确认**（当前最大耗时点=等待确认的交互轮次）；仅用户显式要求「先看摘要再确认」时才两段式。

调用 `mcp__kjptai__add_requirement_review_minutes`（单 prepare + 默认自动提交，**不推进需求状态**）：

| 参数 | 取值规则 | 示例 |
|---|---|---|
| `demandId` | 需求编号（必填） | `R2608130111` |
| `title` | 会议主题；不传默认「需求标题+评审会+当前日期」 | `东方资管融资融券个性化账单需求_20260821` |
| `reviewType` | 评审结果中文名称（按平台字典，禁止猜测编码） | `评审通过` |
| `summaryType` | 纪要类型：`"2"`=富文本（默认） | `"2"` |
| `mettingSummary` | 评审纪要正文（富文本 HTML，Markdown → HTML 转换，规则同 Step 4a） | `<p>...</p>` |

#### 6a. Prepare（脚本一步取摘要+令牌）

运行 `kjptai_prepare.py --tool add_requirement_review_minutes --args '<参数 JSON>'`，打印摘要并写令牌文件。

> ⚡ **默认自动提交（P0-1）**：prepare 提取令牌后**直接进入 6b 提交**，不等待用户对话确认（补纪要不推进状态、风险极低）；仅当用户显式要求「先给我看摘要再确认」时才暂停等待确认。提交后向用户展示摘要与纪要 ID 即可。

> ⚠️ **与 `review_requirement` 的区别**：`review_requirement` =「完成评审」按钮（讨论中→待拆分，含评审表单）；`add_requirement_review_minutes` = 单独新增一条会议纪要（**状态不变**，适用于已评审完成后的纪要补充/更新）。两者纪要正文（mettingSummary）构造规则一致。

#### 6b. 携带令牌提交（落库）

读取 `/tmp/kjptai_confirm_params.json`，调用 `add_requirement_review_minutes` 携带令牌 + `args` 全字段落库，新增会议纪要成功。

#### 6c. 验证（条件触发，P1-4）

提交返回 SUCCESS 即信任落库成功，**默认不验证**；仅当提交响应异常/非 SUCCESS 时才调用 `query_requirement` 或 `query_requirement_flow` 确认纪要是否新增（需求状态保持待拆分不变）。

---

## 📐 业务规则（强制）

1. **先受理后评审**：必须先受理需求（待受理→讨论中），受理成功后才能完成评审（讨论中→待拆分）；不可跳过受理直接评审；
2. **两段式确认（默认）/ `--yes` 预授权 / 补纪要默认自动提交**：受理（`accept_requirement`）、评审（`review_requirement`）写操作先 prepare 展示摘要，默认需用户在对话中明确确认后携带令牌提交；命令显式 `--yes`/`--auto` 时跳过确认自动提交（落库参数完全一致）；**补纪要（`add_requirement_review_minutes`）默认自动提交**（仅新增纪要、不推进状态、风险极低，prepare 后直接提交，无需等待确认）；
3. **单 prepare 原则**：prepare 只调 `kjptai_prepare.py` HTTP 直连一次（摘要+令牌同源），禁止再在对话内用 MCP 工具重复 prepare；
4. **提交必须携带全部业务字段**：`confirmed=true` 提交须原样展开 `/tmp` 文件 `args` 中全部业务字段 + 令牌字段，仅传 `demandId`+令牌会被当新 prepare 拒绝；
5. **令牌时效（服务端机制）**：任何一次成功写库都会使需求 `updateTime` 前移，旧令牌失效。受理与评审各自独立 prepare + 提交；提交必须使用**最近一次** prepare 的令牌及该次响应的 sessionId；
6. **requestId 唯一性**：提交时用 UUID 生成唯一幂等键；同一次提交超时重试必须复用原 requestId，不能重新生成；
7. **subdivisionType 默认值**：`普通业务功能`；缺陷修复类需求填 `缺陷`；
8. **isService 判定**：需求涉及交易、账户、资金、清算相关业务 → `"1"`；其他 → `"0"`。用户未明确指定时，按需求涉及系统判定（集中交易/低延时/清算 → `"1"`）；
9. **title 格式**：`{需求名称}_{YYYYMMDD}`，日期取今日（评审日期）；
10. **reviewDeliveryTime**：从 MD 评审纪要 `预计上线日期` 提取，按**月末日**处理再 − 14 天（如 `2026年10月上线` → `2026-10-31` − 14 = `2026-10-17`）；
11. **mettingSummary**：MD 评审纪要正文全量（含预计上线日期行），Markdown → HTML 转换；
12. **幂等分派（核心铁律）**：每次执行前必须 `query_requirement_flow` 读取真实状态，按状态分派——**已受理（讨论中/待拆分）跳过受理**、**已评审（待拆分）跳过评审**、**已评审仅新增会议纪要**（add_requirement_review_minutes）。严禁对已受理需求重复 `accept_requirement`、对已评审需求重复 `review_requirement`；
13. **单次单需求**：一次只处理一个需求；
14. **ToolSearch 懒加载**：默认信任已知 `mcp__kjptai__*` 工具名直接调用；仅当返回参数校验失败再 `ToolSearch` 刷新 schema；
15. **本地同步收敛**：受理/评审落库并提交成功后（默认模式含 Step 5 验证，`--yes` 模式跳过 Step 5 但落库已成功），**单次**更新本地 MD 文档 `status`/`平台状态` 字段 + 写 memory（避免多次 Edit）；
16. **令牌提取方式（实测结论，2026-08-28 校正）**：`accept_requirement` / `review_requirement` 的 prepare 经 MCP 工具通道**不直出 `confirmationToken`**（工具渲染层只显示文本摘要，令牌藏在 `structuredContent.data` 不可见；与 `start_technical_evaluation` 同现象）。提交前**必须**按「单 prepare 原则」章节用 `kjptai_prepare.py` HTTP 直连提取令牌，不得改为工具通道 prepare（否则丢令牌、提交失败）；令牌不落盘、仅本机会话参数文件供提交复用。
17. **执行后优化点输出（每次执行必做，对齐 ba-to-dev 规则 16）**：每次实际执行 `/gtht-accept-review` 完成受理/评审/补纪要后，在最终回复中**必须新增「🔧 本技能优化点」小节**，主动输出本次执行暴露的优化点，持续驱动技能迭代。输出采用四段式模板：
    - **① 执行摘要**：本次执行总耗时、执行的写操作（受理/评审/补纪要）与状态流转（如 讨论中→待拆分）；
    - **② 优化点清单**：以表格 `# | 类别 | 优化点 | 影响 | 优先级 | 状态` 输出，类别覆盖——**性能**（prepare/令牌提取/MCP 往返/状态查询耗时，如单 prepare 省往返、`--yes` 省确认与验证、ToolSearch 缓存）、**准确性**（纪要要素完整性、令牌时效、字段编码转换、requestId 复用、Step 3.5 双检）、**流程**（幂等分派、本地同步收敛、单次单需求）；**仅输出「待落地」优化点**（已落地的不再重复提示）；
    - **③ 优先级定义**：`P0`=本次即可落地、收益显著；`P1`=需工程化改造；`P2`=体验/流程优化；
    - **④ 状态标注**：`已落地`=本次已采用；`待落地`=已提出待实施。**「已落地」的优化点不进入清单展示**（已生效，无需再提示），仅保留「待落地」项；
    - 优化点须**基于本次实际执行情况**输出，避免空泛套话；若本次执行已足够高效，如实标注「本次执行高效，无显著优化点」。
18. **默认取最新 MD 填写会议纪要（2026-09-15 实测沉淀）**：用户要求「完成评审/填写会议纪要/补纪要」且**未显式指定文件**时，**默认**读取需求分析目录（`/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析/`）下对应需求编号**最新**的 ba-to-dev MD 文档（多份同编号文档按 Front Matter `updated` 或文件名日期取最新），以该文档 `#### 评审纪要` 小节**全量正文**作为 `mettingSummary` 来源，**无需再向用户确认文件路径或内容来源**；仅当最新 MD 缺失、用户明确指定其他版本、或 Step 3.5a 检测到平台内容严重漂移且用户选择刷新时才变更来源。R2609110107 实测：需求已处于「开发中」无法 `review_requirement`，改用 `add_requirement_review_minutes` 仅补纪要，纪要内容默认取最新 MD（含集中交易系统公募银保节点 XA 配置改造项），一次落库成功。
19. **共同受理人仅补纪要（2026-09-15 沉淀）**：执行前从 `query_requirement_flow`（或 `query_requirement`）返回中读取受理人信息（`receiver`/`coReceiver` 等字段，以实际返回为准）；若**当前用户（吴进-125360）为需求「共同受理人」**（`coReceiver` 含吴进），则**无论需求状态如何**（待受理/讨论中/待拆分/开发中等），**跳过受理（`accept_requirement`）与评审（`review_requirement`）**，直接调用 `add_requirement_review_minutes` **仅新增会议纪要**（不推进状态）；纪要来源**读取用户本地修改后的 md 文件**（优先用户显式指定文件，否则取需求分析目录下同编号 MD 中用户最近编辑的一份，识别规则见模式 A），**不按平台内容构造**。R2609110107 实测：需求 receiver=盛浅雨-126468、用户为共同受理人且需求已「开发中」，仅补纪要成功（纪要 ID 2019054）。MD Front Matter 的 `co_receiver` 字段（ba-to-dev 规则 13 有则必填，2026-09-15 起强制落盘）可辅助预判与定位「用户本地修改版」，但**判定一律以平台实时 `coReceiver` 为准**（本地可能过期）。

---

## 💬 对话交互示例

| 用户口令 | 技能处理动作 |
|---|---|
| 「**受理 R2608110032 并完成评审**」 | 查 flow → 按状态分派：待受理→受理；讨论中→跳过受理；待拆分→跳过受理+评审仅加纪要 → 各步单 prepare + 两段式确认 → Step 5 验证 |
| 「**受理 R2608110032 并完成评审 --yes**」 | 同上，但 prepare 后自动提交，跳过 2 轮对话确认（落库参数一致） |
| 「**受理 R2608110032 并完成评审 --merge**」 | 待受理时**仅 1 次确认**：受理 prepare 展示摘要（含「确认后自动完成评审」说明）→ 用户确认 → 受理提交 → 自动评审 prepare+提交，全程一次授权 |
| 「**受理需求**」 | 查最新 ba-to-dev MD → 提取需求编号 → 查 flow → **已受理则跳过受理**，按状态继续评审或仅加纪要 |
| 「**完成评审**」 | 默认取最新 ba-to-dev MD（需求分析目录下同编号最新文档）→ 提取编号/纪要/上线日期 → 查 flow → **已评审则跳过评审**，仅新增会议纪要 |
| 「**R2608110032 受理评审**」 | 从需求编号进入全流程（幂等分派） |
| 「**仅新增会议纪要 / 补个纪要**」 | 查 flow → 确认已评审（待拆分）→ 直接 `add_requirement_review_minutes`（prepare 后**默认自动提交**，状态不变） |
| 「**补纪要 R26xxxxxxx**」（共同受理人是我的） | 查 flow → **共同受理人判定**：当前用户为共同受理人 → **跳过受理+评审**，直接 `add_requirement_review_minutes`（读取**用户本地修改后的 MD** 作为纪要来源，prepare 后**默认自动提交**），状态不变 |

---

## 🚨 注意事项

- **端点必须为 `kjptai/api/mcp`**（需求平台，X-Platform-Id `kjpt_prod_...`）；指向 `devopsai/api/mcp` 时只有 5 个流水线工具，需求工具不可用；
- 改 `mcp.json` 后需**重启/新建会话**并重新信任 kjptai 连接器；
- **ToolSearch 懒加载**：默认信任已知工具名；参数校验失败再刷新；
- **幂等分派是硬约束**：执行任何写操作前必须先 `query_requirement_flow` 读取真实状态；已受理（讨论中/待拆分）不得再 `accept_requirement`，已评审（待拆分）不得再 `review_requirement`，仅用 `add_requirement_review_minutes` 补纪要；
- 本技能为**纯 MCP**，不依赖任何脚本/API/浏览器兜底（令牌提取用 `kjptai_prepare.py` HTTP 直连属 prepare 一环）；kjptai MCP 工具不可用时提示检查连接器，不尝试用网页绕过；
- **三个写操作的分工**：`accept_requirement`=受理（待受理→讨论中）；`review_requirement`=完成评审（讨论中→待拆分，含评审表单与纪要）；`add_requirement_review_minutes`=仅新增会议纪要（状态不变，供已评审需求补纪要）；
- **与 `gtht-review-submit` 的区别**：`gtht-review-submit` 通过 REST API `saveDemandReviewInfo` 新增评审纪要（不改变需求状态）；本技能优先用 MCP `review_requirement` 完成「完成评审」按钮操作（讨论中→待拆分，同时含评审表单数据），已评审完成的场景用 MCP `add_requirement_review_minutes` 补纪要，无需再依赖 REST 通道。
- **共同受理人场景**：当需求「共同受理人」包含当前用户（吴进-125360）时，技能**只做「新增会议纪要」一件事**——不执行受理、不执行评审，无论需求处于何种状态（待受理/讨论中/待拆分/开发中等）；纪要内容以**用户本地修改后的 md 文件**为准（优先用户显式指定，否则取用户最近编辑的一份）。
