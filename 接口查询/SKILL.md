---
name: 接口查询
description: '接口配置查询。优先从本地接口知识库 (/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/rules-raw/.interface_store.db) 毫秒级查询实时接口与文件接口（含完整字段明细）；本地未命中时再回退到金融科技服务治理平台 (sg.gtht.com.cn) 在线查询；平台仍查不到时最后通过代码知识图谱（CBM）做源码级兜底（验证接口号/功能号是否存在于低延时/集中交易/集中清算等系统代码）。

  触发词：接口查询、查询接口、低延时接口查询、interface-query、7300780、7300780接口、interfaceManage、文件接口、功能号、接口号、接口字段。'
agent_created: true
disable: false
---

# 接口查询 (本地优先 · Local-First)

查询指定**接口号 / 文件编号 / 表名 / 关键字**的接口配置与字段明细，输出 Markdown 表格。

---

## 0. 查询策略（重要）

**本地优先，禁止跳过 L1 直接联网。** 本地 SQLite 知识库覆盖 **3257 个接口 / 82421 条字段**，
毫秒级返回（约 3ms）且含完整字段明细；联网查询需启动浏览器并登录，耗时数十秒且字段粒度更粗。

| 层级 | 数据源 | 说明 | 何时使用 |
| --- | --- | --- | --- |
| **L1** | `rules-raw/.interface_store.db` | SQLite，接口元数据 + 全部字段明细 | **默认首选** |
| **L2** | `rules-raw/*.md` | 本地接口规格文档 | L1 未命中时补充 |
| **L1.5** | `rules-raw/.funcid_index.db` | 集中交易功能号注册表索引（KCBPSPD.xml 6048 功能号 + sysfunc_init.sql 功能名） | 纯数字功能号 L1/L2 未命中时**自动**兜底（免 CBM，见 §3 说明） |
| **L3** | 服务治理平台 `sg.gtht.com.cn` | Playwright 自动化在线查询 | **仅当 L1/L2/L1.5 均未命中** |
| **L4** | 代码知识图谱（CBM） | 源码级符号/编号检索（低延时/集中交易/集中清算等本地图谱） | **L1/L2/L1.5/L3 均未命中时兜底** |

### 本地资源地图

```
/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/          ← 数据源（只读，不存放本技能脚本）
└── rules-raw/
    ├── .interface_store.db          # ★ L1 主库（由本技能脚本生成）
    ├── .funcid_index.db             # ★ L1.5 功能号注册表索引（由 build_funcid_index.py 生成）
    ├── 实时接口明细/                 #   源数据：低延时/集中交易/集中清算/参数中心 xlsx
    ├── 文件接口明细/                 #   源数据：集中交易文件接口 xlsx
    ├── 文件接口明细_汇总.csv         #   文件接口汇总
    └── *.md                         # ★ L2 单接口规格文档

~/.workbuddy/skills/接口查询/          ← 本技能（脚本全部自包含）
├── SKILL.md
└── scripts/
    ├── interface_query.py            # ★ 统一查询路由器（L1→L2→L1.5→L3→L4）
    ├── build_interface_cache.py      # ★ 由源 xlsx 重建 L1 知识库
    ├── build_funcid_index.py         # ★ 由 KCBPSPD.xml + sysfunc_init.sql 编译 L1.5 功能号索引
    ├── low_latency_query.py          # L3 服务治理平台查询
    ├── query_fast.py                 # 旧版极简查询（兼容保留）
    ├── query_interface.sh            # 旧版 shell 入口（兼容保留）
    └── config.json                   # 平台账号与登录配置
```

**L1 库覆盖范围**：实时接口 2656 个（低延时 / 集中交易 / 集中清算 / 参数中心 / 交易参数管理后台系统 /
综合理财账户系统 等）、文件接口 601 个。`code` 唯一，可直接按接口号精确命中。

> **脚本归属约定**：本技能所有脚本均位于 SKILL 目录下 `scripts/`，**不依赖** `需求分析` 目录下的任何脚本。
> `需求分析` 目录仅作为**数据源**被读取。数据源路径可用环境变量 `INTERFACE_BASE_DIR` 覆盖。

---

## 1. 快速使用

### 标准查询（推荐）

```bash
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python \
  /Users/wujin/.workbuddy/skills/接口查询/scripts/interface_query.py <关键字>
```

```bash
# 实时接口（数字功能号；本地库未收录的纯数字功能号自动走 L1.5 功能号索引，见 §3）
interface_query.py 7300780
interface_query.py 121335

# 文件接口（字母编号）
interface_query.py T13 A51 L28

# 关键字模糊搜索
interface_query.py 展期
interface_query.py credittargetstk

# 多关键字混合
interface_query.py T13 7390704 A51

# 本地未命中 → 自动升级服务治理平台（L3 也查不到 → 续接代码知识图谱兜底，见 §3）
# ⚠️ 本地库未收录的纯数字功能号（如 121335）会先自动命中 L1.5 功能号索引，不再误报未命中
interface_query.py 9999999 --source auto

# 强制走平台（跳过本地）
interface_query.py 7300780 --source web

# 结构化输出（便于二次加工）
interface_query.py 420662 --json
```

### 参数说明

| 参数 | 说明 |
| --- | --- |
| `keywords` | 接口号 / 文件编号 / 表名 / 关键字，支持多个（位置参数） |
| `-t, --type` | `any`(默认，按输入自动推断) / `realtime` / `file` |
| `-s, --source` | `local`(默认，仅本地) / `web`(强制平台) / `auto`(本地未命中才升级平台) |
| `--no-fields` | 不输出字段明细，只出接口基本信息 |
| `--no-md` | 跳过 L2 本地 Markdown 检索 |
| `--no-web` | 禁止联网升级（本地未命中时以退出码 10 返回） |
| `--limit N` | 模糊查询返回上限，默认 40 |
| `--json` | 输出 JSON |
| `-n, --no-headless` | 平台查询时显示浏览器界面，便于人工查看详情 |
| `-g, --groups` | 平台查询按所属分组过滤，逗号分隔（如 `低延时,集中交易`） |

### 退出码约定（供上层编排判断）

| 退出码 | 含义 | 上层动作 |
| --- | --- | --- |
| `0` | L1/L2/L1.5 命中，**无需联网** | 直接使用输出 |
| `10` | L1/L2 未命中 | 追加 `--source auto` 升级 L3 平台查询 |
| `11` | 本地资源不可用（DB 缺失 / 外置盘未挂载） | 走 L3 平台查询 |

> 🔻 **L4 兜底**：L3 平台查询**仍查不到**时，续接代码知识图谱（CBM）源码级检索（见 §3），
> 可确认接口号/功能号是否存在于相关系统代码；全部检索完成后才向用户汇报「三库 + 源码均未命中」结论。

---

## 2. 升级到服务治理平台（L3）

本地库无该接口时（多为近期新增接口），才走平台在线查询：

```bash
# 自动降级链：先本地，未命中自动升级
interface_query.py <关键字> --source auto

# 平台查询带界面（自动展开详情弹窗）
interface_query.py <关键字> --source auto -n
```

底层复用 `low_latency_query.py`（Playwright + Chrome），配置见 `scripts/config.json`。
Session 缓存在 `~/.workbuddy/skills/uat_accept/scripts/.fintech_session.json`，首次运行需登录。

> ⚠️ 外置盘 `/Volumes/Macintosh HD_Data` 未挂载时 L1/L2 不可用（退出码 11），此时直接走 L3。

---

## 3. 代码知识图谱兜底（L4）

**适用场景**：L1 本地库、L2 本地文档、L3 服务治理平台**均未命中**时（多为未登记平台的内部功能号/源码常量），
通过代码知识图谱（codebase-memory-mcp，CBM）做源码级兜底，验证接口号/功能号是否存在于相关系统代码。

### CBM 项目名映射（`cli list_projects` 可复核）

| 系统简称 | 系统标准名称 | CBM CLI 项目名 | 图谱规模 |
| --- | --- | --- | --- |
| `jzjy` | 集中交易系统 | `Volumes-Macintosh-HD_Data-Project-jzjy-spbsrc` | ~38 万节点 |
| `dys` | 低延时交易系统 / 低延时交易系统（创新域） | `Volumes-Macintosh-HD_Data-Project-dys-branches-master-tree` | ~6.5 万节点 |
| `jzqs` | 集中清算系统 | `Volumes-Macintosh-HD_Data-Project-jzqs-src-src` | ~42 万节点 |
| `cszx` | 交易参数管理后台系统 | 无图谱，sqlite 直连降级 | 🟡 |

### 兜底检索命令

```bash
# 1) 文件/符号定位（按接口号/关键字检索，过滤 info 日志）
/Users/wujin/.local/bin/codebase-memory-mcp cli search_graph \
  --project <CBM项目名> --query <接口号/关键字> --limit 20 --format tree 2>&1 | grep -v "level=info"
# 或按文件名模式匹配
/Users/wujin/.local/bin/codebase-memory-mcp cli search_graph \
  --project <CBM项目名> --file-pattern <文件名.cpp> --limit 20 2>&1 | grep -v "level=info"

# 2) 命中后回读源码片段（qualified-name 取 search_graph 输出的完整 qn）
/Users/wujin/.local/bin/codebase-memory-mcp cli get_code_snippet \
  --project <CBM项目名> --qualified-name <完整QN> --include-neighbors
```

> ⚠️ CBM CLI 不可用时降级 sqlite 直连（文件级检索必须用 `file_path LIKE '%文件名%'`，`name` 列仅存函数/类名；
> 图谱库真实位置在 `~/.cache/codebase-memory-mcp/*.db`，项目目录下 `.code-review-graph/graph.db` **不存在**；cszx 无图谱）：
>
> ```bash
> sqlite3 "$HOME/.cache/codebase-memory-mcp/Volumes-Macintosh-HD_Data-Project-{jzjy-spbsrc|dys-branches-master-tree|jzqs-src-src}.db" \
>   "SELECT file_path, name, label FROM nodes WHERE file_path LIKE '%关键字%' LIMIT 30;"
> ```

> ⚠️ **结论口径**：图谱检索仅能证明「代码中存在该编号/符号」（佐证接口存在或功能号使用位置），
> 字段明细、入参出参仍以平台/本地库为准；不确定涉及哪个系统时，低延时 / 集中交易 / 集中清算三个项目并行检索。

> 🔴 **纯数字功能号盲区（121335 实测来源，已由 L1.5 索引自动补偿）**：图谱符号级索引（`nodes_fts` 仅覆盖
> name/qualified_name/label/file_path，内容来自 Tree-sitter AST 符号节点）对**整数常量、行注释、XML 属性值、SQL insert 值**
> 一律不建索引——功能号以 `nFuncid == 121335` / `//121335` / `name="121335"` / `insert ... 121335` 形式出现时，
> `search_graph` 与 FTS 均检索不到（**非图谱损坏**，382 万级节点库亦如此）。
> **补偿措施（2026-10-20 落地）**：`interface_query.py` 对纯数字功能号在 L1/L2 未命中时**自动查询 L1.5 功能号注册表索引**
> （`.funcid_index.db`，由 `build_funcid_index.py` 从 KCBPSPD.xml 6048 功能号 + sysfunc_init.sql 功能名编译），
> **毫秒级直接命中**并输出 功能名/模块/DLL/类型/缓存/用户出口，无需再手动 grep。索引库缺失时（如外置盘未挂载），仍按源码 grep 反查：
> ```bash
> grep -rn "121335" "/Volumes/Macintosh HD_Data/Project/jzjy/spbsrc" \
>   --include=*.cpp --include=*.h --include=*.hpp --include=*.xml --include=*.sql 2>/dev/null | head -30
> ```
> 优先核对：`KCBPSPD.xml`（功能注册表：`name="121335"` ↔ `module=` 映射）、`sysfunc_init.sql`（功能表初始化）、
> `BusTag.h`/`*Export.h` 注释行（`//121335 功能名`）、业务实现 cpp（`nFuncid == 121335` 分支）。

---

## 4. 维护本地库

源 Excel 更新后（如从服务治理平台重新导出接口列表），重建 L1 库：

```bash
# 体检源数据（不重建，建议先跑）
python scripts/build_interface_cache.py --check

# 重建（自动备份旧库为 .interface_store.db.bak）
python scripts/build_interface_cache.py

# 指定路径 / 数据源
python scripts/build_interface_cache.py --db /tmp/if_test.db
python scripts/build_interface_cache.py --base-dir /Volumes/Macintosh\ HD_Data/WorkBuddy/需求分析
```

> ⚠️ 重建为**全量重编译**，已优化为一次性读入内存矩阵解析（避免 openpyxl 逐格 `ws.cell()` 调用），
> 耗时约 **30 秒**（源 xlsx 约 4MB）。旧库自动备份为 `.interface_store.db.bak`，可随时回滚。

### 功能号索引（L1.5）维护

`interface_query.py` 对纯数字功能号的 L1.5 兜底依赖 `rules-raw/.funcid_index.db`。
当集中交易源码（KCBPSPD.xml / sysfunc_init.sql）更新时重建：

```bash
python scripts/build_funcid_index.py            # 重建（旧库自动备份 .bak）
python scripts/build_funcid_index.py --check    # 仅体检数据源，不建库
python scripts/build_funcid_index.py --spbsrc <集中交易源码根路径>
```

**当前状态**：6048 个功能号（含功能名 5465 个），例如 `121335` = 单客户货币资产查询 /
`unictrCustFundAssetQry` / `lbm_unicounter.dll`。查询时毫秒级命中（约 5-60ms）。

### 数据质量约定

- **模板表头过滤**：解析 Excel 时会混入「场景名称 / 子场景名称 / 示例描述」模板表头行（曾影响 2657 行 / 2656 个接口）。
  `build_interface_cache.py` 已在**解析阶段源头过滤**，重建后残留为 0；
  `interface_query.py` 另有**输出阶段兜底过滤**（兼容旧库），输出中以「已自动过滤 N 行」提示。
- **字段缺失**：极少数接口无字段明细（实时接口 2 个、文件接口 3 个），输出会提示
  「本地库未收录该接口的字段明细」，此时若需字段应升级 L3 平台查询。
- **系统名变体**：清算系统存在 `集中清算` 与 `集中清算系统` 两种写法，按系统名过滤时需兼容两者。

**当前库状态**：3257 接口（实时 2656 / 文件 601）、82421 字段、脏数据 0 行，查询耗时约 3ms。

---

## 5. 目录结构与脚本归属

```
接口查询/
├── SKILL.md
└── scripts/
    ├── interface_query.py            # ★ 统一查询路由器（L1→L2→L1.5→L3→L4）—— 日常查询入口
    ├── build_interface_cache.py      # ★ 由源 xlsx 重建 L1 知识库 —— 仅源数据更新时使用
    ├── build_funcid_index.py         # ★ 由 KCBPSPD.xml + sysfunc_init.sql 编译 L1.5 功能号索引 —— 源码更新时使用
    ├── low_latency_query.py          # L3 服务治理平台查询（被路由器按需调用，也可单独跑；L4 走 CBM CLI）
    ├── query_fast.py                 # 旧版极简查询（兼容保留，功能已被路由器覆盖）
    ├── query_interface.sh            # 旧版 shell 入口（兼容保留）
    └── config.json                   # 平台账号与登录配置
```

**约定**：技能脚本一律放在本 SKILL 目录下自包含运行，不引用 `需求分析` 目录下的脚本；
`需求分析` 仅作为数据源被读取。所有脚本统一使用
`/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python` 运行。
