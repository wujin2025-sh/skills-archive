---
name: biz-logic-query
description: '业务逻辑智能问答 + 证据链工具：将业务/产品/测试人员提出的业务问题（如"这笔业务系统怎么处理""某接口承载什么""改动某函数影响谁"），转化为带证据链的可追溯结论——一句话答案 + 证据出处表 + 可信度分级 + 影响范围提示。复用 ba-to-dev 三域检索权威源（接口库/代码图谱/数据库/需求反查），结论有据可查、非模型猜测。Triggers: 业务规则查询、系统怎么处理这笔业务、接口查询、证据链、查某功能实现、影响范围、业务逻辑问答、biz-logic-query、/bizqa、这是哪个接口。'
disable: false
---

# Biz-Logic-Query: 业务逻辑智能问答 + 证据链

> **角色**：面向业务/产品/测试人员的**业务逻辑解析助手**
> **目标**：把"系统实际如何处理某笔业务"转译为**带证据链、可追溯、非猜测**的问答结论。

> 📍 **单源维护**：本技能主体唯一维护源为 `~/.workbuddy/skills/biz-logic-query/`（AI能力中心及 WorkBuddy 的 `~/.chat/skills/` 均经硬链接/软链接指向此处）。**只在此改**，一处生效、全 agent 可用。

---

## 🎯 适用场景（痛点定位）

| 场景 | 用户疑问示例 |
| :--- | :--- |
| 复杂需求分析 | 系统现在是怎么实现这个功能的？数据链路走哪？ |
| 日常业务处理 | 这笔业务在系统里具体怎么处理？走哪个接口/模块？ |
| 排查问题 | 这个函数被哪些模块调用？改动它会波及哪些系统？ |
| 接口核对 | 功能号 7300780 是什么接口？承载哪些字段？ |

**核心价值**：不是"猜"，而是**每条结论都带可追溯证据**（接口库实证 / 源码行号 / 需求原文 / 图谱索引），并显式标注可信度与"待确认"缺口。

---

## ⚡ 触发词 / 调用方式

- `/bizqa "业务问题"` / `/biz-logic-query "业务问题"` 或直接自然语言描述；
- 输入可为：**业务中文概念**（如 `指定合约还款`）、**功能号/文件号**（如 `7300780` / `Q23`）、**接口名**（如 `自研资金查询`）、**代码函数名**（如 `RepayContractDebets`）。

---

## 🔧 核心命令（v2 并行加速版）

```bash
P=/Users/wujin/.chat/runtimes/darwin-x64/python/versions/3.13.12/bin/python3
S=/Users/wujin/.workbuddy/skills/biz-logic-query/scripts/biz_logic_query.py

# 1) 业务概念全域检索（默认五域并行，自动多域 jzjy/dys/jzqs）
$P $S "指定合约还款" --all --timings

# 2) 只要接口 + 需求规则（最快；热缓存约 0.01s）
$P $S "指定合约还款" --fast

# 3) 功能号 / 英文函数名精查（ASCII 标识符自动走精准检索）
$P $S "7300780" --code
$P $S "RepayContractDebets" --all --project jzqs --trace

# 4) 缓存脏了强制重查 / 清缓存 / 证据不截断 / 结构化输出
$P $S "担保品返还" --all --refresh --verbose --json

# 5) L3 数据库实证：表结构 / 直查字典值（注意字典表真名）
$P $S "orderrec" --db-table run.dbo.orderrec --project jzjy
$P $S "信用账户余额" --db-sql "SELECT dictitem,subitem,subitemname FROM run.dbo.dictvalue WHERE subitemname LIKE N'%还款%'" --project jzjy

# 6) 单域 / 自定义多域 / 关闭部分域
$P $S "担保品划转" --project dys
$P $S "担保品划转" --projects jzjy,dys --no-rule

# 7) 订阅矩阵库：文件编号 → 消费者（L1.5 已自动联动，也可单独查）
$P $S "A37 大宗交易预委托记录信息" --no-db --no-rule   # 证据链自动带出「订阅矩阵」行
M=/Users/wujin/.workbuddy/skills/biz-logic-query/scripts/subscription_matrix.py
$P $M build                              # xlsx 更新后重建数据库
$P $M query A37                          # 消费者 + 跨源实证证据
$P $M consumer "低延时交易系统(虚拟)"     # 反查某系统订阅了哪些文件
$P $M stats                              # 全量总览
$P $M sql "SELECT * FROM v_a37_consumers" # 自由 SQL
```

参数速查：
| 参数 | 作用 | 默认 |
| :--- | :--- | :--- |
| `question`（位置参数） | 业务问题 / 功能号 / 英文函数名 | 必填 |
| `--all` | 全域检索（保留兼容；**默认就是全域**） | 开 |
| `--fast` | 仅 L1 接口库 + L4 业务规则，跳过 L0/L2/L3 | 关 |
| `--project` | 单域（`jzjy`/`dys`/`jzqs`/`cszx`/`grc`），覆盖默认多域 | 无 |
| `--projects` | 自定义多域，逗号分隔 | `jzjy,dys,jzqs` |
| `--code` | 按功能号/文件号查接口并触代码图谱 | 关 |
| `--trace` | 额外跑 `trace_path` 影响范围（默认关闭以提速） | 关 |
| `--db-table / --db-search-table / --db-sql` | **[L3]** 表结构 / 搜表 / 直查 SQL | 无 |
| `--no-db` / `--no-rule` | 关闭 L3 / L4 | 关 |
| `--verbose` | 证据摘要不截断（默认 600 字符）+ 跑备选词检索 | 关 |
| `--timings` / `--quiet` | 打印各域耗时明细 / 完全不打印耗时 | 关 |
| `--refresh` / `--clear-cache` | 忽略缓存强制重查 / 清空缓存 | 关 |
| `--cbm-timeout N` | 单域代码图谱超时秒数 | `12` |
| `--no-clarify` | 不生成澄清建议 | 关 |
| `--json` | 结构化 JSON（含 `timings`/`cache_hits`/`keywords`/`clarification`） | 关 |

> 缓存位置：`~/.workbuddy/skills/biz-logic-query/.cache/`。TTL：图谱/表结构 24h、需求反查 1h、业务规则 6h；`--db-sql` 不缓存。数据源更新后请 `--refresh`。

退出码：`0`=有证据结论；`2`=熔断未命中；`10`=本地资源不可用。

---

## 🔎 证据链可信度分级（P0 铁律）

> 三态定义、权威来源与诚实原则**统一见文末「🔗 共性规范基线 · 证据可信度三态与诚实原则」**（`_shared/SHARED.md` 的 `evidence_grading` 块，与 `ba-to-dev` P0#22 同源，两技能判定口径必须一致）。
> 本技能落点：`--json` 的 `evidence[*].confidence` 列 + 结论段「仍待确认」清单；脚本 `CONF_*` 常量与共享三态一一对应。**新增证据来源或调整分级口径时先改 SHARED.md 再 `apply`**，不得只改本技能。

---

## ⚙️ 底层复用（不重造检索核心）

> 权威源路径、`dbq` profile、CBM 项目名、字典表真名、DB-First 优先级**统一见文末「🔗 共性规范基线 · 权威源注册表」**。本节只列本技能 v2 特有执行方式。

| 域 | v2 调用方式 | 特有参数 / 剪枝 |
| :--- | :--- | :--- |
| L0 | `demand_dep_find.py` 并行任务 | 缓存 1h；命中本地 MD 直接作 🟢 证据，输出清洗固定模板头 |
| L1 | `.interface_store.db` 同步查询 | `FILE_CODE_TOKEN` 编号精确回退；`query_interface_family()` 同族扩展 |
| L1.5 | `.subscription_matrix.db` 只读 | 命中文件编号自动附加消费者证据（库不存在静默跳过） |
| L2 | CBM `search_code` 主域 / `search_graph` 辅域 | `--path-filter`、按系统域关键词覆盖、辅域 8s 上限、缓存 24h |
| L3 | `dbq <profile>` | 中文概念 → **表名词**映射（非字段名）、缓存 24h |
| L4 | `openviking_mcp.py find` | 缓存 6h；冷启动约 7.5s（内网语义检索固有耗时） |

> 五域 + 多域共 8 任务由 `ThreadPoolExecutor(max_workers=10)` 并行，逐域耗时与提速见「⚡ 性能基线」。

---

## ⚠️ 已知边界与处理

- **同名函数歧义**：CBM `trace_path` 对同名函数（如 lbm_book 与 lbm_book_zy 各有一个 `RepayContractDebets`）返回 `ambiguous`，需用 `search_graph` 先定位唯一符号；CLI 不接受 qualified_name/JSON 精确消歧（RC=1），**批量/精准影响范围扫描建议走 MCP 常驻服务器（JSON-RPC 可传完整符号）**；
- **`--direction` 合法值**：`inbound`(上游"谁调用我") / `outbound`(下游"我调用谁") / `both`；
- **影响范围**：v2 默认**不再**自动跑 `trace_path`（中文词必然 0 命中且拖慢关键路径）；需要时 `--trace` + 英文函数名，或用 MCP `trace_path outbound` 看真实调用面（KCBP 导出型函数 `inbound` 恒 0）；
- **多域超时**：辅域 `dys/jzqs` 的全库 grep 约 12-22s，v2 改用 BM25 快查（3-6s）+ 单域 8s 上限；若仍超时会如实标注，不臆断补全，可用 `--project <域> --cbm-timeout 30` 单域深挖。
- **共性同步**：本技能与 `ba-to-dev` 共用规范统一维护在 `~/.workbuddy/skills/_shared/SHARED.md`；**优化任一技能时触及共性项，须先改 SHARED.md → `sync_shared.py apply` → `sync_shared.py check`，未通过不得收尾**（详见文末「🔗 共性规范基线 · 共性同步协议」）。

---

## 🧪 实测字典与已知缺陷（2026-11-13「指定合约还款」实证复盘）

### ⚠️ 脚本层缺陷 → v2 修复状态（2026-11-13 已改脚本）

| # | 缺陷（旧版） | v2 处理 | 残余风险 / 绕行 |
| :--- | :--- | :--- | :--- |
| 1 | 证据摘要硬截断 CBM/demand `[:120]`、openviking/dbq `[:240]`（`--json` 同样） | ✅ 默认 600 字符，`--verbose` 全量；需求反查清洗固定模板头 | 超长需求全文仍需直连底层 `read`/读本地 MD |
| 2 | 中文业务词在 C++ 库 BM25 全命中 `makefile`/锁字段噪声 | ✅ `KEYWORD_MAP` 中文→英文标识符；主域改 `search_code` grep，辅域 BM25 并显式标注"弱相关" | 辅域 BM25 仍可能弱相关，需英文函数名精查 |
| 3 | dbq 中文搜表恒 0 命中；v2 初版误把字段名 `contract_sno` 当表名词，三库全 0 | ✅ `DB_KEYWORD_MAP` 表名词（还款→`repay`），字段名不再用于搜表 | 概念未登记映射时请 `--db-search-table "%xxx%"` 手动指定 |
| 4 | `query_interface` 只取前 5 条 + 完整中文词 `LIKE`，实测「直接还款」41 条同族只返回 2 条 | ✅ **已修复**：`query_interface_family()` 用最泛核心词（`还款`/`合约`…）`LIKE` 全库，按系统域分组出一条概览证据，`--verbose` 列全；同族 ≥12 条触发澄清 | 核心词由 `FAMILY_CORE_MAP` 决定；未登记概念不扩展，用 `--verbose` 或功能号重跑 |
| 5 | `trace_path inbound` 对 KCBP 导出函数恒 0、且中文词必然 0 命中还耗时 | ✅ 默认关闭，`--trace` 才跑（需英文函数名） | 真实影响范围走 MCP `trace_path outbound` + `KCBPSPD.xml` 功能号注册 |
| 6 | 超时结果不缓存 → 慢域每次热启动都重新等待 | ✅ 超时/0 命中也缓存（timeout 值进 cache key），`--refresh` 可失效 | 无 |
| 7 | 需求反查被截断，误判"无本地 MD"（实际命中 R2609160118 本地文档） | ✅ 提高上限；`clarification` 改用「▶ 命中行」判定而非占位文字 | 无 |
| 8 | 中文概念只映射一个英文词，不区分系统域：低延时模块名 `direct_repay` 在 jzjy 全库 grep **10.28s 且 0 命中** | ✅ `PROJECT_KW_OVERRIDE` 按域覆盖（jzjy→`perCRReturnFund`、dys→`direct_repay`），主域加 `--path-filter lbmdll/`；实测 10.28s/0 命中 → **4.83s/8 命中** | 新概念需补进覆盖字典；未覆盖时仍可能白跑 | 

| 9 | 「文件号 + 名称」组合查询（如 `A37 大宗交易预委托记录信息`）整词 `LIKE` 必然 0 命中，实际接口库精确存在 `A37` | ✅ `FILE_CODE_TOKEN` 提取编号 token 后按 `code` 精确回查；实测 0 命中 → 1 命中，澄清项 3→1 | 仅支持字母开头编号（A37/Q49/S140）或 5-9 位纯数字功能号 |
| 10 | 编号查询被同族扩展词「委托」放大成 350 条噪声，掩盖精确命中 | ✅ 检出编号且已有命中时跳过 `query_interface_family()`；「直接还款」等同族扩展回归仍为 41 条 | 文件类查询的代码检索词仍按中文映射为 `order`，需手工 `--project jzqs` + 表名精查 |

> 仍未固化：① 文件接口类查询应自动把代码域切到文件所属系统、并用 `table_name`（如 `dzjypreorder`）作代码检索词；② `openviking find` 冷启动约 7.5s 属内网语义检索固有耗时，仅能靠缓存规避（现已是冷启动唯一瓶颈）。

### 复现/补证命令模板

```bash
P=/Users/wujin/.chat/runtimes/darwin-x64/python/versions/3.13.12/bin/python3
O=/Users/wujin/.workbuddy/skills/openviking-query/openviking_mcp.py
DB="/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/rules-raw/.interface_store.db"
export NO_PROXY=csgl.gtht.com.cn,fintech.gtht.com.cn no_proxy=$NO_PROXY

$P $O find "概念"          # 完整 15 项；glob "*需求号*" 列附件；read "<URI>" 读原文
$P - <<'PY'                 # 接口库全字段（含 interface_fields）
import sqlite3; c=sqlite3.connect("$DB"); ...
PY
# 代码层走 MCP：search_code（grep）→ get_code_snippet（完整源码）→ trace_path outbound
# 数据库层：dbq jzjy_sit --search-table "%repay%" / --table run.dbo.xxx / --sql "..."
# 字典表真名：run.dbo.dictindex + run.dbo.dictvalue（**不是 t_dict**，示例 SQL 里的 t_dict 会报 208）
```

### 「指定合约还款」实测映射（可直接复用）

| 层 | 实证值 |
| :--- | :--- |
| 接口库 | `124370` 指定合约还款｜**低延时 KCXP**｜v2.0.0｜负责人 114305｜双向；输入关键字段 `contractdate/contractsno/returnamt/estimated`，输出 `sno/fundeffect` |
| 低延时消息对 | 请求 `7108701`（`contract_date`,`contract_sno`,`repay_value`）→ 应答 `7208702`（`real_repay_value`）；普通直接还款对照 `7102701`→`7202702` |
| 卖券还款族 | 委托 `7109701`（带 `contract_sno`）→ 成交回报 `7209715`；试算 `7390737`→`7490737`；类型查询 `7390733`→`7490733`（字典 Z000156）；多合约还款 `7110701`（`dd_contract_sno`）→`7210702` |
| 集中交易源码 | `Cperiphery::perCRReturnFundAppointed` `lbmdll/lbm_periphery/credittran.cpp:3486-3791`；参数结构 `tagperCRReturnFundAppointed` `perBusTag.h:4971-4980`；导出 `LBMExport.cpp:8505-8524`；普通还款对照 `perCRReturnFund` `credittran.cpp:3205-3466`（KCBPSPD.xml:4717 注册为 `420417`） |
| 集中交易→低延时 | 低延时客户（`GF_CheckDYSCuststatus`, sysid=96）走 RPC `126108`，`business_type=208`，`contract_sno=0`、**合约流水号塞 `appoint_cl_ord_no`（集中交易兜底）**，返回 `real_repay_value`；非低延时走 `stkReturnFundAppointcom` 本地处理 |
| 低延时源码 | 模块 `biz_impl/business/direct_repay_appoint/`；`messages_direct_repay_appoint.h` 定义 `kPktDirectRepayAppoint=7108701`、`kPktDirectRepayAppointResult=7208702`，字段含 `contract_sno` 与 `appoint_cl_ord_no`；核心 `DirectRepayAppointFeeUtil::ReturnFundItem` / `DirectRepayAppointSecurityTrader::ProcessDirectRepayAppoint` / `direct_repay_appoint_business_risk_check.cpp` |
| 字典实证 | `Exyjyzy='w'` = 客户直接还款(指定合约还款)；`Axychfs`：1 直接还款 / 2 卖券还款 / B 合约强制还款 / C 清偿强制还款；`Asfhklx`：1 可全额 / 2 可部分 / 3 无金额还款 |
| 需求/规则 | `R2209280022` 君弘屏蔽卖券还款下"指定合约还款"入口（已上线）；`R2401250039` 卖券还款偿还顺序（息费→预到期本金→同标本金→其他合约，按负债截止日/开仓日排序）——**指定合约还款绕过该默认顺序** |
| **R2609160118 本地文档（v2 新补证）** | `.../obsidian/100_Projects/需求分析/20261008-R2609160118-关于指定合约直接还款的优化需求.md`；状态 **SIT测试待排期**，受理/评审 2026-10-14，交付 2026-12-16，预计 2026年12月上线，ndw 0.5，受理人 **吴进-125360**（云端原文作 050599，两套工号编码），系统 `[jzjy,dys,jzqs]`，Story `[低延时交易系统(大集中-信创域), 集中交易, 集中清算]` |
| R2609160118 关键条款 | ① 委托新增**合约发生日期+合约流水号**；② 批量指定合约还款接口下线、统一单笔（低延时 `is_multi_appoint` 下线）；③ 与客户类型无关，**优先偿还合约级费用再本金，不偿还账户级费用**；④ 还款资金计入当日累积还款金额 `day_total_repay_amt`、可算作中签可用资金 `ipoavl`（联动 `R2607240079` IPO缴款金额提示）；⑤ 委托下场文件 **Q23** 的 `remark`/`bankfrzsno` 存合约编号，外围客户端/集中营运/经纪业务平台备注字段展示；⑥ 防重唯一键 = 合约发生日期+合约流水号+委托序号 |
| R2609160118 代码溯源 | `dys` `direct_repay_appoint/`（已含 `contract_date/contract_sno`；`business_type 208`=DirectRepayAppoint、`202`=DirectRepay，`tradingconfigdb.t_dict`；`t_order` 复用 `bankfrzsno`）；`jzjy` `loantran.cpp Cperiphery::perLoanFundRepay:8659-9424`（功能号 `410672`，`perBusTag.h:7968`，`cBusitype='2'` 两融；`orderrec` 复用 `bankfrzsno`）；`jzqs` `DealCredit.cpp RepayContractDebets:1439-2198` + `GetRepayOrderOfOther:16345`（统一时序落点候选） |
| R2609160118 待确认（需求自身 BA 澄清项） | 委托字段扩展方案 A（现有委托加可选 `contract_date/contract_sno`，推荐）/ B（新增独立委托类型）；清算时序统一的「结果回执/资金扣减/负债更新」三时点差异核对；**全业务实时资产计算中心系统是否纳改**；与保证金可用余额优化、个微融资偿还加速项目的上线次序 |
| 数据库 | `bb_contract`(74字段, 主键 orderdate/serverid/sno)、`clearcreditdebt`(26字段, debtsno/debt_sno/debt_ordersno)、`gqjlrz_repaydetail`(21字段, `contractsno`+`repayamt`)、`creditassetdebts`(70字段)；搜表 `%repay%` 5 张 / `%debt%` 380 张 / `%contract%` 266 张；`dys95` 搜 `%repay%` 另命中 `t_new_repay_white_list`（信用客户新偿还模式白名单） |

### 「直接还款」实测映射（2026-11-13 追加，同族自动扩展实证）

| 层 | 实证值 |
| :--- | :--- |
| 主接口 | `124369` 直接还款（低延时 KCXP v2.0.0，负责人 114305）、`420417` 直接还款（集中交易 v1.2.6，负责人 102180） |
| 接口族全貌 | `LIKE '%还款%'` 全库 **41 条**：低延时 31 / 集中交易 9 / 集中清算 1。业务子类：① 普通直接还款 `124369/420417/7102701→7202702/100007102701→100007202702`；② 指定合约还款 `124370/420419/7108701→7208702`；③ 卖券还款 `124026/7109701→7209715/7390733→7490733/7390737→7490737/7110701→7210702`；④ 小贷/股权激励 `410672/412023/420640`；⑤ 查询与白名单 `124063/124265/125097/124913/C83/124826` |
| 集中交易源码 | `perCRReturnFund` `credittran.cpp:3205-3466`（导出 `LBMExport.cpp:8481-8498`，`KCBPSPD.xml:4717`=420417）；`perLoanFundRepay` `loantran.cpp:8655-9420` / `LBMExport.cpp:13622-13640`（410672，`LBMExport.h:662`）；`stkReturnFundcomLoan` `CommStk.cpp:51986-52234`（**贷款类链路，调 `up_com_loancreditreturnfund`**；同文件并列 `stkReturnFundcom` :51325-51657 → `up_com_creditreturnfund`、`stkReturnFundAppointcom` :51658-51985 → `up_com_creditreturnfund_appointsno`；R2610120003 文档已勘误）；`stkLoanCreditForceRepay` `stkLoanTran.cpp:3829-3871`；`perLoanCreditReturnFund` `loantran.cpp:10951-11026` |
| 低延时源码 | `biz_impl/business/direct_repay/include/direct_repay.h:62-66` `DirectRepay`；`business_type` **202**=DirectRepay / **208**=DirectRepayAppoint（`tradingconfigdb.t_dict`），两者 `bsflag='ZZ'`，靠 business_type 区分 |
| 需求 | `R2610120003`【债基货基主动卖券还款优化】状态 **技术评估中**、预计 2026-12 上线：取消委托发起阶段「剔除融资数量后剩余货基市值 < 货（债）基占用则禁止卖券还款」的禁止性校验，成交后资券处理不变；**低延时与集中交易须同步取消**，代码落点 `CommStk.cpp` / `loantran.cpp` / `stkLoanTran.cpp`；本地 MD 已于 2026-11-13 完成源码勘误（见下）；`R2609160118` 指定合约直接还款时序统一 |
| 同族澄清 | 该概念短词多义，同族 ≥12 条自动触发澄清（选系统域 / 仅主命中）；`指定合约还款` 等 ≥5 字已登记精确概念豁免。用户 2026-11-13 选择「普通直接还款主链路」→ 回灌 `420417`/`124369`/`perCRReturnFund` 精查 |
| **普通直接还款源码主链路** | `perCRReturnFund` `credittran.cpp:3205-3466`（完整源码经 `get_code_snippet` 实证）：① `CheckTrdpwd`→`-420417005`；② `GF_GetPerOper`→`-420417010`；③ `GF_GetFundinfo`→`-420417018`；④ **15:30 后**（`nSystime>=15300000`）查 `creditmixparam '0i'/ckind='1'` + `crdcustcompwhitelist` 白名单，不在名单→`-420417050`；⑤ `creditmixparam '0j'` 取 `qty` 禁止时点→`-420417051`(未配置)/`-420417052`(超时点)；⑥ `GF_CheckDYSCuststatus(sysid=96)` 低延时客户 → **RPC 126107**、`business_type=202`（字段 `repay_value/currency/order_way/cust_id/fund_account_id/branch_id/account_id/user_info/pwd/remark/client_feature_code/is_account_partition/te_partition_no/transact_time/client_seq_id`），`RpcCallRpcLbm("126107", DYS_VIPNODEID)` 取 `real_repay_value`，异常 `-420417070`；⑦ 普通客户查 `creditcustcontrol.ctrlkinds` 含 `'0'`→`-420417068`、`creditcustcontrol_new.creditdigestid` 含 `'w'` 且 stkcode/market/secuid 均空→`-420417069`；⑧ `GF_GetEntrustType`（`ENTRUST_LOCAL`/`ENTRUST_SECUBANK`）→ `objCCommStk.stkReturnFundcom`（`CommStk.cpp:51325-51650`）→ `MakeSingleResultSet("fundeffect")` |
| **普通 vs 指定合约还款对照** | 普通：`126107` / `202` / `stkReturnFundcom` / 无合约字段 / 输出 `fundeffect`；指定合约：`126108` / `208` / `stkReturnFundAppointcom` / 合约流水号塞 `appoint_cl_ord_no` / 取 `real_repay_value` / 仅冲本笔合约。两函数并列于 `credittran.cpp`（3205-3466 / 3486-3791） |
| 接口字段实证 | `420417` 16 字段：输入 `funcid/custid/custorgid/trdpwd/netaddr/orgid/operway/operwayext/ext/terminalinfo/userinfo/fundid/moneytype/fundeffect/remark`，输出 `fundeffect`(实际还款金额)；`124369` 19 字段：含 `g_funcid/trustcode(互信码)/targetNode/custid/fundid/brhid/secuid/moneytype`，输出 `CODE/LEVEL/MSG/clordno/fundeffect`；`7102701` 15 字段（`cust_id/fund_account_id/branch_id/account_id/currency/order_way/repay_value/remark/password/client_seq_id/client_feature_code/user_info/order_way_ext`）→ `7202702` 18 字段（`real_repay_value/cl_ord_no/reject_reason_code/transact_time…`） |
| 低延时报文 | `biz_impl/business/direct_repay/include/messages_direct_repay.h:35-36` 定义 `kPktDirectRepay=7102701` / `kPktDirectRepayResult=7202702`；`repay_value` :48/:91、`real_repay_value` :92 |
| 字典实证 | `Exyjyzy` 共 23 项：`'u'`=卖券还款、`'v'`=总部还款平仓、`'w'`=客户直接还款(指定合约还款)；**字典未区分普通/指定合约还款**，区分靠 `business_type 202/208`；相关字典 `Arzhkbz`(融资还款标志)、`Asfhklx`(可还款类型) |
| **两还款函数关系（源码闭环）** | `stkReturnFundcom`(51325-51650) 与 `stkReturnFundcomLoan`(51986-52219) 是 **并列实现、互不调用**（`CommStk.cpp` 同文件两个方法，callers 分别 4 / 2）。前者入参 `tagstkReturnFund`、调 `sql..up_com_creditreturnfund`，含 VIP 同步校验（`vipconfig/vip_syncstatus`）、信用状态检查(150626/150826)、`jzjyorderpushlog` 推送，错误码 `-990287xxx`；后者入参 `tagLoanstkReturnFund`（含 `nApplydate/nApplysno/sExtstr`）、调 `sql..up_com_loancreditreturnfund`，更新 `loan_applylist.endamt`，资金校验更严（同时校验 `fundbal`/`fundavl`/`fundbal-creditbal`），无 VIP 校验与推送，错误码 `-990293xxx`。**普通两融直接还款走前者；后者属小贷/贷款还款链路** |
| ⚠️ 需求文档溯源偏差（**已于 2026-11-13 勘误**） | `R2610120003` 本地 MD「（四）代码知识图谱与架构溯源」原表把 `stkReturnFundcomLoan` 记为「融资还款核心逻辑，调用 `up_com_creditreturnfund`」、行号 51427-51660，与源码不符。已修正为 6 行表（`stkReturnFundcom` / `stkReturnFundAppointcom` / `stkReturnFundcomLoan` 三函数并列，含真实存储过程/入参/错误码/行号）并新增「溯源勘误」小节（原表述→修正后→源码依据→并列结论），frontmatter `updated` 同步 2026-11-13；勘误前备份 `.workbuddy/backup/R2610120003.bak.20261113-1324.md`。**待评审确认**：该表覆盖资金处理/成交后清算，未定位「卖券还款委托发起前置校验」真实代码落点。另发现 `perLoanFundRepay`(410672) `loantran.cpp:8755` 仅放行 `cBusitype='1'`（质押），与 `R2609160118` 本地 MD L77「本需求为两融 `cBusitype='2'`」口径冲突，**尚未核销** |

### 「A37 大宗交易预委托记录信息」实测映射（2026-11-13 追加）

| 层 | 实证值 |
| :--- | :--- |
| 接口库定义 🟢 | `A37`｜**集中清算系统**｜文件接口 / 交易参数文件｜表名 `dzjypreorder`｜**39 字段**（`file_fields`）；主键 `serverid + sysdate + sno`；无版本/负责人 |
| 同名对照文件 🟢 | `Q49` 同名同表（**低延时交易系统(虚拟)**，35 字段，含 `custid/fundid/orderwayext`）；`S140` 大宗交易预委托营业部审批权限信息（交易参数管理后台，表 `dzjy_brhright`，2 字段 `brhid/opendate`） |
| A37 vs Q49 字段差异 | A37 独有 `orgid/settunit/fundacct/trdsysid/coreid/gtserverid/operwayext/userinfo`；Q49 独有 `custid/fundid/orderwayext`；两侧都有 `extstr varchar(32)` |
| 关键枚举 | `applystatus` 0未审批/1审批同意/2审批拒绝/3已撤销/5已过期；`dealstatus` 0未执行/1执行申报成功/3执行失败；`limitstkflag` 0非受限/1受限 |
| 文件定义（源码 🟢） | `jzqs/src/src/src_sql/4_file_import/文件导出脚本/低延时按serverid拆分/node_dzjypreorder_out_file.sql`（另有「信创-文件导出脚本」同构版）：`fileid=JZQS_DZJYPREORDER_DYS`、`intfid=JZQS_DYS`、`iodirect='O'`（导出）；文件名 `CFD_130_@receiver_@nextbusidate_A37.TXT`，按 serverid 拆分 `..._A37_@serverid.TXT`；行分隔 CRLF、列分隔 `CHAR(1)`、文件头字段 `totalnum`；**文件体 37 列** |
| 导出 SQL（源码 🟢） | 主表 `node..node_dzjypreorder_{nodeid}_baktable_file ta` → JOIN `node_fundacct`（`trdsysid+coreid` 拼 `gtserverid`）、`comm_trdsysfilter`、`comm_org(orgtype=1)` 取 `serverid`、`node_custchange(clearsysid=1)` 过滤；`market` 经 `node.dbo.convertmarket()` 转换 |
| 数据库（🟢 `jzqs_sit`） | `node.cjs_dzjypreorder` / `node.dys_dzjypreorder`（各 38 字段，含 `nodeid/operwayext/userinfo`）；`node.dys_dzjypreorder` SIT 抽样：`market=9`、`stkcode=920745`（北交所）、`extstr=0899074922`（对手方股东账户）、`applystatus=1/dealstatus=1`，沪深 `market=1` 的 `extstr` 为空 → **R2610120043 改造已在 SIT 落地**；`node.cjs_dzjypreorder` 0 行 |
| 代码侧 | `jzqs` `lbm/comm/memdb_mgr_factory.h:498/726` 注册 `cjs_dzjypreorder` / `dys_dzjypreorder` 内存表；`jstp_database_table_idx.h:45/101` 索引 14/70；`jzjy` / `dys` 项目全库 grep `dzjypreorder` **0 命中**（文件落地逻辑只在清算侧导出脚本） |
| 需求（🟢 本地 MD） | `20261012-R2610120043-关于北交所信用账户大宗交易需求.md` L233-243 / L278：预计 2026-11 上线、改造范围低延时+集中交易、联测集中清算+集中营运；**Q49** 低延时 → 集中交易/集中清算下发；**A37** 集中清算 → 低延时下发（清算核对回流通道）；两者复用 `extstr` 承载北交所对手方股东账户；集中交易日间预委托**不下场给集中清算** |
| 订阅矩阵（🟢 权威） | `新一代文件交互接口订阅矩阵.xlsx` Sheet1 **R299**：A37 输出系统=**集中清算系统**、**唯一消费者=低延时交易系统(虚拟)**（√）；**R523**：Q49 输出=低延时交易系统(虚拟)，消费者=**集中清算系统 + 集中交易系统**；**R49**：S140 输出=交易参数管理后台，消费者=低延时。全量 498 文件 / 743 条订阅关系，已入库 `.subscription_matrix.db` |
| ⚠️ 口径差异（3 项待确认 + 1 项已核销） | ① 接口库 A37 登记 **39 字段**，源码导出脚本（普通/信创两版）均 **37 列**，差 `operwayext`/`userinfo`；② ✅ **已核销**：订阅矩阵 R299 明确 A37 唯一订阅者为「低延时交易系统(虚拟)」，需求文档口径正确，源码注释「统一清算-->集中交易系统」为泛称/偏差；③ Q49 在 jzqs `src_sql` 内未找到文件定义（疑在低延时侧或文件接口平台）；④ `node.cjs_dzjypreorder` SIT 0 行，A37 回流通道暂无测试数据 |

---

## 🗂️ 订阅矩阵库（本技能特有补充）

> 库路径、脚本、命令、状态口径与 **A37 权威结论**统一见文末「🔗 共性规范基线 · 订阅矩阵库」；`ba-to-dev` P0#26 数据流图铁律⑥ 引用同一份权威源。本节只列建库细节。

| 表 / 视图 | 内容 |
| :--- | :--- |
| `files` | **498** 个文件编号：名称、输出系统(生产者，A 列稀疏合并→前向填充)、接口库元数据（**492/498** 命中，98.8%） |
| `consumers` | 18 个消费者系统列 + 各自订阅数（集中交易 271 / 低延时虚拟 216 / 集中清算 93 …） |
| `subscriptions` | **743 条订阅关系**（file_code × consumer，含矩阵行列号、实证状态，唯一约束防重） |
| `columns_meta` | 22 有效列元数据；`是否根据分区号下发（仅限低延时订阅）` 是**属性列**（`is_consumer=0`），不计消费者 |
| `evidence` | 14 条跨源实证 / 待确认（A37 9、Q49 3、S140 2），status 🟢已实证 / 🟡可追溯 / 🔴待确认 |
| `meta` | 数据源、构建日期、计数、证据状态字典 |
| `v_file_consumers` / `v_a37_consumers` | 消费者查询视图 |

**建库细节**：`build` 采用 temp + 原子替换，可随时重建；A 列稀疏合并单元格用**前向填充**还原 8 个输出系统分组；`columns_meta.is_consumer=0` 的属性列不参与消费者统计，避免污染计数。

**L1.5 联动实现**：`biz_logic_query.py` 的 `query_subscription()` 在接口库命中文件编号时自动附加一条「订阅矩阵」证据（只读毫秒级，库不存在静默跳过）。实测查 `A37 大宗交易预委托记录信息`、`--code Q49` 均自动带出消费者；回归「指定合约还款 --all」无影响。

**6 个未关联接口库的文件**：`A022` / `A095` / `C73` / `M03` / `M04` / `M05`（`files.interface_matched=0`，多为债券柜台/深沪港通通知类）。

---

## ⚡ 性能基线（2026-11-13 实测 / macOS / Python 3.13.12）

| 场景 | v1 串行 | v2 | 变化 |
| :--- | ---: | ---: | :--- |
| `--all` 冷启动（8 任务） | 15.68s | **7.89s** | 提速 50% |
| `--all` 热缓存（8/8 命中） | 15.68s | **0.52s** | 提速 97% |
| `--all --json` 热缓存 | — | 0.10s | 供下游解析 |
| `--fast` 热缓存 | — | 0.01s | 仅接口库 + 规则 |

**v1 逐域基线（定位瓶颈）**：`openviking find` 7.34s ＞ `需求反查` 3.05s ＞ `CBM search_graph` 2.31s + `trace_path` 2.42s ＞ `dbq 搜表` 0.95s ＞ `接口库` 0.01s —— 旧版总耗时 ≈ 各域之和。

**v2 五个加速点**：
1. **并行**：五域 + 多域拆成 8 任务 `ThreadPoolExecutor(max_workers=10)`，总耗时 ≈ 最慢域而非累加；
2. **缓存**：`.cache/` 文件缓存，图谱/表结构 24h、需求反查 1h、规则 6h；超时/0 命中也缓存（timeout 进 cache key），避免慢域每次重复等待；
3. **剪枝**：中文概念映射英文标识符、dbq 用**表名词**而非字段名、默认关闭 `trace_path`、去掉已实证 0 命中的备选词全库 grep；
4. **多域分工**：主域 `search_code` grep 精准命中符号，辅域 `search_graph` BM25 快查 + 8s 上限（大项目全库 grep 12-22s 会拖垮关键路径）；
5. **超时保护**：单域超时如实标注"已跳过"并提示 `--project` 单域重试，不阻塞其余域。

**v2.1 增量（2026-11-13「直接还款」实证）**：冷启动 10.36s → **7.50s**，主域 `search_code(direct_repay)` 全库 grep **10.28s / 0 命中** → `perCRReturnFund` + `--path-filter lbmdll/` **4.83s / 8 命中**；同族接口从 2 条补全到 41 条。热缓存不变（约 0.08s / 8-8 命中）。

> 冷启动仍受 `openviking find`（约 7.5s 内网语义检索）限制，属数据源固有耗时；高频概念靠缓存规避，数据更新后 `--refresh`。

---

## ❓ 交互澄清协议（本技能脚本触发细节）

> 原则、回灌映射、已确认字典**统一见文末「🔗 共性规范基线 · 交互澄清协议」**（用户 2026-11-13 明确要求，两技能共用）。本节只列本技能 `--json` 信号与执行流程。

### 触发条件（脚本 `--json` 的 `clarification` 数组非空）

| 信号 | 该问什么 | 目的 |
| :--- | :--- | :--- |
| 接口库 0 命中 | 功能号 / 接口名 / 所属系统域 | 换成系统正式名称 |
| 命中 ≥4 个同族接口 | 本次定位请求 / 应答 / 试算 / 委托哪一类 | 消除多义 |
| 中文概念未映射出英文标识符 | 英文函数名 / 报文结构名 / 字段标识 | 让代码层 grep 精准 |
| 代码层多域 0 命中或超时 | 是否收窄到单域 | 提速 + 提准 |
| 本地需求库未命中 | 明确需求号 | 补齐需求证据 |
| 同族接口自动扩展 ≥12 条（短词多义，如「直接还款」41 条） | 定位哪个业务子类 / 哪个系统域，还是仅主命中 | 把泛词换成精确接口名或功能号 |

> **豁免**：`q` 精确等于 `KEYWORD_MAP` 中 ≥5 字的已登记概念（如「指定合约还款」）时视为明确，虽展示同族概览但不触发澄清；不要打扰顺畅查询。

### 执行流程（智能体必做）

1. 跑 `$P $S "<问题>" --all --json`，读 `clarification` 与 `keywords`；
2. `clarification` 非空 → **立即向用户提问**（用 `AskUserQuestion`，≤3 问，选项取自 `options`，`why` 写明"为什么这个答案会影响关键词"）；
3. 用户答案按**共性基线的回灌映射表**回灌重跑，不得只记在对话里不用；
4. 稳定确认项写回 `SHARED.md` 的 `clarification` 块并 `apply` 推送到两技能（`check` 通过后），下次不再重复问；同一概念的新映射补进脚本 `KEYWORD_MAP` / `DB_KEYWORD_MAP`。

> **诚实原则**：`clarification` 是"请用户补充证据"，不是"模型自己补全"。用户未确认前，相关结论一律保持 🔴 待确认，严禁臆断（三态定义见共性基线）。

---

## 🔗 共性规范基线（单一事实源：_shared/SHARED.md）

> ⚠️ 本章由 `sync_shared.py apply` 自动同步，**禁止手工编辑块内内容**；共性改动一律先改 `~/.workbuddy/skills/_shared/SHARED.md` 再 `apply` + `check`。本章之外的内容是本技能特有的场景化扩展。

<!-- SHARED:authority_sources START -->
### 🔗 权威源注册表（两技能共用，DB-First）

| 检索域 | 权威源 | 路径 / 命令 | 口径 |
| :--- | :--- | :--- | :--- |
| L0 需求依赖反查 | `demand_dep_find.py` | `~/.workbuddy/skills/ba-to-dev/scripts/demand_dep_find.py <需求号> [概念...]` | 本地需求 MD 全库反查；反查词用**业务概念**，禁用 `ipoavl` 等特化字段名 |
| L1 接口知识库 | SQLite | `/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/rules-raw/.interface_store.db`（`interfaces` / `interface_fields`） | 功能号、文件编号、字段明细以本库为准 |
| L1.5 订阅矩阵库 | SQLite | 同目录 `.subscription_matrix.db`，见下方「订阅矩阵库」块 | 文件编号 → 输出系统 / 消费者方向 |
| L2 代码知识图谱 | `codebase-memory-mcp` | `~/.local/bin/codebase-memory-mcp cli` 或 MCP `search_code` / `get_code_snippet` / `trace_path` | 项目 `jzjy` / `dys` / `jzqs` / `grc` / `cszx`；**中文业务词 0 命中是常态**，改英文符号 + `--path-filter` |
| L3 数据库实证 | `dbq <profile>` | `/usr/local/bin/dbq`；profile `jzjy_sit` / `dys95` / `jzqs_sit` / `cszx_sit` / `jzqs_comm_sit` | `--table` / `--search-table` / `--sql`；**字典表真名 `run.dbo.dictindex` + `run.dbo.dictvalue`，不是 `t_dict`** |
| L4 业务规则 / 既有需求 | `openviking_mcp.py` | `~/.workbuddy/skills/openviking-query/openviking_mcp.py find\|glob\|read` | 必须 `NO_PROXY=csgl.gtht.com.cn,fintech.gtht.com.cn` |
| 系统名称清单 | `system_list.csv` | `/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/rules-raw/system_list.csv` | 中文全称；BA 正文写统称，括号域归属留给拆 Story 阶段 |
| 本地需求 MD | Obsidian | `/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析/` | 需求号优先本地三级检索，命中即 0 秒复用 |

**DB-First 优先级（P0）**：`dbq 直查 > 权威清单(system_list.csv / 接口库 / 订阅矩阵) > 代码图谱符号级溯源 > 需求原文`。凡**客观事实**（表名 / 字段名 / 字段类型 / 参数编码 / 系统中文全称 / 接口号 / 规则条文编号）必须先实证再落盘，**严禁「名字像 / 关键词像 / 函数名像」推断语义**。典型反例：`comm_secuid_total` 实为计数表（标准名称源是 `comm_stock.stkname`）、`zy_debts` 实为股票质押（非两融负债表）。

**路径约定**：`.chat/skills` 是指向 `.workbuddy/skills` 的软链接，改一处即生效；所有脚本一律只用 `~/.workbuddy/skills/` 下的版本，不用临时副本。
<!-- SHARED:authority_sources END -->

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

<!-- SHARED:sync_protocol START -->
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
<!-- SHARED:sync_protocol END -->
