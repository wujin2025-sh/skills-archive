# dys 低延时库表分布参考（数据库直查已核验 · 2026-11-05）

> 数据来源：`information_schema` 直查（`10.187.101.51:8885` user=query，低延时 SIT）。
> ⚠️ **密码不在此记录**，运行时向用户索取；连接信息仅 host/port/user 半公开项。
> 表分布可能随版本演进，**以数据库实时查询为权威**，本文件仅作“去哪查”的导航。

## 实例连接

| 项 | 值 |
| --- | --- |
| host | `10.187.101.51` |
| port | `8885` |
| user | `query` |
| password | ❌ 不落盘，向用户索取 |
| 通道 | dys-95 四通道均被 dbx 内置凭据 1045 拒绝（2026-11-05 实测），须 pymysql 直连 |
| 服务器 | MySQL 8.x（information_schema 列名大小写混杂：`schemata.SCHEMA_NAME` 大写 / `columns.table_schema` 小写，脚本已统一小写化处理） |

## 20 个库（17 业务库 + 3 运维库）

**业务库**：`appconfigdb, basedb, bosgwdb, cachedatadb, dkdb, dpdb, drdb, exportdb,
historydb, importdb, mddb, operationdb, paramflowdb, sourcedatadb, tradingconfigdb,
tradingdb, userdb`

**运维/系统库**：`dbagent`(库迁移代理)、`heartbeat_info`(心跳)、`recyclebin`(回收站)

## 委托/订单相关表分布（核心）

| 库 | 表 | 字段数 | 用途 | 关键字段 |
| --- | --- | --- | --- | --- |
| `tradingdb` | `t_order` | 69 | **委托主表**（无错误信息字段） | `agw_seq_id` 业务流水号(全局唯一)、`cl_ord_id` 报盘合同号、`cl_ord_no` 客户合同号、`security_id` 合约编码、`order_qty/price`、`json_data`(varchar 4000 订单自定义属性)、`bsflag`、`credit_type`、`sale_repay_source` 卖券还款来源 |
| `tradingdb` | `t_order_status` | 25 | **状态回报表 ← 交易所错误信息所在** | `ex_err_msg`(varchar128)=**错误原因描述**、`key_error_msg`(512) 错误信息、`key_error_code`(64) 错误代码串、`reject_reason_code`(int) 拒绝原因代码、`ord_rej_reason`(255) 订单拒绝原因 |
| `sourcedatadb` | `t_orderrec` | 96 | **委托记录/文件接口源表 ← 备注字段所在** | `remark`(varchar32)=备注（存合约发生日期+合约流水号）、`bankfrzsno`(32) 银行冻结流水号、`extkind1`(char1) 预留（信用卖券还款区分 R/P/Q）、`ordersno`+`orderdate` 主键 |
| `operationdb` | `t_order_*` 等 | — | 运维/审计类委托表（共 6 张 order 表） | 按需直查 |

## 其他库主题（导航）

| 库 | 主题 |
| --- | --- |
| `basedb` | 资金/证券/客户类（103 张表，**无委托表**） |
| `tradingdb` | 委托交易库（33 张 order 相关表） |
| `sourcedatadb` | 文件接口源表（9 张 order 表） |
| `tradingconfigdb` | 交易配置 |
| `paramflowdb` | 参数流 |
| `historydb / exportdb / importdb` | 历史 / 导出 / 导入 |
| `cachedatadb / mddb / dpdb / drdb / dkdb` | 缓存 / 行情 / 数据处理类 |

## 常用查询 SQL（手查模板）

```sql
-- 全部库
SELECT schema_name FROM information_schema.schemata
WHERE schema_name NOT IN ('information_schema','performance_schema','mysql','sys') ORDER BY 1;

-- 某库全部表（含注释）
SELECT table_name, table_comment FROM information_schema.tables
WHERE table_schema='tradingdb' AND table_type='BASE TABLE' ORDER BY 1;

-- 表字段（名称/类型/长度/键/可空/注释）
SELECT column_name, data_type, character_maximum_length, column_key,
       is_nullable, column_comment
FROM information_schema.columns
WHERE table_schema='tradingdb' AND table_name='t_order'
ORDER BY ordinal_position;

-- 关键字跨库搜字段注释（业务含义定位）
SELECT table_schema, table_name, column_name, column_comment
FROM information_schema.columns
WHERE column_name LIKE '%remark%' OR column_comment LIKE '%备注%'
ORDER BY table_schema, table_name;
```

## 业务映射速查（R2609160118 等已核验结论）

| 业务口径 | 落库位置 |
| --- | --- |
| 前端「备注字段」（合约发生日期+合约流水号） | `sourcedatadb.t_orderrec.remark` |
| 「交易所错误信息」 | `tradingdb.t_order_status.ex_err_msg`（错误原因描述 128） |

---

# jzqs 集中清算 SIT 库表分布参考（数据库直查已核验 · 2026-11-05）

> 数据来源：`information_schema` 直查（`10.187.109.56:2883` user=`gjman_q@jjnode#jzqs_sit`，集中清算 SIT）。
> ⚠️ **密码不在此记录**，运行时向用户索取；连接信息仅 host/port/user 半公开项。
> 服务器：OceanBase 4.2.5.7（**MySQL 协议，pymysql 直连兼容，实测通过**）。

## 实例连接

| 项 | 值 |
| --- | --- |
| host | `10.187.109.56` |
| port | `2883` |
| user | `gjman_q@jjnode#jzqs_sit`（含 `@`/`#`，须整体作字符串传入） |
| password | ❌ 不落盘，向用户索取 |
| profile | `query_schema.py --profile jzqs_sit`（已固化 2026-11-05） |

## 6 个业务库

`bak`(备份/历史快照), `comm`(公共), `node`(★主业务库), `oceanbase`(系统), `sit56`(测试), `test`(测试)

## node 库委托/订单相关表（核心，2026-11-05 实测）

**集中清算委托表 = `node.node_orderrec`（85 字段）**，主键 = `orderdate + ordersno + fundacct + nodeid`
关键字段：`ordersno` 流水号、`fundacct` 资金账号、`secuid/stkcode/stkname`、`orderprice/orderqty`、
`matchqty/matchamt/clearamt`(清算金额 19,2)、`orderfrzamt` 委托冻结、`creditfrzqty/creditfrzamt` 信用冻结、
`fundmarginfrz/funddebtsfrz`、`credittype`(char1)、`bsflag/trdbsflag/inputbs`、`orderstatus`(char1)、
`remark`(varchar128)、`extqty1/extamt1/extkind1/extsecuid1` 扩展、`nodeid`(varchar4 节点号)、`operwayext`、`userinfo`

其他委托/订单表（可见 204 张 order 匹配表，主要位于 node 库）：
- 信用类：`node_credit_orderrec`、`node_xyhg_orderrec`(信用还券)、`node_hgt_orderrec`(港股通)
- 网关/文件：`cjs_orderrec`、`cjs_credit_orderrec`、`cjs_closeorder`、`cjs_dzjypreorder`
- 低延时映射：`dys_orderrec`、`dys_bond_orderrec`、`dys_commfo_order`、`dysgs_order`
- 其他：`node_bond_orderrec`(债券)、`node_closeorder`、`node_oforder`(成交回报)、`node_frzorderrec`(冻结)

## 负债/费用表（R2609160118 交叉验证已核验）

| 表 | 用途 |
| --- | --- |
| `node_creditdebts` | 负债表 |
| `node_creditfee` | 费用表 |

## 常用查询 SQL（与 dys 相同模板，替换 schema/table 名即可）

```sql
-- node 库全部表
SELECT table_name, table_comment FROM information_schema.tables
WHERE table_schema='node' AND table_type='BASE TABLE' ORDER BY 1;

-- node_orderrec 字段
SELECT column_name, data_type, character_maximum_length, column_key,
       is_nullable, column_comment
FROM information_schema.columns
WHERE table_schema='node' AND table_name='node_orderrec'
ORDER BY ordinal_position;
```

> 新结论或表结构变更后，请回写本文件；表分布导航类信息价值大于一次查询结果。

---

# jzjy 集中交易 SIT 库表分布参考（SQL Server · 2026-11-05）

> 数据来源：`sys.*` / `INFORMATION_SCHEMA` 直查（`10.187.160.91:1433` user=`rdonly` database=`run`，集中交易 SIT）。
> ⚠️ **密码不在此记录**，运行时向用户索取；连接信息仅 host/port/user/database 半公开项。
> 服务器：**Microsoft SQL Server 2014 (12.0.4100.1 X64)**；pymssql 驱动，**仅 TDS 7.0 可用**（7.1~8.0 报 20002 连接失败）。

## 实例连接

| 项 | 值 |
| --- | --- |
| host | `10.187.160.91` |
| port | `1433` |
| user | `rdonly` |
| 默认库 | `run`（rdonly **仅 run 库可读**，AT/his/sql 报 916 无权限） |
| password | ❌ 不落盘，向用户索取 |
| profile | `query_sqlserver.py --profile jzjy_sit`（已固化 2026-11-05） |
| 运行 | `~/.workbuddy/binaries/python/versions/3.13.12/bin/python3`（自带 pymssql 2.4.6；TDS 版本必须 7.0） |

## 4 个业务库

`AT`（rdonly 不可读）、`his`（历史，不可读）、`run`（★主业务库）、`sql`（不可读）
（另有 master/model/msdb/tempdb 系统库）

## run 库委托/订单相关表（核心，2026-11-05 实测）

**集中交易委托主表 = `run.dbo.orderrec`（91 字段）**，主键 = `ordersno + orderdate + serverid`
关键字段：`ordersno` 流水号、`orderdate`(如 20261105)、`serverid` 节点、`orderid`(char10 客户合同号，如 1100001VAI)、
`custid/custname`、`secuid/rptsecuid/market/seat/stkcode/stkname`、`orderprice`(numeric10,4)/`orderqty`(bigint)、
`fundavl/matchqty/cancelqty/tradefee/orderfrzamt/clearamt`(19,2)/`matchamt`、`ordertype/nightflag`(隔夜)、
`bsflag`(char2 买卖+币种)、`inputbs/cancelflag/combtype/orderstatus/sourcetype`、`bankcode/bankorderid/bankid/bankfrzsno`、
`netaddr`(varchar255 设备指纹，PC;IIP=140.207.161.125;...)、`operway`(如 F)、`remark`(varchar32)、
`creditfrzqty/creditfrzamt/fundmarginfrz/funddebtsfrz/credittype/creditdigestid`、`extamt1/extqty1/extkind1/extkind2/extsecuid1/extchar32` 扩展、
`mkt_branchid/channel/crisklevel/criskkind/prisklevel/passflag/ctrlkinds/outbizsno/protocolver/protocolno1/protocolno2/doublevideo/extstr1/extstr2/extint1/extint2/operwayext/userinfo`

其他委托/订单表（run 库 10593 张表，`%order%` 命中 1037，过滤备份/回灌后核心 751 张）：
- 信用类：`credorderrec`、`xyhg_orderrec`(信用还券)、`comborderrec`(组合)、`vip_orderrec`(VIP 快速通道)
- 债券类：`bond_orderrec`、`pre_bondorderrec`(预债券)
- 港股通/北交所：`hgt_orderrec`、`bjhgorderrec`
- 撤单/冻结：`closeorder`、`frzorderrec`、`chkfrzorderrec`、`sgt_frzorderrec`
- 隔夜/基金：`nightpreorderrec`(夜市委托)、`oforderrec`(基金委托)
- 分区视图：`v_*_in`（按交易节点分表）

## 交易所错误信息字段（2026-11-05 直查实测）

集中交易主委托表 **`orderrec` 不存错误信息**（91 字段无 err 相关字段）；交易所错误信息按业务场景分布如下：

| 场景/表 | 字段 | 类型 | 说明 |
| --- | --- | --- | --- |
| **交易所错误码→中文文案字典** | `marketerrmsg` | `marketerrmsg` varchar64 / `syserrmsg` varchar16 | 主键=`channel+market+marketcode+serverid`；样例 marketcode=0 →「委托合法」；前端/柜台按 市场+错误码 关联翻译展示（等价低延时 `t_order_status.ex_err_msg`） |
| 主委托表 | `orderrec` | — | **无错误信息字段**（只有 orderstatus 状态位） |
| 债券委托 | `bond_orderrec` / `vip_bond_orderrec` / `localbondorderrec` | `errmsg` varchar64/255 | 直接存错误文案 |
| 信用还券 | `xyhg_orderrec` / `vip_xyhg_orderrec` | `errmsg` varchar64 | 直接存错误文案 |
| 冻结委托 | `frzorderrec` / `rollfrzorderrec` | `errmsg` varchar255 | 直接存错误文案 |
| 北交所/股份 | `bjhg_orderrec_sz` / `fjybs_orderrec` | `errmsg` varchar255 | 直接存错误文案 |
| 快速输出表（拒单原因码） | `orderrec{85/88/95/96/98}_fast_out` / `hgt_orderrec{节点}_fast_out` | `reject_reason_code` int | 拒绝原因码（与低延时 `t_order_status.reject_reason_code` 同源） |
| OF 基金/理财委托 | `of_order` | `errinfo` varchar32 | OF 系统委托错误信息；配套 `oferrmsg`/`ofmatch`（errcode char4 + errmsg varchar255/128） |
| E-投票表决 | `evotereport` | `rejectreason` int | 表决委托拒绝原因 |

> **跨系统对照**：dys 低延时 `t_order_status.ex_err_msg`(128)/`key_error_msg` ≈ jzjy `marketerrmsg.marketerrmsg`(64) + 细分表 `errmsg`；
> `reject_reason_code` 两套（dys `t_order_status`、jzjy `*_fast_out`）命名同源。

## 表命名规律（--exclude-backup 默认过滤规则 · 两脚本已内置）

| 前缀/后缀 | 含义 | 默认过滤 |
| --- | --- | --- |
| `bcp_` / `SYNC_` 前缀 | BCP 回灌表 / 同步表 | ✅ |
| `_bak` / `_backup` / `_temp` / `_zj` / `_wq` / `_yq` / `_upd` 子串 | 备份/临时/回切历史测试表 | ✅ |
| 纯数字日期/批次后缀（`_20240301`、`_326`） | 备份/批次表 | ✅ |
| `v_` 前缀 | 分区视图（按交易节点分表） | ❌ 保留（业务可查） |
| `*_fast_out` / `*_jzqs_out` | 快速输出表 / 跨系统输出表（**含 reject_reason_code 等业务字段**） | ❌ 保留（勿误伤，见「错误信息」节） |
| `_out` 后缀 | 含义不统一（可能业务也可能导出） | ❌ 不默认过滤，按需人工判断 |

> 搜索/列表现已默认走 `--exclude-backup`（命中超过 `--max-rows 100` 自动摘要+落盘 /tmp）；
> `--no-exclude-backup` 看全部、`--full` 关闭截断。

## 常用查询 SQL（手查模板）

```sql
-- 列库（sys.databases，database_id>4 排除系统库）
SELECT name FROM sys.databases WHERE database_id > 4 ORDER BY name;

-- 列 run 库全部表
SELECT name, create_date FROM [run].sys.tables WHERE is_ms_shipped=0 ORDER BY name;

-- 表字段（跨库须三段限定 [db].INFORMATION_SCHEMA）
SELECT c.TABLE_SCHEMA, c.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE,
       c.CHARACTER_MAXIMUM_LENGTH, c.NUMERIC_PRECISION, c.NUMERIC_SCALE,
       c.IS_NULLABLE, c.ORDINAL_POSITION
FROM [run].INFORMATION_SCHEMA.COLUMNS c
WHERE c.TABLE_SCHEMA='dbo' AND c.TABLE_NAME='orderrec' ORDER BY c.ORDINAL_POSITION;

-- 主键
SELECT kcu.COLUMN_NAME FROM [run].INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
JOIN [run].INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
  ON kcu.CONSTRAINT_NAME=tc.CONSTRAINT_NAME AND kcu.TABLE_NAME=tc.TABLE_NAME
WHERE kcu.TABLE_SCHEMA='dbo' AND kcu.TABLE_NAME='orderrec' AND tc.CONSTRAINT_TYPE='PRIMARY KEY';

-- 数据样例（SQL Server 无 LIMIT，用 SELECT TOP n）
SELECT TOP 1 * FROM [run].[dbo].[orderrec];
```

> ⚠️ **注意**：`INFORMATION_SCHEMA`/`sys` 视图仅反映**连接当前库**（本工具连接已固定 database=run）；
> 手写 SQL 跨库必须 `[db].INFORMATION_SCHEMA.COLUMNS` 三段限定；连接默认库不对会查到 0 字段（实测坑）。
> 新结论或表结构变更后，请回写本文件；表分布导航类信息价值大于一次查询结果。

---

# cszx 参数中心后台 SIT 库表分布参考（SQL Server · 2026-11-05）

> 数据来源：`sys.*` / `INFORMATION_SCHEMA` 直查（`10.187.64.75:1433` user=`jygl_zd` database=`run`，参数中心后台 SIT）。
> ⚠️ **密码不在此记录**，运行时向用户索取；连接信息仅 host/port/user/database 半公开项。
> 服务器：**Microsoft SQL Server**；pymssql 驱动，**仅 TDS 7.0 可用**（7.1~8.0 报 20002 连接失败，与 jzjy 同）。

## 实例连接

| 项 | 值 |
| --- | --- |
| host | `10.187.64.75` |
| port | `1433` |
| user | `jygl_zd` |
| 默认库 | `run`（**实例 5 库中仅 run 可读**，run_cszx/his/sql/upgrade 报 18456 登录失败 · 实测） |
| password | ❌ 不落盘，向用户索取 |
| profile | `query_sqlserver.py --profile cszx_sit`（已固化 2026-11-05） |
| 运行 | `~/.workbuddy/binaries/python/versions/3.13.12/bin/python3`（自带 pymssql 2.4.6；TDS 版本必须 7.0） |

## 5 个业务库

`his`（不可读）、`run`（★主业务库=参数业务库）、`run_cszx`（不可读）、`sql`（不可读）、`upgrade`（不可读）
（另有 master/model/msdb/tempdb 系统库；run_cszx 疑为参数中心独立库但 jygl_zd 无权限）

> ⚠️ **与 jzjy 实例库名混淆警示**：jzjy 集中交易实例（10.187.160.91）**同样有 `run/his/sql` 库**，
> 但那是交易实例（run 库 10593 张交易表）；cszx 参数中心实例（10.187.64.75）的 run 库是**参数业务库**（1043 张表）。
> 两实例查询必须带 profile 区分，**勿按库名混用**。

## run 库参数类表（核心，2026-11-05 实测）

**run 库共 1043 张表**，主题分布：`param` 59 张 / `cfg` 17 张 / `rule` 5 张。

| 表 | 字段数 | 主键 | 用途/关键字段 |
| --- | --- | --- | --- |
| `paramcfg` | 12 | `paramid + serverid` | **参数主表**；`serverid` int / `paramid` varchar32 / `paramname` varchar255 / `paramkind` char1 / `funcdetail` char1 / `allowsetflag` char1 / `allowsetkinds` varchar32 / `timeout` int / `begintime1/endtime1/begintime2/endtime2` int |
| `paramroutecfg` | 6 | `nodeid + paramid + serverid + systemid` | **参数路由配置**；`paramid` varchar32 / `systemid` varchar32 / `nodeid` varchar32 / `upddate` int / `updatetime` int |

相关表清单：
- `param` 主题 59 张：`bondtradparams`（债券交易参数）、`creditalertparam`（信用预警参数）、`creditmixparam`（信用混用参数）等
- `cfg` 主题 17 张：`busiflowcfg`（业务流程）、`cleardaycfg`（清算日）、`etfbusicfg`（ETF 业务）、`paramcfg`/`paramcfgexter`/`paramroutecfg` 及多张日期后缀备份表
- `rule` 主题 5 张：`dynamicrule`、`paramrouterule`、`ruleinfo`、`ruleinfo_fastout`、`unitcalrule`

> 定位参数表优先 `dbq cszx_sit --search-table param` 精确查；导航类结论变更后请回写本文件。

---

# 系统连接与核心表横向对照（2026-11-05 直查实测）

> 跨系统查同一业务（委托/错误信息/备注/信用类）时优先对照本表定位；未核验项标注「待核」，不臆造表名。

## 实例一览

| 系统 | profile | 引擎 | 连接（host:port user） | 脚本 + python |
| --- | --- | --- | --- | --- |
| dys 低延时 SIT | `dys95` | MySQL 8 | 10.187.101.51:8885 query | query_schema.py + /usr/local/bin/python3 |
| jzqs 集中清算 SIT | `jzqs_sit` | OceanBase 4.2.5.7 | 10.187.109.56:2883 gjman_q@jjnode#jzqs_sit | query_schema.py + /usr/local/bin/python3 |
| jzjy 集中交易 SIT | `jzjy_sit` | SQL Server 2014 | 10.187.160.91:1433 rdonly(database=run) | query_sqlserver.py + workbuddy python3 · TDS 7.0 |
| cszx 参数中心 SIT | `cszx_sit` | SQL Server | 10.187.64.75:1433 jygl_zd(database=run) | query_sqlserver.py + workbuddy python3 · TDS 7.0 |

> cszx 为**参数业务库**（无委托交易表），核心表 `paramcfg`/`paramroutecfg` 见上文「cszx」章节；勿与 jzjy 实例的 run/his/sql 库名混淆。

> 全部 profile 密码运行时提供（DB_PASSWORD / 交互输入），**永不落盘**；最快入口 `dbq <profile> <args>`。

## 委托主表 / 主键 / 错误信息 / 备注

| 业务口径 | dys（低延时） | jzqs（集中清算） | jzjy（集中交易） |
| --- | --- | --- | --- |
| 委托主表 | `tradingdb.t_order`（69 字段） | `node.node_orderrec`（85 字段） | `run.dbo.orderrec`（91 字段） |
| 主键 | `agw_seq_id` 业务流水号（全局唯一） | `orderdate+ordersno+fundacct+nodeid` | `ordersno+orderdate+serverid` |
| 客户合同号 | `cl_ord_no` | —（待核） | `orderid`(char10，如 1100001VAI) |
| **交易所错误信息** | `t_order_status.ex_err_msg`(128) + `key_error_msg`(512) + `reject_reason_code`(int) | 细分表/字典（待核） | 主表**无**；字典 `marketerrmsg`（marketerrmsg varchar64 / syserrmsg varchar16，主键 channel+market+marketcode+serverid）翻译展示；细分表自带 `errmsg`（债券/信用还券 64、冻结/北交所 255）；`*_fast_out.reject_reason_code`；OF 基金 `of_order.errinfo` |
| 委托备注 | `sourcedatadb.t_orderrec.remark`(32) | `remark`(128) | `remark`(32) |
| 成交回报 | —（待核） | `node_oforder` | `ofmatch`(基金) / 主成交表（待核） |

## 各系统专属重点表（已核验）

| 系统 | 表 | 说明 |
| --- | --- | --- |
| dys | `t_order_status` | 25 字段，状态回报 ← 查错误信息优先 |
| dys | `sourcedatadb.t_orderrec` | 96 字段，文件接口源表（备注字段所在） |
| jzqs | `node_creditdebts` / `node_creditfee` | 负债表 / 费用表（R2609160118 交叉核验） |
| jzqs | `node_credit_orderrec` / `node_xyhg_orderrec` / `node_hgt_orderrec` | 信用委托 / 信用还券 / 港股通 |
| jzjy | `credorderrec` / `xyhg_orderrec` / `comborderrec` / `vip_orderrec` | 信用委托 / 信用还券 / 组合 / VIP 快速通道 |
| jzjy | `bond_orderrec` / `hgt_orderrec` / `bjhgorderrec` | 债券 / 港股通 / 北交所委托 |
| jzjy | `closeorder` / `frzorderrec` / `chkfrzorderrec` / `sgt_frzorderrec` | 撤单 / 冻结 / 冻结核查 / 融券冻结 |
| jzjy | `of_order` / `oferrmsg` / `ofmatch` | OF 基金委托 / 错误信息 / 成交 |
| jzjy | `marketerrmsg` | **交易所错误码→中文文案字典**（前端/柜台翻译展示） |

## 查询技巧对照

| 目标 | 推荐命令 |
| --- | --- |
| 委托主表字段 | `dbq dys95 --table tradingdb.t_order` / `dbq jzqs_sit --table node.node_orderrec` / `dbq jzjy_sit --table run.dbo.orderrec` |
| 按字段名搜（dys/jzjy 可全库，**jzqs 禁止**） | `dbq dys95 --search-field remark --match-comment` / `dbq jzjy_sit --search-field err` |
| jzqs 定位表（避免扫字段超时） | `dbq jzqs_sit --search-table order` |
| 找错误信息字段 | dys → `t_order_status.ex_err_msg`；jzjy → 字典 `marketerrmsg` + 细分表 `errmsg` + `*_fast_out.reject_reason_code` + `of_order.errinfo` |
| cszx 参数表定位 | `dbq cszx_sit --table paramcfg`（参数主表 12 字段）/ `dbq cszx_sit --search-table param`（59 张参数表） |
