---
name: gtht-req-query
description: 'GTHT 金融科技平台需求查询技能。通过 kjptai 科技平台 MCP 协议访问（服务端鉴权）。

  kjptai MCP（https://fintech.gtht.com.cn/kjptai/api/mcp）提供 9 个需求管理工具：

  query_requirement / query_story / query_task / create_requirement / submit_requirement_create
  /

  accept_requirement / create_story / create_task / split_story_to_tasks。

  另有 kjptai-devops（/devopsai/api/mcp）提供 5 个 DevOps 流水线工具。

  触发词：需求查询、查需求、Rxxxx、需求编号、需求管理、gtht-req-query。

  '
disable: false
---


# GTHT 需求查询（kjptai MCP）

## MCP 服务器配置

> [!IMPORTANT]
> **两个独立 MCP 服务器**，分别承担需求管理和 DevOps 流水线职责。

| 配置项 | kjptai（需求管理） | kjptai-devops（流水线） |
| :--- | :--- | :--- |
| **URL** | `https://fintech.gtht.com.cn/kjptai/api/mcp` | `https://fintech.gtht.com.cn/devopsai/api/mcp` |
| **Platform ID** | `kjpt_prod_3059935247a2` | `kjpt_devops_prod_8c10cc4e96cf` |
| **传输协议** | `streamable_http`（HTTP SSE） | `streamable_http`（HTTP SSE） |
| **鉴权方式** | 服务端 Bearer Token（JWT），无需本机登录态 | 同左 |
| **配置文件** | `~/.workbuddy/mcp.json` | 同左 |
| **工具数量** | 9 个需求管理工具 | 5 个 DevOps 流水线工具 |

> ⚠️ **配置陷阱**：`transport` 字段必须使用下划线格式 `streamable_http`，不能用连字符 `streamable-http`。
> 上次因 `kjptai` 使用 `type: "streamable-http"`（连字符+错误字段名 `type`），导致服务器未正确加载，
> 误判需求查询工具不存在。两个服务器必须统一使用 `"transport": "streamable_http"`。

---

## kjptai 工具清单（9 个需求管理工具）

### 查询类工具（3 个）

| # | 工具全名 | 用途 | 核心参数 |
| :-: | :--- | :--- | :--- |
| 1 | `mcp__kjptai__query_requirement` | 查询需求列表或按编号查单条详情 | `demandId?`, `mineScope?`, `searchKey?`, `priority?`, `demandStatusCategory?`, `departmentNames?`, `receiverNames?`, `primaryDomainNames?`, `secondaryDomainNames?`, `storySystemNames?`, `startTime?`, `endTime?`, `esDuedateStartTime?`, `esDuedateEndTime?`, `isImportantDemand?`, `isexceed?`, `keyFocus?`, `currentPage?`, `pageSize?`, ... |
| 2 | `mcp__kjptai__query_story` | 查询 Story 列表，支持按需求编号过滤 | `demandId?`, `storyNo?`, `searchKey?`, `storyStatusCategory?`, `storyLevel?`, `mineScope?`, `systemNames?`, `projectNames?`, `devManagePersonNames?`, `testManagePersonNames?`, `planLineV?`, `planLineStart?`, `planLineEnd?`, ... |
| 3 | `mcp__kjptai__query_task` | 查询 Task 列表，支持开发/SIT/UAT 三种类型 | `taskType?` (2/3/4), `mineScope?`, `noOrTitle?`, `taskNo?`, `storyNo?`, `systemNames?`, `systemVersionIds?`, `devHeaderNames?`, `devAppointNames?`, `planProdLineDateBegin?`, `planProdLineDateOver?`, `creatorNames?`, `targetUserNames?`, ... |

### 创建/操作类工具（6 个）

| # | 工具全名 | 用途 | 核心参数 |
| :-: | :--- | :--- | :--- |
| 4 | `mcp__kjptai__create_requirement` | 准备/补充需求草稿（不直接创建） | `draftId?`, `draftVersion?`, `summary?`, `priority?`, `groupId?`, `secondaryGroupId?`, `receiver?`, `receiverTeam?`, `wishDate?`, `description?`, `businessDirector?`, `listReceivers?`, `listEpics?`, `listCompanyProjects?`, ... |
| 5 | `mcp__kjptai__submit_requirement_create` | 提交需求创建（需用户确认） | `draftId`*, `draftVersion`*, `confirmed`* (const true), `requestId`* |
| 6 | `mcp__kjptai__accept_requirement` | 受理待受理需求（两步确认） | `demandId`*, `expectedUpdateTime?`, `confirmationToken?`, `requestId?`, `confirmed?` |
| 7 | `mcp__kjptai__create_story` | 在已评审需求下创建 Story（两步确认） | `demandId`*, `summary?`, `tId?`, `projectId?`, `systemId?`, `systemModuleId?`, `devManagePersonId?`, `testManagePersonId?`, `uatUserId?`, `priority?`, ... |
| 8 | `mcp__kjptai__create_task` | 创建单个 Task（开发/SIT/UAT） | `storyNo?`, `taskTitle?`, `taskType?`, `devHeader?`, `devAppoint?`, `devAssessDateStart?`, `devAssessDateEnd?`, `devPlanWorkload?`, ... |
| 9 | `mcp__kjptai__split_story_to_tasks` | 将 Story 拆分成多个 Task 草稿 | `storyNo`* |

> `*` = 必填参数，`?` = 可选参数

### 通用 `_meta` 参数（所有工具共享）

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `sessionId` | string | 会话 ID；不传则服务端自动生成 |
| `rawInput` | string | 原始自然语言请求；未显式传业务参数时可用于补充提取 |
| `agentKey` | string | 可选的上游 Agent 标识，仅用于链路透传 |

---

## kjptai-devops 工具清单（5 个流水线工具）

| # | 工具全名 | 用途 | 核心参数 |
| :-: | :--- | :--- | :--- |
| 1 | `mcp__kjptai-devops__query_pipeline` | 查询本人流水线列表或按 ID 查详情 | `pipelineConfId?`, `_meta?` |
| 2 | `mcp__kjptai-devops__query_pipeline_build` | 查询构建历史/详情 | `pipelineConfId?`, `buildId?`, `statusList?`, `triggerUserNameList?`, `branch?`, `offset?`, `limit?` |
| 3 | `mcp__kjptai-devops__prepare_pipeline_run` | 准备运行草稿（不执行） | `pipelineConfId`*, `draftId?`, `parameterOverrides?`, `sourceOverrides?` |
| 4 | `mcp__kjptai-devops__submit_pipeline_run` | 提交执行（需确认） | `draftId`*, `draftVersion`*, `confirmed`* (const true) |
| 5 | `mcp__kjptai-devops__set_pipeline_webhook` | Webhook 通知设置（两步确认） | `pipelineConfId`*, `toUser`*, `noticeEventList`*, `enable`*, `confirmed?` |

---

## 概述

本技能为 `/ba-to-dev`（业务需求转研发文档）反向供给全部输入要素：输出结构显式覆盖 ba-to-dev 的 Front Matter 9 项、`一、需求背景`/`二、需求内容` 原文、`评审纪要`事实源②（需求/Story/任务单），使 ba-to-dev 可直接消费。

**当前状态**：kjptai MCP 已完整提供需求管理工具集（9 个），支持纯 MCP 直连模式，无需 Playwright 回退。

> [!PRIORITY] `/ba-to-dev` **优先调用本技能**
> 当执行 `/ba-to-dev` 转换时，**必须优先调用本技能（`gtht-req-query`）**而非 `req-query`。本技能为 MCP 原生直连模式，响应速度更快（<0.5s）、数据更准确、无需浏览器回退。仅在 MCP 不可用时才考虑使用 `req-query`（Playwright 模式）。

## 触发条件

当用户提及以下关键词时使用本技能：

- 需求查询、查需求、查询需求、gtht-req-query
- 提供需求编号格式如 `R2605250074` / `R26xxxxxxx`
- 需求管理、需求列表、查 Story、查需求状态、查 Task
- `/ba-to-dev` 工作流（**优先调用本技能**）

> [!NOTE]
> 当执行 `/ba-to-dev` 转换时，本技能为**第一数据源**。`req-query`（Playwright 模式）仅在 MCP 不可用时作为备用。

## 工作流程（MCP 直连模式）

1. **需求要素查询** — 调用 `mcp__kjptai__query_requirement`，传入 `demandId=<需求编号>`（如 `R2608180076`），取回：标题、状态、优先级、**一/二级领域**、提出部门、提交人（姓名-老工号）、受理人（姓名-工号）、业务主管、业务验收人、共同受理人、期望上线、**创建时间**、公司信息技术项目、需求价值量、是否暂停、是否涉及交易结算、是否涉及监管报送、需求描述（HTML 富文本，含「一、需求背景」「二、需求内容」结构与内嵌 `<img>` 附件链接）
2. **关联 Story 查询** — 调用 `mcp__kjptai__query_story`，传入 `demandId=<需求编号>`，取回关联 Story 列表（编号、标题、状态、所属系统、开发负责人、SIT 负责人等）
3. **（可选）任务单查询** — 若需评审纪要事实源②补全「任务单」，调用 `mcp__kjptai__query_task`（按 Story 编号或系统名称过滤）；无任务单则为空
4. **描述解析与分段** — 将需求描述 HTML 去标签转纯文本；按 `<h4>一、需求背景</h4>` / `<h4>二、需求内容</h4>` 切分为两段；过滤平台占位符（`【填写需求背景:...】`、`【填写需求描述:...】`），过滤后无实际内容则写 `无`；提取 `<img src>` / `download?id=` 链接形成**附件清单**
5. **领域与涉及系统推导** — 基于「一/二级领域」关键词推断 `domain`（信用两融/低延时交易/清算与对账/风控与盯市/接口与报送）与**涉及系统**（如「结算业务工程」→ 集中清算系统），均标注「推导，待研发确认」
6. **合并输出** — 按下方输出格式整合，末尾附 `ba-to-dev 要素映射` 块，逐项标明本输出如何喂给 ba-to-dev 的 Front Matter / 章节

> 若需「计划生产排期」「备注」等仅存在于大宽表的字段，改用 `wide-table-query` 技能。
>
> **实测结论（2026-09-10）**：`query_story_detail` 返回的字段清单中**不含通用「备注」字段**，仅有场景化备注：`noSitReasonRemarks`（免 SIT 原因备注）、`grayUpgradeRemarks`（灰度升级备注）；`query_story` 列表仅输出固定 7 列摘要（编号/标题/状态/需求编号/所属系统/开发负责人/SIT 负责人），同样无备注。要取 Story 备注只能走大宽表或浏览器抓页面。

## 使用方法

### 查询单条需求详情

```text
调用 mcp__kjptai__query_requirement(demandId="R2608180076")
```

返回固定完整字段清单（detailFields），包括：需求编号、标题、需求类型、需求子类型、状态、优先级、一级领域、二级领域、提出部门、提交人（姓名-老工号）、业务主管、受理人（姓名-工号）、共同受理人、业务验收人、期望上线时间、需求评审预计交付时间、需求实际交付验收时间、创建时间、公司信息技术项目、需求价值量、是否暂停、是否涉及交易结算、是否涉及监管报送、是否影响灰度升级、当前 OA 节点、描述（HTML 富文本）。

### 查询关联 Story

```text
调用 mcp__kjptai__query_story(demandId="R2608180076")
```

### 查询关联 Task

```text
调用 mcp__kjptai__query_task(storyNo="R2608180076-1", taskType="2")  # 开发任务
```

`taskType` 支持：`2`=开发任务、`3`=SIT 测试任务、`4`=UAT 测试任务。

### 列表查询（常用筛选条件）

```text
# 我的需求
调用 mcp__kjptai__query_requirement(mineScope="development_testing")

# 我受理的需求
调用 mcp__kjptai__query_requirement(mineScope="accepted")

# 按状态分类查询
调用 mcp__kjptai__query_requirement(demandStatusCategory="IN_PROGRESS")  # 进行中
调用 mcp__kjptai__query_requirement(demandStatusCategory="COMPLETED")    # 已完成
调用 mcp__kjptai__query_requirement(demandStatusCategory="DRAFT")        # 草稿

# 按受理人查询
调用 mcp__kjptai__query_requirement(receiverNames=["吴进-125360"])

# 按提出部门查询
调用 mcp__kjptai__query_requirement(departmentNames=["融资融券部"])

# 按一级领域查询
调用 mcp__kjptai__query_requirement(primaryDomainNames=["合并专属"])

# 按二级领域查询
调用 mcp__kjptai__query_requirement(secondaryDomainNames=["经纪业务核心交易、结算业务工程"])

# 按预计上线时间范围查询
调用 mcp__kjptai__query_requirement(esDuedateStartTime="2026-09-01", esDuedateEndTime="2026-12-31")

# 重点关注需求
调用 mcp__kjptai__query_requirement(keyFocus="1")

# 逾期需求
调用 mcp__kjptai__query_requirement(isexceed="1")
```

### mineScope 枚举说明

| 值 | 语义 |
| :--- | :--- |
| `development_testing` | 我的需求（参与开发或测试） |
| `submitted` | 我提出的 |
| `department` | 我部门的 |
| `domain` | 我对口领域 |
| `team` | 我所在组参与 |
| `pending_it_evaluation` | 待我 IT 评估 |
| `evaluated_it` | 我已 IT 评估 |
| `horizontal` | 我横向平台 |
| `accepted` | 我受理的 |
| `data` | 数据需求 |

### demandStatusCategory 枚举说明

| 值 | 语义 |
| :--- | :--- |
| `IN_PROGRESS` / `进行中` / `ONGOING` | 进行中 |
| `COMPLETED` / `已完成` / `已上线` / `FINISHED` | 已完成 |
| `TERMINATED` / `已终止` / `终止` / `CANCELLED` | 已终止 |
| `DRAFT` / `草稿` / `暂存` | 草稿 |

### 输出格式

对话窗口输出示例（以 R2608180076 为例）：

```
**需求查询　|　R2608180076**

【需求要素】
　　需求编号：R2608180076
　　标题：【集中清算】融券合约顺延改造
　　需求类型：标准需求
　　需求子类型：普通业务功能
　　级别：P4
　　状态：开发待排期
　　一级领域：合并专属
　　二级领域：经纪业务核心交易、结算业务工程
　　提出部门：融资融券部
　　提交人：孙鹰-118072
　　业务主管：胡业伟-111958
　　受理人：吴进-125360
　　业务验收人：孙鹰-118072
　　期望上线时间：2026-10-31
　　创建时间：2026-08-18 15:50:03
　　公司信息技术项目：P26173-券源平台建设
　　需求价值量：5.2
　　是否暂停：否
　　是否涉及监管报送：否

【涉及系统（推导，待研发确认）】
　　二级领域含「结算业务工程」→ 推导改造系统：集中清算系统

【需求描述（原文，已分段、去占位符）】
　　▶ 一、需求背景
　　　　（平台占位符已过滤，无用户实际填写内容 → 无）
　　▶ 二、需求内容
　　　　根据两融合约及公司法合要求，现需对融券合约进行顺延改造:
　　　　1）若融券合约到期日当日，同时该合约证券为停牌日，则到期日自动向后顺延一个交易日。
　　　　2）顺延后，若次日仍为停牌日，则次日当日继续向后顺延一个交易日，直到证券恢复交易
　　　　3）仅对融券合约生效，融资合约不做处理。

【附件清单】
　　1. 图片：https://fintech.gtht.com.cn/download?id=981eccee35424c79bb
　　　　（需求背景内嵌图；ba-to-dev 中保留为 Markdown 图片引用融入正文）

【关联 Story（1 条）】
　　1. R2608180076-1 — 【集中清算】融券合约顺延改造
　　　　状态：- | 所属系统：- | 开发负责人：- | SIT负责人：-

【关联 Task（1 条）】
　　1. JZQSPT-T202610047 — 【集中清算】融券合约顺延改造
　　　　类型：开发 | 状态：待排期 | 经办人：石雪军 | 预计结束：2026-09-18

【ba-to-dev 要素映射（供直接消费）】
　　req_id      ← 需求编号 R2608180076
　　submitter   ← 提交人 孙鹰-118072 + 提出部门 融资融券部
　　created     ← 创建时间 2026-08-18
　　domain      ← 二级领域「结算业务工程」→ 清算与对账（推导）
　　system      ← 涉及系统推导「集中清算系统」（推导，待研发确认）
　　status      ← 状态 开发待排期
　　ndw         ← 平台无，ba-to-dev 默认 0.3
　　预计上线     ← 期望上线 2026-10-31 → 2026年10月上线
　　一/二章      ← 需求描述（已按背景/内容分段）
　　评审纪要源② ← 需求要素 + Story 列表 + Task 列表

【详情页】https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId=R2608180076&templateId=8888&flag=1
```

## 字段映射（kjptai MCP → 输出 → ba-to-dev 用途）

| 输出字段 | kjptai MCP 来源 | ba-to-dev 用途 |
| :--- | :--- | :--- |
| 需求编号 | `query_requirement` demandId | Front Matter `req_id` |
| 标题 | `query_requirement` 标题 | H1 标题 / 文件名 |
| 需求类型 | `query_requirement` 需求类型/子类型 | 需求分类参考 |
| 级别 | `query_requirement` 优先级 | 优先级标注（P0–P4） |
| 状态 | `query_requirement` 状态 | Front Matter `status`（实时） |
| 一级领域 | `query_requirement` 一级领域 | 推导 `domain` |
| 二级领域 | `query_requirement` 二级领域 | 推导 `domain` / `system` |
| 提出部门 | `query_requirement` 提出部门 | `submitter` 部门部分 |
| 提交人 | `query_requirement` 提交人（姓名-老工号） | `submitter` 姓名部分 |
| 业务主管 | `query_requirement` 业务主管 | 评审纪要参考 |
| 受理人 | `query_requirement` 受理人（姓名-工号） | 受理人 / 评审纪要禁填校验 |
| 共同受理人 | `query_requirement` 共同受理人 | 评审纪要参考 |
| 业务验收人 | `query_requirement` 业务验收人 | 验收流程参考 |
| 期望上线时间 | `query_requirement` 期望上线时间 | 预计上线日期（YYYY年MM月上线） |
| 创建时间 | `query_requirement` 创建时间 | Front Matter `created` |
| 公司信息技术项目 | `query_requirement` 公司信息技术项目 | 项目关联参考 |
| 需求价值量 | `query_requirement` 需求价值量 | NDW 参考值 |
| 是否暂停 | `query_requirement` 是否暂停 | 状态判断 |
| 是否涉及交易结算 | `query_requirement` 是否涉及交易结算 | 系统推导参考 |
| 是否涉及监管报送 | `query_requirement` 是否涉及监管报送 | 合规标注 |
| 是否影响灰度升级 | `query_requirement` 是否影响灰度升级 | 上线策略参考 |
| 需求描述（分段） | `query_requirement` 描述 HTML | **一、需求背景** / **二、需求内容**（100% 原文照搬） |
| 附件清单 | 描述内 `<img>` / `download?id=` | ba-to-dev 第 6 条：附件智能解析与深度融合 |
| 涉及系统（推导） | 二级领域关键词推导 | Front Matter `system` / 评审纪要改造范围 |
| 关联 Story | `query_story`（demandId） | 评审纪要源② / 拆分 Story 输入 |
| 关联 Task | `query_task`（storyNo） | 评审纪要源② 补全 |

## 技术细节

- **两个 MCP 服务器**：`kjptai`（`/kjptai/api/mcp`，9 个需求管理工具）和 `kjptai-devops`（`/devopsai/api/mcp`，5 个流水线工具），是**两个独立的 MCP 服务器**，指向不同端点、不同 Platform ID、不同工具集
- **鉴权方式**：服务端 Bearer Token（JWT），配置于 `~/.workbuddy/mcp.json` 的 `headers.Authorization` 字段；无需本机 session、无需浏览器
- **工具调用名规范（2026-09-09 实测落地）**：调用 kjptai MCP 工具时，`tool_name` 必须使用**不带前缀**的工具名（如 `query_requirement`、`query_story`、`query_task`）。若使用 `mcp__kjptai__query_requirement` 带前缀形式，会报「工具 mcp__kjptai__query_requirement 在服务器 kjptai 中不存在」。R2603180028 实测：带前缀调用失败，去掉前缀后成功。上文各节中的 `mcp__kjptai__` 前缀仅为 MCP 协议层全名示意，**实际 `use_mcp_tool` 调用一律省略该前缀**。
- **配置字段格式**：必须使用 `"transport": "streamable_http"`（下划线），不能用 `"type": "streamable-http"`（连字符+错误字段名）
- **detailFields 展示规范**：`query_requirement` 查询单条详情时返回固定完整字段清单；展示时应保留原字段名称、顺序和空值占位符，不应缩写或省略
- **富文本描述处理**：`query_requirement` 返回「描述」为 HTML 富文本，输出时剥离标签转纯文本；按 `<h4>一、需求背景</h4>` / `<h4>二、需求内容</h4>` 切分两段；图片链接保留为 Markdown 图片引用并列入附件清单
- **占位符过滤**：必须剔除平台模板占位符（`【填写需求背景:...】`、`【填写需求描述:...】`）；过滤后无实际内容写 `无`
- **姓名-工号格式**：kjptai 返回的提交人为「姓名-老工号」格式（如 `孙鹰-118072`），受理人为「姓名-工号」格式（如 `吴进-125360`）；均直接可用
- **领域→系统推导**：基于二级领域关键词推断（如「结算/清算」→ 集中清算系统、「交易」→ 集中交易/低延时、「融资融券/信用」→ 融资融券相关、「参数」→ 交易参数管理后台系统、「报送/监管」→ 证金监管数据报送子系统）；推导结果标注「待研发确认」，不覆盖 ba-to-dev 实际判定
- **详情页 URL**：`/kjpt/DemandManage/details?demandId={编号}&templateId=8888&flag=1`（仅供人工跳转参考，查询本身通过 MCP 不访问该网页）

## 注意事项

- **若 kjptai MCP 工具未连接**：提示用户检查 **kjptai 连接器**状态（WorkBuddy 右上角 → 自定义连接器 → 信任 kjptai）
- **配置字段陷阱**：`transport` 必须使用下划线格式 `streamable_http`；曾因使用 `type: "streamable-http"` 导致整个服务器未加载，误判工具不存在
- **工具名前缀陷阱（2026-09-09 实测落地）**：`use_mcp_tool` 的 `tool_name` 参数传 `mcp__kjptai__query_requirement` 会报"工具不存在"，必须传 `query_requirement`（不带 `mcp__kjptai__` 前缀）。其他 MCP 服务器（如 kjptmcp-server）的工具名同理无需加前缀。
- 「涉及系统」「domain」为基于领域的推导值，最终以 ba-to-dev 结合 `system_list.csv` 与需求实际改造范围判定为准
- **`query_requirement` 只查询需求本身**，不查询 Story、Task 或风险评估；需分别调用 `query_story` / `query_task`
- **创建/操作类工具的两步确认机制**：`create_requirement` → `submit_requirement_create`、`accept_requirement`、`create_story` 等均采用首次返回摘要、用户确认后携带 confirmed=true 再次调用的模式
- **Task 类型区分**：`query_task` 的 `taskType` 支持开发(2)、SIT(3)、UAT(4) 三种类型，一次查询只能传一种类型
