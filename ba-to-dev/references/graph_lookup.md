# 代码知识图谱逆向核验与系统映射指南 (Graph Lookup Reference)

本文档为 `ba-to-dev` 技能的代码知识图谱专项参考。包含系统图谱映射、查询模式、降级链与证据提取规范。

---

## 1. 系统源码与代码图谱映射全景

| 系统简称 | 系统标准名称 (`system_list.csv`) | 源码物理路径 | CBM CLI 项目名 (`list_projects`) | 本地图谱支持状态 |
| :--- | :--- | :--- | :--- | :---: |
| **`jzjy`** | 集中交易系统 | `/Volumes/Macintosh HD_Data/Project/jzjy/spbsrc/` | `Volumes-Macintosh-HD_Data-Project-jzjy-spbsrc` | 🟢 已接入 (~38万节点) |
| **`dys`** | 低延时交易系统 / 低延时交易系统（创新域） | `/Volumes/Macintosh HD_Data/Project/dys/branches/master/tree/` | `Volumes-Macintosh-HD_Data-Project-dys-branches-master-tree` | 🟢 已接入 (~6.5万节点) |
| **`jzqs`** | 集中清算系统 | `/Volumes/Macintosh HD_Data/Project/jzqs/src/src/` | `Volumes-Macintosh-HD_Data-Project-jzqs-src-src` | 🟢 已接入 (~42万节点) |
| **`cszx`** | 交易参数管理后台系统 | `/Volumes/Macintosh HD_Data/Project/jygl/jygl_sys/` | `jygl_sys_cszx` | 🟢 已接入 (~27.6万节点) |
| **`djgl`** | 客户登记管理系统 | - | - | ⚪ 暂无图谱（跳过） |
| **`ssjs`** | 用户实时计算系统 | - | - | ⚪ 暂无图谱（跳过） |
| **`grc`** | 低延时全局风控系统 | `/Volumes/Macintosh HD_Data/Project/grc/branches/main/tree/` | `Volumes-Macintosh-HD_Data-Project-grc` | 🟢 已接入 (~1.85万节点) |
| **`jzyy`** | 集中营运系统 | - | - | ⚪ 暂无图谱（跳过） |

> **低延时「域归属」判定规则**：
> - 需求含 **「个微」** 或指向 **「98 / 98 创新域」** 时，系统选择 **`低延时交易系统（创新域）`**（代码与 `dys` 图谱同源）；
> - 需求泛称「低延时」且属两融业务时，默认 95 信创域；
> - 严禁跨系统借用或混淆代码节点。

---

## 2. 图谱逆向核验前置门禁 (Checklist)

**任一命中「是」即跳过图谱逆向，文档中整体省略「（四）代码知识图谱与架构溯源」小节**：
- [ ] 改造范围为空 / 无任何代码改动点？
- [ ] 需求类型为纯参数调整、文案修改、单表字段增加（L1 轻量级）？
- [ ] 需求为纯业务/管理/流程类，不涉及任何系统代码改造？
- [ ] 涉及的系统均无本地知识图谱支持（如 `djgl` / `ssjs`）？

---

## 3. 图谱高效检索三级流水线

### 第一优先级：CBM CLI 结构化查询 (秒级)
全路径调用：`/Users/wujin/.local/bin/codebase-memory-mcp cli <command>`

1. **文件/符号定位**：
   ```bash
   codebase-memory-mcp cli search_graph --project <CBM项目名> --query <关键词> --limit 20 --format tree 2>&1 | grep -v "level=info"
   # 或按文件名模式匹配：
   codebase-memory-mcp cli search_graph --project <CBM项目名> --file-pattern <文件名.cpp> --limit 20
   ```
2. **代码片段回读**：
   ```bash
   codebase-memory-mcp cli get_code_snippet --project <CBM项目名> --qualified-name <完整QN> --include-neighbors
   ```

### 第二优先级：sqlite3 直连批量查询 (降级)
当 CBM CLI 不可用时：
```bash
sqlite3 "/Volumes/Macintosh HD_Data/Project/{jzjy|dys|jzqs}/.code-review-graph/graph.db" \
  "SELECT file_path, name, kind FROM nodes WHERE file_path LIKE '%关键词%' LIMIT 30;"
```
* **铁律**：文件级检索必须用 `WHERE file_path LIKE '%文件名%'`，`name` 列仅存函数与类名；
* **GRC / cszx 图谱库**：CBM 图谱统一存于 `~/.cache/codebase-memory-mcp/`（GRC=`Volumes-Macintosh-HD_Data-Project-grc.db`，cszx=`jygl_sys_cszx.db`，与 jzjy/dys/jzqs 同机制），项目目录 `.code-review-graph/graph.db` 不存在。

### 第三优先级：定向 grep 兜底 (带熔断)
* 限定单词边界：`grep -E "(^|[^A-Za-z0-9_])KEYWORD([^A-Za-z0-9_]|$)"`
* 编码感知：GBK 源码中文需转码，英文符号直接搜；
* **5秒超时熔断**：超过 5s 未返回即降级为「未定位到精确代码，待研发确认」，严禁阻塞产出。

---

## 4. 证据融入与链接格式铁律

1. **物理文件链接格式**：`[文件名.h](file:///绝对路径/文件名.h)`（空格用 `%20` 编码）；
2. **严禁在 URI 结尾添加 `#L10-L20` Hash 锚点**（会导致 macOS 协议解析失败无法跳转），行号统一填入表格独立的“行号”列；
3. **存在性门禁**：仅 `test -f` 确认存在的文件可挂载 `file://`，待新建文件使用纯文本加 `(待新建)` 标注；
4. **同名表 ≠ 文件接口生成方**：
   - 文件类接口归属以需求方口径或接口明细库登记为准，严禁凭源码中存在同名内部表推断生成方；
   - 账单/报表分工标准：数据清理/补全 = 生成方系统（如 `djgl`），数据文件生成与发送 = 消费方系统（如 `ssjs`）。

---

## 5. 数据库交叉验证（与 DB Lookup 配合）

**代码图谱定位到表名/字段/参数编码/存储过程后，必须调用「数据库查询」SKILL（/db-schema-query，`dbq <profile>`）对同一系统数据库做交叉验证**（系统图谱 ↔ 系统数据库一一对应，严禁跨系统借用）。

| 验证模式 | 图谱发现 | 数据库验证（「数据库查询」SKILL） | 产出 |
| :--- | :--- | :--- | :--- |
| ① 表结构 | 代码引用 `creditmixparam` | `INFORMATION_SCHEMA.COLUMNS` 查实际列名/类型 | 确认字段口径一致 |
| ② 参数值 | 代码读 `paramkinds='0m'` | `SELECT * FROM run.dbo.creditmixparam WHERE paramkinds='0m'` | 参数当前值，评估改动影响 |
| ③ 字典含义 | 代码用 `paramkinds` 编码判断 | `dictvalue(dictitem='Z000409')` 查中文名 | 业务语言描述参数 |
| ④ 影响分析 | 代码 `WHERE paramkinds IN (...)` | `GROUP BY paramkinds` 统计分布 | 评估批量改动波及范围 |

> **完整查询模板、系统-数据库映射、cszx 参数表速查**详见 [`references/db_lookup.md`](file:///Users/wujin/.chat/skills/ba-to-dev/references/db_lookup.md)。
> ⚠️ 数据库表名/字段名仅置于第三章技术实现，严禁暴露在评审纪要（第 3 项必须业务语言）。

---

## 6. 溯源精准性红线（防误判，P0）

> 以下规则源自 R2609160118「指定合约直接还款」溯源实测沉淀，用于避免「定位到表但业务语义不符」导致改造点判断错误。

### ① 表名语义核对（P0）
代码图谱/数据库定位到表名后，**必须核对表名前缀语义是否匹配本需求业务**，严禁仅凭表名含 `debt`/`credit`/`loan` 关键词即判定为目标表：
- `zy` = 质押（**股票质押**，如 `zy_debts`），**非融资融券**；
- `gqjl` = 约定购回线，非两融直接还款；
- `credit` = 融资融券信用（`creditdebts`/`t_credit_debts`/`node_creditdebts`）。

> ⚠️ 实测教训：曾把股票质押 `zy_debts` 误当融资融券负债表，导致改造点判断错误。核对表名语义后须在文档「明确排除」注明易混淆表及排除理由。

### ② 数据库交叉验证覆盖所有涉及系统
多系统需求必须对**每个涉及系统**的库做交叉验证（负债表 + 委托表关键字段），严禁只验证主系统后照搬结论。每系统验证产出：
- 负债表：定位字段（如 `applydate/applysno/sno/groupsno`）与目标字段（如 `contract_date/contract_sno`）是否存在；
- 委托表：目标字段是否存在，承载方式（结构对象 vs 落库列）需确认。

### ③ 溯源文件只保留直接支撑改造点的（映射表精简原则）
文件映射表**只输出与本需求改造点密切相关的文件/函数**，关联不大的**一律不输出**，每系统**建议 1-4 行**。

**正向保留清单**（满足其一才保留）：
- 改造点所在的核心交易处理函数（如 TER/CER 处理、`unictrCROrderGuaranty`）；
- 主校验/计算函数（风控校验、可提数量计算，如 `PledgeInOrOutBusinessRiskCheck`）；
- 查询/提示口径函数（如 `CreditGetStockDbzc` 提示可划转数量）；
- 直接参与改造口径的外部入口（需口径一致时，如 `perCROrderGuaranty`）。

**删除清单**（与改造点无直接关联）：
- 网关层（AGW）委托解析入口/ER 回报处理；
- 委托预处理器、业务执行器；
- 辅助/外部/未处理管理器（如 `PledgeInOrOutBizExtManager`、`RepoPledgeUndealedInfoManager`）；
- 纯回报/请求结构体（TER/CER 等，无字段增减时）；
- 报文标签定义（`BusTag.h` 等，无字段增减时）；
- 参照类（强平还款、约定购回）、同构副本（如 `lbm_book_zy/DealCredit.cpp`）；
- 摘要号/字典定义（如 `digest.h`）、memdb 联动回调层。

### ④ 委托表承载字段表述
字段承载方式统一用「**新增或复用字段**」，不武断「需新增」；具体承载方式（新增字段 vs 复用现有字段）留待实现阶段确认（对应需求矛盾审计方案 A/B）。

### ⑤ 各系统核心表命名速查
| 业务实体 | 集中交易 jzjy | 低延时 dys | 集中清算 jzqs |
|---------|--------------|-----------|--------------|
| 委托表 | `orderrec` | `t_order` | `node_orderrec` |
| 融资融券负债表 | `creditdebts` | `t_credit_debts` | `node_creditdebts` |
| 负债明细 | `creditdebtsdetail` | `t_credit_debts_detail` | `node_creditdebtsdetail` |
| 信用资金 | `creditfund` | `t_credit_fund` | `node_creditfund` |
| 息费 | （`creditdebts` 内含 `debtskind`） | `t_credit_fee` | `node_creditfee` |

---

## 7. 图谱 0 命中 ≠ 无图谱（排查流程，P0）

> 源自 R2609170003「担保品返还剔除融资数量」溯源纠错实测沉淀。

**背景**：图谱 `nodes_fts` 仅索引符号四列（name/qualified_name/label/file_path，FTS5 `content=''`），**整数常量、行注释、XML 属性值、SQL insert 值、业务中文词全不建索引** → 纯数字功能号、业务中文检索 0 命中是**常态而非图谱损伤**，**严禁据此判定「本地无图谱，待开发确认」**。

**「无图谱」标注资格门禁（P0）**：只有本文件第 1 节映射表标注「⚪ 暂无图谱（跳过）」的系统（`djgl`/`ssjs`/`jzyy`）允许省略溯源；`jzjy`/`dys`/`jzqs`/`grc`/`cszx` 五系统图谱真实存在（38万/6.5万/42万/1.85万/27.6万节点），任何检索 0 命中都必须走完整兜底链后才能给结论。

### 兜底复核链（按序执行，任一步命中即停止）

1. **L1.5 功能号注册表反查（最快）**：调用 `接口查询` SKILL 或直查 `rules-raw/.funcid_index.db`
   ```bash
   sqlite3 "/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/rules-raw/.funcid_index.db" \
     "SELECT code, func_name, module, dll FROM funcids WHERE code='121315';"
   # 命中 → 已知功能名+模块，直接定位到源码
   ```
   场景：需求已给出功能号 / 业务动作可反查功能名（如「担保物转出」→121315/420415）。

2. **源码定向 grep（功能号维度）**：图谱符号检索不到的整数常量/注释/XML 属性，源码 grep 必然命中
   ```bash
   grep -rn --include=*.cpp --include=*.h --include=*.xml --include=*.sql "121315" "/Volumes/Macintosh HD_Data/Project/jzjy/spbsrc/lbmdll"
   # 优先核对 KCBPSPD.xml（功能号↔模块）、sysfunc_init.sql（注册名）、BusTag.h 注释行、错误码 -121315●●●
   ```

3. **CBM 换词/符号检索**：符号存在时用代码符号检索（类名/函数名/文件名），不用业务中文词
   ```bash
   codebase-memory-mcp cli search_graph --project Volumes-Macintosh-HD_Data-Project-jzjy-spbsrc --query CROrderGuaranty --limit 20 2>&1 | grep -v "level=info"
   ```

4. **sqlite 直连（file_path LIKE）**：文件级定位
   ```bash
   sqlite3 "/Volumes/Macintosh HD_Data/Project/jzjy/.code-review-graph/graph.db" \
     "SELECT file_path, name FROM nodes WHERE file_path LIKE '%unicounterStk%' LIMIT 30;"
   ```
   > ⚠️ 图谱数据实际在 `~/.cache/codebase-memory-mcp/*.db`，项目目录 `.code-review-graph/graph.db` 不存在（2026-10-20 实测）；两处路径均可尝试。

### 结论口径
| 情况 | 允许写法 |
| :--- | :--- |
| 四步兜底全未命中 + 系统有图谱 | 「图谱检索未定位到精确代码」+ 明确列出已试过的检索词/功能号（**严禁写「本地无图谱」**） |
| 系统本身无图谱（`djgl`/`ssjs`/`jzyy`） | 「本地无图谱，待开发确认」 |
| 定位到真实代码 | 挂 file:// 链接 + 行号，写入溯源映射表 |
