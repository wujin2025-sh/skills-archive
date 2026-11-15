# 数据库参数交叉验证指南 (DB Lookup Reference)

本文档为 `ba-to-dev` 技能的**数据库参数交叉验证**专项参考，与 [`graph_lookup.md`](file:///Users/wujin/.chat/skills/ba-to-dev/references/graph_lookup.md)（代码知识图谱）配套使用。

**核心理念**：代码知识图谱回答「代码怎么写的」，数据库回答「数据/参数实际是什么」。两者结合，可在需求分析时交叉验证表结构、参数值、字典含义，大幅提升分析准确度，避免「代码引用某表/参数，但实际数据库结构或值已变化」的口径偏差。

> **🔑 DB-First 权威源优先（P0 铁律，2026-11-12）**：凡**表名/字段名/字段类型/参数编码/默认值**等客观事实，**数据库直查结果高于代码/源码推断**——数据库返回的是最权威表结构，与源码/文档冲突时**以数据库为准**（并在回复注明「数据库直查结果」）。严禁凭**表名语义/关键词/函数名**臆断表用途与字段归属。**典型名不副实**：`comm.comm_secuid_total`（集中清算 comm 库）表名带 "secuid" 实为**计数表**（仅 partid/nodeid/market/secuid/htcnt/gjcnt 等，无证券名称字段），标准证券名称源是 `comm.comm_stock.stkname`（22 字段，`market`+`stkcode`+`stkname`）；`node.node_secuid` 含账户维度 `fundacct`，为账户证券关联表而非纯证券主参数表。写表名前先问「有 dbq 实证吗」，拿不出就 `dbq` 操作实证（见 SKILL P0#22）。

---

## 1. 系统代码图谱 ↔ 数据库连接映射全景

| 系统简称 | 系统标准名称 (`system_list.csv`) | CBM 代码图谱 | 数据库查询 profile (dbq) | 数据库类型 | 主机:端口/库 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`jzjy`** | 集中交易系统 | 🟢 已接入 (~38万节点) | `jzjy_sit` | sqlserver | 10.187.160.91:1433 |
| **`dys`** | 低延时交易系统 / 低延时交易系统（创新域） | 🟢 已接入 (~6.5万节点) | `dys95` | mysql 8 | 10.187.101.51:8885 / 多库（`tradingdb`/`tradingconfigdb`/`basedb` 等） |
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

**常用命令**（dbq 已加入 PATH `/usr/local/bin/dbq`，密码自动从 `.db_credentials` 加载，无需手动传 DB_PASSWORD）：
```bash
dbq --list                                        # 查看全部 profile 可用性
dbq jzjy_sit --list-databases                     # 列库（仅 run 可读）
dbq cszx_sit --list-tables                        # 列表（默认过滤备份表，run=1043 表）
dbq dys95 --table tradingdb.t_order               # 精确查表字段
dbq jzqs_sit --search-table '%order%'             # 按关键字搜表
dbq jzjy_sit --table run.dbo.orderrec             # 委托表字段（91 字段）
dbq cszx_sit --table run.dbo.paramcfg             # 参数主表字段（12 字段）
dbq dys95 --sql "SELECT * FROM tradingconfigdb.t_dict WHERE category_code='BusinessType'"  # ⚠️ 用 tradingconfigdb（完整版48条），不是 tradingdb（仅17条）
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

### 模式⑤：多字典表探查（防查错库导致结论错误，2026-11-09 R2609160118 教训）

> ⚠️ **同一系统可能有多个同名字典表分布在不同库**（如 dys 有 `tradingdb.t_dict` 仅 17 条 BusinessType 和 `tradingconfigdb.t_dict` 48 条完整版）。查字典时**必须先搜全部同名表，对比记录数后选用完整版**，严禁只查一个库就下结论。

```sql
-- 先搜全部同名表
SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_ROWS FROM information_schema.TABLES 
WHERE TABLE_NAME = 't_dict' ORDER BY TABLE_ROWS DESC;
-- 对比各库记录数，选用完整版（如 tradingconfigdb.t_dict 48 条 > tradingdb.t_dict 17 条）
```

**用途**：避免因查到不完整字典表而错误结论"字典表未维护某枚举"。实测教训：R2609160118 初查 `tradingdb.t_dict` 仅 17 条 BusinessType（缺 200+ 还款类），误判"字典表未维护还款类"，实际 `tradingconfigdb.t_dict` 48 条完整含 202=直接还款、208=指定合约直接还款。

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
| **jzjy** | `creditdebts`（融资融券负债，含 `applydate/applysno/sno/groupsno/debtskind`） | `orderrec` | 委托表无独立 `contract_date/contract_sno`，**复用 `bankfrzsno`(varchar32) 字段存储合约编号**（合约发生日期+合约流水号） |
| **dys** | `t_credit_debts`（按 `DebtsUniqKey(ContractDate, ContractSno)` 定位） | `t_order` | 委托结构对象已含合约标识；`t_order` 复用 `bankfrzsno` 字段存储合约编号；`business_type=208`=指定合约直接还款、`bsflag='ZZ'` |
| **jzqs** | `cjs_creditdebts`（对应 `m_map_node_creditdebts`，含 `applydate/applysno/sno/groupsno/specdate/specsno/debtskind`），费用 `cjs_creditfee` | `cjs_orderrec` | 委托表无独立 `contract_date/contract_sno`，**复用 `bankfrzsno`(varchar32) 字段存储合约编号** |

---

## 7. dys 字典表正确来源（2026-11-09 R2609160118 教训固化）

> ⚠️ dys 有两个同名 `t_dict` 表分布在不同库，**必须查 `tradingconfigdb.t_dict`（完整版）**，严禁查 `tradingdb.t_dict`（不完整版）。

| 库.表 | 分类数 | BusinessType 条数 | 是否含还款类(200+) | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `tradingconfigdb.t_dict` | 172 | 48 | ✅ 完整 | **正确来源**，含 202=直接还款、208=指定合约直接还款等 |
| `tradingdb.t_dict` | ~20 | 17 | ❌ 缺失 | 仅含基础业务类型(1-98)，200+ 枚举未同步落库 |

**字典表字段名**：`category_code`（非 `category`）、`code`、`value`、`name`。

**BusinessType 关键枚举速查**（`tradingconfigdb.t_dict`，48 条）：

| value | code | name | 说明 |
| :--- | :--- | :--- | :--- |
| 200 | CreditAuction | 信用账户普通买入/普通卖出（卖券还款）交易业务 | |
| 201 | MarginTrading | 融资买入/融券卖出交易业务 | |
| 202 | DirectRepay | 直接还款 | `bsflag='ZZ'` |
| 203 | CollateralInOrOut | 担保品转入/转出 | |
| 204 | BuySecuRepay | 买券还券 | |
| 205 | CurSecuRepay | 现券还券 | |
| 208 | DirectRepayAppoint | **指定合约直接还款** | `bsflag='ZZ'` |

### 买卖类别（bsflag）与业务类型（business_type）关系

> 实测来源：`tradingdb.t_order`（dys），2026-11-09 R2609160118 采集。

| business_type | bsflag | side | code | 含义 | 记录数 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 208 | ZZ | 1 | DirectRepayAppoint | 指定合约直接还款 | 27 |
| 202 | ZZ | 1 | DirectRepay | 直接还款 | 8 |

- `bsflag='ZZ'`：还款类委托专用买卖方向标识，**字典表未定义**（非 Side 字典枚举，为还款类委托特有）；
- 202 与 208 的 `bsflag` 均为 `ZZ`，**区分靠 `business_type`**（208 vs 202）；
- `side='1'`（买方向），还款类委托统一为买方向；
- `bsflag` 全量分布：`0B`(542) > `0S`(121) > `ZZ`(35) > `0y`(23) > `0w`(19) 等，`ZZ` 为第三大类。