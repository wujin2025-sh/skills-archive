---
name: db-schema-query
description: 数据库表结构与表字段极速查询（查表 / 表字段 / 表结构 / 字段注释 / 数据库连接）。优先尝试 dbx MCP 直查（已配置凭据实例秒级返回）；dbx
  不可用或报 1045 凭据被拒时降级直连元数据视图（凭据向用户索取，绝不落盘、绝不出现在记忆）。内置已核验的四套库表分布参考
  （dys 低延时 tradingdb.t_order / 集中清算 node_orderrec / 集中交易 SQL Server run.dbo.orderrec / 参数中心后台 SQL Server paramcfg），支持列库、列表、按表查字段
  （名称/类型/长度/键/注释）、按关键字搜表与搜字段。MySQL/OceanBase 用 /usr/local/bin/python3（自带 pymysql），SQL Server 用
  workbuddy python3（自带 pymssql，TDS 7.0）。触发词：数据库查询、查表、查字段、表结构、字段查询、表字段、字段注释、查数据库、
  数据库表、db-query、schema-query、information_schema、查低延时表、dys 表、集中交易表、orderrec。
metadata:
  agent_created: true
disable: false
---

# 数据库查询 (数据库直查优先 · DB-First)

凡是查询**表名 / 表字段 / 字段类型 / 字段注释 / 表分布**，一律优先从数据库直查，
秒级得到权威结果，**禁止凭空猜测表名字段名、禁止把表名写成占位符**（P0 红线）。

---

## 0. 查询策略（重要）

按**数据库直查优先**顺序执行，能直查绝不降级源码搜索：

| 层级 | 方式 | 说明 | 何时使用 |
| --- | --- | --- | --- |
| **D1** | dbx MCP 直查 | 对已配置凭据的服务器实例，直接调 dbx MCP 的查询工具 | **默认首选** |
| **D2** | 直连实例元数据：MySQL/OceanBase → pymysql（`query_schema.py`）；SQL Server → pymssql（`query_sqlserver.py`，TDS 7.0）。凭据经环境变量/交互输入（**不落盘**） | dbx 报 `1045 Access denied` / 连接失败 / dbx 实例未配置时 |
| **D3** | 源码图谱兜底 | CBM / 源码 grep（表名在建表 SQL/结构体） | D1/D2 均不可达时；结论标注「以数据库为准」 |

> ⚠️ **dbx MCP 1045 已知问题（2026-11-05 实测）**：dbx 内置凭据对 dys-95 四个通道
> 全部返回 `ERROR 1045 Access denied for user 'query'@... (using password: YES)`（服务端拒绝旧口令）。
> **遇到 1045 直接走 D2**，向用户索取口令后 pymysql 直连，无需反复尝试 dbx。
>
> ⚠️ **Python 环境**：默认 workbuddy python（3.13.12）**无 pymysql** 但**自带 pymssql 2.4.6**；
> `/usr/local/bin/python3` 自带 pymysql（Homebrew 3.14，PEP 668 拦截无法装 pymssql）。
> 运行约定：MySQL/OceanBase 脚本 `query_schema.py` 用 `/usr/local/bin/python3`；
> **SQL Server 脚本 `query_sqlserver.py` 用 `$HOME/.workbuddy/binaries/python/versions/3.13.12/bin/python3`**（仅 TDS 7.0 可用）。

---

## 1. 快速使用

### 1.0 一键查询（推荐入口）

**首选统一启动器 `dbq`**（按 profile 自动选脚本+Python 解释器，免记环境）：
```bash
DBQ=/Users/wujin/.chat/skills/数据库查询/scripts/dbq
$DBQ --list                                                    # 查看可用 profile
DB_PASSWORD='<用户提供>' $DBQ dys95 --table tradingdb.t_order          # 低延时委托主表
DB_PASSWORD='<用户提供>' $DBQ jzjy_sit --table run.dbo.orderrec        # 集中交易委托主表
DB_PASSWORD='<用户提供>' $DBQ jzjy_sit --search-field err              # 搜字段（默认过滤备份表）
```

> 将 `scripts/` 加入 PATH 后可直接 `dbq <profile> ...`；dbq 内部即按下方「底层脚本直调」执行并透传全部参数。

**底层脚本直调**（dbq 内部即按此执行）：
```bash
# dys-95 低延时 SIT 实例（profile 已内置 host/port/user，密码仍须提供）
DB_PASSWORD='<用户提供>' /usr/local/bin/python3 \
  /Users/wujin/.chat/skills/数据库查询/scripts/query_schema.py --profile dys95 \
  --table tradingdb.t_order
```

密码三选一（**优先级**）：环境变量 `DB_PASSWORD` > `--password` 参数 > 交互式输入（不回显）。
**严禁**把密码写入脚本、配置文件、SKILL.md 或记忆文件。

**SQL Server 实例（jzjy_sit 集中交易 / cszx_sit 参数中心）**：脚本与运行环境相同（pymssql + TDS 7.0 + workbuddy python）：
```bash
S=/Users/wujin/.chat/skills/数据库查询/scripts/query_sqlserver.py
PY="$HOME/.workbuddy/binaries/python/versions/3.13.12/bin/python3"
DB_PASSWORD='<用户提供>' $PY $S --profile jzjy_sit --table run.dbo.orderrec   # 委托主表 91 字段+样例
DB_PASSWORD='<用户提供>' $PY $S --profile jzjy_sit --search-table orderrec      # 表名模糊（run 库命中 655 张）

# 参数中心后台 SQL Server（cszx_sit，同脚本同环境；实例 5 库中仅 run 可读 · 实测）
DB_PASSWORD='<用户提供>' $PY $S --profile cszx_sit --list-databases            # 先探测可访问库
DB_PASSWORD='<用户提供>' $PY $S --profile cszx_sit --table paramcfg            # 参数主表 12 字段（paramid+serverid）
```

### 1.1 典型命令

```bash
S=/Users/wujin/.chat/skills/数据库查询/scripts/query_schema.py
PY=/usr/local/bin/python3

# 1) 列实例下所有数据库
DB_PASSWORD='***' $PY $S --profile dys95 --list-databases

# 2) 列某库所有表（含表注释）
DB_PASSWORD='***' $PY $S --profile dys95 --database tradingdb --list-tables

# 3) 查表字段（库.表 精确命中最优先）
DB_PASSWORD='***' $PY $S --profile dys95 --table tradingdb.t_order

# 4) 表名模糊定位（不确定在哪个库时自动跨库匹配）
DB_PASSWORD='***' $PY $S --profile dys95 --table t_order_status

# 5) 关键字跨库搜表名
DB_PASSWORD='***' $PY $S --profile dys95 --search-table order

# 6) 关键字跨库搜字段名
DB_PASSWORD='***' $PY $S --profile dys95 --search-field err

# 7) 关键字同时匹配字段注释（找业务含义字段，如"备注""错误原因"）
DB_PASSWORD='***' $PY $S --profile dys95 --search-field 备注 --match-comment

# 8) JSON 结构化输出（便于二次加工）
DB_PASSWORD='***' $PY $S --profile dys95 --table tradingdb.t_order --json

# 9) 海量命中自动摘要（默认过滤备份表；--full 关闭截断、--max-rows 调阈值）
DB_PASSWORD='***' $PY $S --profile dys95 --search-field err
```

### 1.2 参数说明

| 参数 | 说明 |
| --- | --- |
| `--profile NAME` | 预置实例：`dys95`=低延时 SIT(`10.187.101.51:8885 user=query`，MySQL)；`jzqs_sit`=集中清算 SIT(`10.187.109.56:2883 user=gjman_q@jjnode#jzqs_sit`，OceanBase MySQL 协议)；`jzjy_sit`=集中交易 SIT(**SQL Server** `10.187.160.91:1433 user=rdonly database=run`，用 `query_sqlserver.py`，TDS 7.0 + workbuddy python)；`cszx_sit`=参数中心后台 SIT(**SQL Server** `10.187.64.75:1433 user=jygl_zd database=run`，同 `query_sqlserver.py`，实例 5 库仅 run 可读、其余 18456)；密码一律运行时提供 |
| `--host / --port / --user` | 覆盖 profile（或直接指定实例） |
| `--password` | 密码（**不推荐**，会短暂出现在进程参数中；优先 `DB_PASSWORD` 环境变量或交互输入） |
| `--list-databases` | 列出实例全部数据库 |
| `--database DB` | 限定数据库（配合 `--list-tables` / `--search-field` 等） |
| `--list-tables` | 列出指定库全部表（需 `--database`） |
| `--table NAME` | 查字段；支持 `库.表` 精确或纯表名模糊（跨库自动定位） |
| `--search-table KW` | 按关键字模糊搜表名（跨库，输出 库.表+表注释） |
| `--search-field KW` | 按关键字模糊搜字段名（跨库，输出 库.表.字段+注释） |
| `--match-comment` | 与 `--search-field` 连用：同时匹配字段注释 |
| `--sample N` | `--table 库.表` 精确查询后附加数据样例条数（默认 1）；纯表名模糊查询不附带 |
| `--no-sample` | 关闭数据样例输出 |
| `--exclude-backup` | 搜索/列表默认过滤备份/回灌/临时表（bcp_/SYNC_ 前缀、_bak/_backup/_temp/_zj/_wq/_yq/_upd/纯数字日期后缀）；默认开 |
| `--no-exclude-backup` | 关闭备份表过滤（例：确认某备份表是否存在时） |
| `--max-rows N` | 搜索命中超过 N 条进入摘要模式：按表分组 TOP20 + 明细截断 + **完整结果落盘 /tmp**（默认 100） |
| `--full` | 搜索不截断（关闭摘要模式，输出全部明细） |
| `--json` | JSON 输出（样例并入 `sample` 结构化字段） |

### 1.3 输出示例（Markdown 表格）

```
$ query_schema.py --profile dys95 --table tradingdb.t_order_status
tradingdb.t_order_status (25 字段)
| 字段 | 类型 | 长度 | 键 | 允许空 | 注释 |
| --- | --- | --- | --- | --- | --- |
| ex_err_msg | varchar | 128 | | NO | 错误原因描述 |
| key_error_msg | varchar | 512 | | YES | 错误信息 |
| key_error_code | varchar | 64 | | YES | 错误代码串 |
| reject_reason_code | int | | | YES | 拒绝原因代码 |
| ord_rej_reason | varchar | 255 | | YES | 订单拒绝原因 |
...

📊 数据样例（1 条）：   ← 精确 库.表 查询默认自动附带，直观看到真实字段值
| 字段 | 值 |
| --- | --- |
| busidate | 20261105 |
| moneytype | RMB |
| nodeid | 0000 |
...
```

---

## 2. 凭据与安全（P0）

1. **凭据不落盘**：密码不写入任何脚本/配置/SKILL.md/记忆文件；host/port/user 属半公开信息可内置
   （profile），密码一律运行时提供（环境变量或交互输入）。
2. **向用户索取**：不知道用户名/密码时**直接询问用户**（「用户名：query / 密码：***」），
   不要猜、不要翻旧记录里的明文。
3. **有限权限**：本技能全部查询只读 `information_schema`（及必要的 `SHOW`），
   不执行 DDL/DML，不修改任何业务数据。
4. **结论口径**：数据库返回的是**最权威表结构**；当数据库与源码/文档冲突时以数据库为准，
   并在回复中注明「数据库直查结果」。

---

## 3. 库表分布速查（dys + jzqs，直查已核验）

### 3.1 dys 低延时 SIT

已核验的 dys（低延时 SIT）**20 个库**（17 业务库 + dbagent/heartbeat_info/recyclebin 3 个运维库）分布，完整清单见 `references/tables.md`。
速查：

| 主题 | 位置 | 说明 |
| --- | --- | --- |
| 委托主表 | `tradingdb.t_order` | 69 字段，无错误信息字段；`agw_seq_id` 业务流水号、`cl_ord_id` 报盘合同号、`json_data` 自定义属性 |
| 状态回报（**交易所错误信息**） | `tradingdb.t_order_status` | 25 字段；`ex_err_msg`(128) 错误原因描述、`key_error_msg`(512)+`key_error_code`、`reject_reason_code`/`ord_rej_reason` |
| 委托文件源表（**备注字段**） | `sourcedatadb.t_orderrec` | 96 字段；`remark`(32) 备注（存合约发生日期+合约流水号）、`bankfrzsno` 银行冻结流水号、`ordersno`+`orderdate` 主键 |
| 运维类委托表 | `operationdb` | 6 张 order 表（运维/审计） |
| 资金/证券/客户 | `basedb` | 103 张表，无委托表 |

> 查业务字段含义（如「备注」「错误原因」）优先 `--search-field <词> --match-comment` 跨库搜注释，
> 命中即为权威答案，无需再翻源码。

---

## 3.5 jzqs 集中清算 SIT 库表分布速查（2026-11-05 直查实测）

连接：`--profile jzqs_sit`（`10.187.109.56:2883`，user=`gjman_q@jjnode#jzqs_sit`，
**OceanBase 4.2.5.7 MySQL 协议，pymysql 直连兼容**；密码向用户索取不落盘）。
6 个业务库：`bak`(备份) / `comm`(公共) / `node`(★主业务库) / `oceanbase`(系统) / `sit56` / `test`。

| 主题 | 位置 | 说明 |
| --- | --- | --- |
| **集中清算委托表** | `node.node_orderrec` | **85 字段**；主键=`orderdate+ordersno+fundacct+nodeid`；`ordersno` 流水号、`secuid/stkcode`、`orderprice/qty`、`matchqty/matchamt/clearamt`、`creditfrzqty/creditfrzamt` 信用冻结、`credittype`、`remark`(128)、`netaddr` 渠道设备指纹、`operway` 委托方式 |
| 信用委托/还券 | `node.node_credit_orderrec` / `node.node_xyhg_orderrec` | 信用委托、信用还券（xyhg）类 |
| 负债表 | `node.node_creditdebts` | R2609160118 交叉验证已核验 |
| 费用表 | `node.node_creditfee` | 43 字段，`busidate+moneytype+settunit+fundunit+stkholdunit+nodeid` 主键 |
| 其他委托 | `node_bond_orderrec`(债券)、`node_hgt_orderrec`(港股通)、`node_closeorder`(撤单)、`node_frzorderrec`(冻结)、`cjs_orderrec`(网关) | node 库 204 张 order 匹配表 |

> ⚠️ **jzqs 搜字段坑（实测）**：`--search-field` LIKE 扫 columns **即使 `--database` 限定库也 60s 超时 2013**
> （node 库过大，OceanBase 下 queries 慢）；须用 `--table 库.表` 精确查（秒回）或 `--search-table`（扫 tables 量小）。
> 完整 6 库分布 + 字段级明细见 `references/tables.md`「jzqs」章节。

---

## 3.6 jzjy 集中交易 SIT 库表分布速查（SQL Server，2026-11-05 直查实测）

连接：`query_sqlserver.py --profile jzjy_sit`（`10.187.160.91:1433`，user=`rdonly`，数据库=`run`，
**Microsoft SQL Server 2014**；密码向用户索取不落盘）。⚠️ 仅 TDS 7.0 可用、仅 run 库可读（AT/his/sql 报 916 无权限）。

| 主题 | 位置 | 说明 |
| --- | --- | --- |
| **集中交易委托主表** | `run.dbo.orderrec` | **91 字段**；主键=`ordersno+orderdate+serverid`；`ordersno` 流水号、`orderid`(char10 客户合同号)、`orderprice`(numeric10,4)/`orderqty`/`matchqty/clearamt/matchamt`、`bsflag/inputbs/cancelflag/orderstatus`、`remark`(32)、`netaddr`(255 设备指纹)、`creditfrzqty/creditfrzamt` 信用冻结、`extamt1/extqty1/extkind1/extsecuid1` 扩展、`mkt_branchid/channel/crisklevel/passflag` |
| 信用/组合/VIP类委托 | `credorderrec` / `comborderrec` / `vip_orderrec` / `xyhg_orderrec` | 信用委托、组合委托、VIP 快速通道、信用还券 |
| 债券/港股通/北交所 | `bond_orderrec` / `pre_bondorderrec` / `hgt_orderrec` / `bjhgorderrec` | 债券、预债券、港股通、北交所 |
| 撤单/冻结 | `closeorder` / `frzorderrec` / `chkfrzorderrec` / `sgt_frzorderrec` | 撤单、冻结、冻结核查、融券冻结 |
| 隔夜/基金类 | `nightpreorderrec` / `oforderrec` | 夜市委托、基金委托 |
| 分区视图 | `v_*_in` 等 | 按交易节点分表的分区视图（`v_` 前缀） |
| 备份/回灌表（非核心，查询时过滤） | `bcp_*` 前缀 / `_bak`/`_zj`/`_out`/`_temp`/`_backup`/日期后缀 | BCP 回灌、备份、导出、临时表 |

> ⚠️ **run 库规模大**：10593 张表，`LIKE '%order%'` 命中 1037 张；脚本已默认 `--exclude-backup`
> 过滤 bcp_/SYNC_/备份/临时表（`--no-exclude-backup` 看全部）。定位核心表优先 `--table` 精确查。
> 完整字段明细见 `references/tables.md`「jzjy」章节。

**参数中心后台 SIT（cszx_sit）**：同一套 SQL Server 脚本；连接 `query_sqlserver.py --profile cszx_sit`
（`10.187.64.75:1433`，user=`jygl_zd`，数据库=`run`）。⚠️ 实例 5 库（his/run/run_cszx/sql/upgrade）中**仅 run 库可读**
（run_cszx/his 等报 18456 登录失败 · 实测）；run 库=**参数业务库**（1043 张表，**区别于 jzjy 交易实例的同名 run 库**）。
核心表：`paramcfg`（12 字段，主键 `paramid+serverid` 参数主表）、`paramroutecfg`（6 字段，主键 `nodeid+paramid+serverid+systemid` 参数路由）；
主题分布 `param` 59 张 / `cfg` 17 张 / `rule` 5 张。定位优先 `--search-table param` / `--table paramcfg`。
完整明细见 `references/tables.md`「cszx」章节。

---

## 3.7 GOTCHAS 速查表（踩坑清单 · 2026-11-05 实测固化）

| # | 场景 | 坑 | 对策 |
| --- | --- | --- | --- |
| 1 | dbx MCP 查 dys95 | 内置凭据四通道全 1045（服务端拒旧口令） | 直接走 D2 pymysql 直连，向用户索取口令；勿反复试 dbx |
| 2 | Python 环境 | 默认 workbuddy python 无 pymysql；/usr/local python 无 pymssql 且 PEP 668 拦截 | MySQL/OceanBase → `/usr/local/bin/python3`；SQL Server → workbuddy python 3.13.12（自带 pymssql） |
| 3 | pymssql 连 SQL Server | TDS 7.1~8.0 报 20002 连接失败 | `tds_version='7.0'`（脚本已内置，勿改） |
| 4 | pymysql 连 SQL Server | 协议不同，TCP 可达但报 Connection reset by peer | 判定为 SQL Server 必须用 query_sqlserver.py（pymssql） |
| 5 | rdonly 权限 | AT/his/sql 库报 916 无权限；只能读 run 库 | 业务查询限定 run 库；跨库手写 SQL 须 `[db].INFORMATION_SCHEMA` 三段限定 |
| 6 | INFORMATION_SCHEMA 空结果 | 视图仅反映连接当前库，连 master 查 run 表得 0 字段 | 连接 database=run，或三段限定跨库 |
| 7 | jzqs 搜字段 | `--search-field` LIKE 扫 columns 必 60s 超时 2013（node 库过大） | 用 `--table 库.表` 精确查或 `--search-table`（扫 tables 量小）；勿再全库扫字段 |
| 8 | MySQL 8 information_schema | 列名大小写混杂（schemata.SCHEMA_NAME 大写 / columns.table_schema 小写） | 脚本已统一小写化处理，无需干预 |
| 9 | run 库搜索噪音 | 10593 张表，`%order%` 命中 1037，SYNC_*/bcp_*/备份表刷屏 | 脚本默认 `--exclude-backup` 过滤；定位核心表用 `--table` 精确查 |
| 10 | 海量命中刷屏 | `--search-field err` 命中 1760 字段 | 默认 `--max-rows 100` 自动摘要（按表分组 TOP20 + 明细截断 + 完整结果落盘 /tmp）；`--full` 看全部 |
| 11 | 密码安全 | 密码落盘=红线 | 一律运行时提供：`DB_PASSWORD` 环境变量 > `--password` > 交互输入；永不写入脚本/配置/记忆 |
| 12 | SQL Server 列注释 | sys.extended_properties 无 MS_Description 记载（实测为空） | 列注释检索在 SQL Server 无意义，靠字段名/字典表（如 marketerrmsg）理解语义 |
| 13 | cszx 库权限 | 参数中心实例（10.187.64.75）5 库仅 run 可读，run_cszx/his/sql/upgrade 报 18456 登录失败 | 参数查询限定 run 库；run_cszx 无权限勿依赖；与 jzjy 实例同名 run/his/sql 不可混用（交易 vs 参数） |

---

## 4. 目录结构

```
数据库查询/
├── SKILL.md
├── scripts/
│   ├── dbq                        # ★ 统一启动器（按 profile 自动选脚本+python；已 chmod +x）
│   ├── query_schema.py            # ★ MySQL/OceanBase 查询脚本（列库/列表/表字段/关键字搜索/样例）
│   └── query_sqlserver.py         # ★ SQL Server 查询脚本（pymssql·TDS 7.0，profile jzjy_sit）
└── references/
    └── tables.md                  # dys 低延时 + jzqs 集中清算 + jzjy 集中交易 + cszx 参数中心 库表分布速查（直查已核验）
```

**约定**：脚本全部自包含于本 SKILL 目录，只读元数据视图（`information_schema` / `sys.*` / `sys.extended_properties`），
不执行 DDL/DML；MySQL/OceanBase 用 `/usr/local/bin/python3`、SQL Server 用 workbuddy python 3.13.12 运行；`assets/` 无内容已删除。
