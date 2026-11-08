# 数据库参数交叉验证指南 (DB Lookup Reference)

本文档为 `ba-to-dev` 技能的**数据库参数交叉验证**专项参考，与 [`graph_lookup.md`](file:///Users/wujin/.chat/skills/ba-to-dev/references/graph_lookup.md)（代码知识图谱）配套使用。

**核心理念**：代码知识图谱回答「代码怎么写的」，数据库回答「数据/参数实际是什么」。两者结合，可在需求分析时交叉验证表结构、参数值、字典含义，大幅提升分析准确度，避免「代码引用某表/参数，但实际数据库结构或值已变化」的口径偏差。

---

## 1. 系统代码图谱 ↔ 数据库连接映射全景

| 系统简称 | 系统标准名称 (`system_list.csv`) | CBM 代码图谱 | 数据库查询 profile (dbq) | 数据库类型 | 主机:端口/库 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`jzjy`** | 集中交易系统 | 🟢 已接入 (~38万节点) | `jzjy_sit` | sqlserver | 10.187.160.91:1433 |
| **`dys`** | 低延时交易系统 / 低延时交易系统（创新域） | 🟢 已接入 (~6.5万节点) | `dys95` | mysql 8 | 10.187.101.51:8885 / `basedb` |
| **`jzqs`** | 集中清算系统 | 🟢 已接入 (~42万节点) | `jzqs_sit`（`--database node/comm`） | mysql 兼容(OB) | 10.187.109.56:2883 / `node` / `comm` |
| **`cszx`** | 交易参数管理后台系统 | 🟢 已接入 (~27.6万节点) | `cszx_sit` | sqlserver | 10.187.64.75:1433 / 仅 `run` 可读 |
| **`grc`** | 低延时全局风控系统 | 🟢 已接入 (~1.85万节点) | -（无 DB 连接） | - | - |
| **`djgl`/`ssjs`/`jzyy`** | 客户登记/实时计算/集中营运 | ⚪ 暂无图谱 | - | - | - |

> **映射铁律**：
> - 每个系统的**代码知识图谱**与其**数据库**一一对应（jzjy 图谱 ↔ jzjy 库，dys 图谱 ↔ dys 库，jzqs 图谱 ↔ jzqs 库，cszx 图谱 ↔ cszx 库）；
> - **`grc`（低延时全局风控系统）代码图谱已接入（~1.85万节点），但暂未配置数据库直连**，GRC 溯源以代码图谱 + 源码 grep 为主，暂不做数据库交叉验证；
> - 严禁跨系统借用：集中交易的代码/表不得用低延时库验证，反之亦然；
> - 低延时「域归属」与图谱一致：需求含「个微」/「98创新域」时用 `dys` 图谱与 `dys95` profile；两融泛称「低延时」默认 95 信创域。

---

## 2. 数据库查询方式（「数据库查询」SKILL 优先，dbx MCP 降级）

**优先调用「数据库查询」SKILL（/db-schema-query）**，统一入口：`/Users/wujin/.chat/skills/数据库查询/scripts/dbq`（按 profile 自动选择脚本与 Python 环境）：

| profile | 系统 | 脚本 / 环境 | 数据库类型 | 可读库 |
| :--- | :--- | :--- | :--- | :--- |
| `dys95` | 低延时 | `query_schema.py`（/usr/local/bin/python3 + pymysql） | mysql 8 | `basedb` 等 |
| `jzqs_sit` | 集中清算 | `query_schema.py`（OceanBase MySQL 协议兼容） | mysql 兼容 | `node` / `comm`（`--database`） |
| `jzjy_sit` | 集中交易 | `query_sqlserver.py`（workbuddy python3.13.12 + pymssql, TDS 7.0） | sqlserver | 仅 `run`（其余 916） |
| `cszx_sit` | 参数中心 | `query_sqlserver.py`（同上） | sqlserver | 仅 `run`（其余 18456） |

**常用命令**（密码不落盘，运行时代环境变量索取）：
```bash
dbq --list                                        # 查看全部 profile 可用性
dbq --profile jzjy_sit --list-databases           # 列库（仅 run 可读）
dbq --profile cszx_sit --list-tables              # 列表（默认过滤备份表，run=1043 表）
dbq --profile dys95 --table tradingdb.t_order     # 精确查表字段
dbq --profile jzqs_sit --search-table '%order%'   # 按关键字搜表
dbq --profile jzjy_sit --table run.dbo.orderrec   # 委托表字段（91 字段）
dbq --profile cszx_sit --table run.dbo.paramcfg   # 参数主表字段（12 字段）
```
> ⚠️ `--search-field` 仅配合 `--table 库.表` 精确限定使用；jzqs 实例全库扫字段会 60s 超时 2013。搜索默认 `--exclude-backup` 过滤 `bcp_`/`SYNC_`/`_bak`/`_wq`/纯数字后缀备份表，`--max-rows 100` 自动摘要。

> ⚠️ **降级路径（dbx MCP，仅当 SKILL 不可用/凭据被拒/超时时）**：`use_mcp_tool`，server_name=`dbx`，`dbx_execute_query(connection_id, sql)`；连接名参考 `dbx_list_connections`（`jzjy-sit64` / `dys-95` / `jzqs-sit64-jj` / `jzqs-sit64-comm` / `cszx-sit64` / `kjpt`）。dbx 走代理隧道 502 时 `NO_PROXY=fintech.gtht.com.cn` 直连重试（与 kjptai 脚本同源策略）。

---

## 3. 数据库交叉验证流水线（与图谱配合）

**触发时机**：Step 2 架构细化中，代码图谱定位到**表名、字段、参数编码、存储过程**后，随即调用「数据库查询」SKILL（`dbq <profile>`）对同一系统数据库做交叉验证。

### 模式①：表结构验证（代码引用表 vs 实际表结构）
```sql
-- sqlserver (jzjy / cszx)
SELECT COLUMN_NAME, DATA_TYPE FROM <库>.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME='<表名>' ORDER BY ORDINAL_POSITION;
-- mysql (dys / jzqs)
SELECT COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA='<库>' AND TABLE_NAME='<表名>' ORDER BY ORDINAL_POSITION;
```
**用途**：确认代码中使用的列名/类型与数据库实际一致，识别字段口径变化。

### 模式②：参数值溯源（代码读取的参数编码 → 实际值）
```sql
SELECT * FROM <库>.<表名> WHERE <编码字段>='<参数编码>';
```
**用途**：给出参数当前值，评估需求改动影响面。例：`creditmixparam` 表 `paramkinds='0m'` 查「融资专户头寸控制」当前值。

### 模式③：字典名称解析（参数编码 → 业务中文名）
```sql
-- 参数中心 cszx 通用字典三件套
SELECT dictitem, itemname FROM <库>.dbo.dictindex WHERE dictitem='<字典项>';
SELECT dictitem, subitem, subitemname FROM <库>.dbo.dictvalue
WHERE dictitem='<字典项>' AND LTRIM(RTRIM(subitem))=LTRIM(RTRIM('<参数编码>'));
```
**用途**：把代码/表中的编码翻译成业务可理解的中文名，写入评审纪要/技术实现时用业务语言表达。

### 模式④：影响分析（代码 WHERE 多参数 → 关联表）
```sql
SELECT <编码字段>, COUNT(*) FROM <库>.<表名> GROUP BY <编码字段> ORDER BY <编码字段>;
```
**用途**：评估批量参数改动的波及范围，识别代码分支里所有相关编码。

---

## 4. 参数中心（cszx）两融核心参数表速查

> 库 `run`（sqlserver），字典表在 `run.dbo.{dictindex|dictlist|dictvalue}`。

| 表名 | 说明 | 关键字段 |
| :--- | :--- | :--- |
| `creditparam` | 信用参数（基础） | `paramkinds`/`amt`/`rate`/`qty`/`cparam` |
| `creditmixparam` | **信用混杂参数** | `paramkinds`/`amt`/`rate`/`qty`/`cparam` |
| `creditalertparam` | 信用预警参数 | - |
| `creditmargin` | 信用保证金参数 | - |
| `creditdiscountlevel` | 信用折扣率档位 | - |
| `credittargetstk` / `creditpledgestkrate` | 信用标的/质押折算率 | - |
| `loan_mixedparam` | 贷款混杂参数 | - |
| `loanrate` | 贷款利率 | - |

**字典关联**：`creditmixparam.paramkinds` ↔ `dictvalue(dictitem='Z000409').subitem`（两融杂项参数参数）；`creditparam` 关联 `dictitem` 需按具体字典项确认。

---

## 5. 证据融入与链接格式铁律

1. **数据库查询结果**在文档中作为「参数当前值/表结构确认」证据，写入第三章技术实现的对应小节；
2. **严禁把数据库表名/字段名直接暴露在评审纪要**（第 3 项【各系统改造功能】必须业务语言），仅置于第三章技术实现；
3. 数据库查询得出的参数中文名/值，用于评审纪要第 6 项【业务参数】、第 9 项【业务关注点】的业务化表述；
4. 表名有改动或结构不明确时，注明 `(具体表名以研发设计为准)`，严禁凭空捏造。

---

## 6. 融资融券还款链路核心模块/函数速查

> 来源：R2609160118【指定合约直接还款】溯源沉淀。后续还款类需求可直接复用，无需重复溯源。

### 还款顺序业务规则（通用）
- **直接还款**：先还息费、再还本金（`GetRepayOrderOfOther`）；
- **融资还款**：按金额（`GetRepayOrderOfRzamt`）；
- **融券还款**：按数量（`GetRepayOrderOfRqqty`）。

### 跨系统还款核心入口（委托链路：柜台 → 交易 → 清算 → 回执）

| 系统 | 核心文件 | 关键函数 | 职责 |
| :--- | :--- | :--- | :--- |
| **jzjy** | `lbmdll/lbm_periphery/loantran.cpp` | `Cperiphery::perLoanFundRepay`（:8659） | 日间还款核心入口：以 `applydate/applysno/sno/groupsno` 查询 `creditdebts` 定位合约，按 `debtskind` 区分融资/融券 |
| **jzjy** | `lbmdll/lbm_periphery/LBMExport.cpp` | `perLoanFundRepay`（:13578） | 还款委托导出 |
| **jzjy** | `lbmdll/lbm_sett/SettCrdMatchCommit.cpp` | `SettDoCommit_Repay_DEBT`（:5571）、`SettDoCommit_Repay_FUNDSTK`（:5821） | 清算侧逐笔还款提交：负债扣减与资金/股票变动 |
| **dys** | `biz_impl/business/direct_repay_appoint/src/direct_repay_appoint_security_trader.cpp` | `ProcessDirectRepayAppoint`（:125） | 指定合约还款核心交易：按 `ContractDate+ContractSno` 限定本笔合约 |
| **dys** | `.../direct_repay_appoint_fee_util.cpp` | `ReturnFund`（:29）、`GetRepayItems`（:388） | 还款项计算与逐笔还款 |
| **jzqs** | `lbm/lbm_book/DealCredit.cpp` | `CDealCredit::RepayContractDebets`（:1439） | 偿还合约负债核心：按 `cDebtType` switch 分派，遍历 `m_map_node_creditdebts` 逐笔偿还 |
| **jzqs** | `lbm/lbm_book/DealCredit.cpp` | `GetRepayOrderOfRzamt`（:16305）/`Rqqty`（:16441）/`Other`（:16345） | 还款顺序决策：融资按金额、融券按数量、其他（直接还款先息费后本金） |
| **jzqs** | `lbm/lbm_book/DealCredit.cpp` | `RepayCreditDebets`（:961） | 偿还负债历史入口 |

### 还款链路核心表（跨系统）
| 系统 | 负债表 | 委托表 | 备注 |
| :--- | :--- | :--- | :--- |
| **jzjy** | `creditdebts`（融资融券负债，含 `applydate/applysno/sno/groupsno/debtskind`） | `orderrec` | ⚠️ 无 `contract_date/contract_sno`，指定合约还款委托需新增或复用字段 |
| **dys** | `t_credit_debts`（按 `DebtsUniqKey(ContractDate, ContractSno)` 定位） | `t_order` | 委托结构对象已含合约标识，需确认落库映射 |
| **jzqs** | `node_creditdebts`（对应 `m_map_node_creditdebts`）、费用 `node_creditfee` | `node_orderrec` | ⚠️ 无 `contract_date/contract_sno` |