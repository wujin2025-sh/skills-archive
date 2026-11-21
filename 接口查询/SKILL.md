---
name: 接口查询
description: '接口配置查询（fwzl-mcp 优先）。通过服务治理 MCP（fwzl-mcp，端点 sg.gtht.com.cn）按功能号/接口名/关键字查询接口契约：存在性、基本信息（功能号/名称/所属系统/负责人）、出入参明细（IN/OT/HD）、调用链（上下游）。fwzl-mcp 未命中或不可用（401/403/网关不可达）时才回退到本地脚本兜底。

  触发词：接口查询、查询接口、低延时接口查询、interface-query、7300780、7300780接口、interfaceManage、文件接口、功能号、接口号、接口字段、服务治理接口、fwzl。'
agent_created: true
disable: false
---

# 接口查询 (fwzl-mcp 优先 · Service-Governance-First)

查询指定**功能号 / 接口号 / 关键字**的接口契约与字段明细，输出 Markdown 表格。

---

## 0. 查询策略（重要）

**默认首选服务治理 MCP（`fwzl-mcp`），无浏览器、无登录态、返回结构化 JSON。**
`fwzl-mcp` 端点为 `https://sg.gtht.com.cn/api/v1/mcp/byApplication/fwzlMcpServer/mcp`，
正是服务治理平台的 MCP 网关，直接替代原先 Playwright 浏览器自动化查询（更轻、更快、字段粒度更细）。

| 层级 | 数据源 | 说明 | 何时使用 |
| --- | --- | --- | --- |
| **M（主）** | `fwzl-mcp`（服务治理 MCP） | 服务治理平台网关，按功能号/关键字查契约 | **默认首选** |
| **F（兜底）** | 本地脚本 `interface_query.py` | 本地 SQLite 库 + 服务治理平台 Playwright 自动化 | 仅当 fwzl-mcp **不可用/未命中** |

> 🔻 **处置规则**：
> - 本技能执行时，**优先直接调用 `mcp__fwzl-mcp__*` 工具**，不要先起浏览器。
> - 若 fwzl-mcp 调用报 **401/403**（鉴权失败）、网关不可达、或工具未加载，
>   才回退到 **F 兜底**（本地脚本 `interface_query.py`，见 §4）。
> - 两者都查不到时，如实向用户汇报「服务治理 MCP 与本地兜底均未命中」结论，
>   并在「需求补充说明」标注，不进接口缺失审计。

---

## 1. 通过 fwzl-mcp 查询（主路径）

直接调用 `fwzl-mcp` 命名空间的 MCP 工具（调用形式 `mcp__fwzl-mcp__<tool>`）。

### 可用工具总览

| 工具 | 用途 |
| --- | --- |
| `functionQueryServiceByKeyWord({keyWord})` | **判定接口存在性**，返回功能号/类型/名称/系统/负责人/请求方式（**主判据**） |
| `functionQueryServiceBySystemName({systemName})` | 按系统名批量查功能号 |
| `queryServiceParameterByFuncCode({funcCode})` | 取 IN/OT/HD 出入参明细（paramName/paramType/paramDesc） |
| `queryMSServiceParameterByFuncCode({funcCode})` | 取微服务结构体出入参明细（serviceName/methodName/inParamType） |
| `queryParentFunction({funcCode})` | 查上游（父）调用链 |
| `queryChildFunction({funcCode})` | 查下游（子）调用链 |
| `queryServiceIdlByFuncCode({funcCode})` | 查 Maven 依赖（groupId/artifactId/version） |
| `serviceManage-queryFunction({funcCode})` | 功能号接口信息（含出入参）；**可能报 Gson 解析错**（`Expected BEGIN_ARRAY but was STRING`），此时直接改走 `queryServiceParameterByFuncCode` |
| `serviceMD-queryGuide({funcCode})` | 指引手册 Markdown（**仅作说明**，不作存在性判据） |

### 标准查询流程

```text
① 判定存在性   mcp__fwzl-mcp__functionQueryServiceByKeyWord({keyWord: <功能号/名称/关键字>})
              → 有返回即存在；功能号/类型/所属系统/负责人/请求方式 → 供「系统交互」引用

② 取出入参      mcp__fwzl-mcp__queryServiceParameterByFuncCode({funcCode: <功能号>})
              → IN 入参 + OT 出参 + HD 头部明细（paramName/paramType/paramDesc）
              → 可能需再查 queryMSServiceParameterByFuncCode 取微服务结构体字段

③ 调用链       mcp__fwzl-mcp__queryParentFunction({funcCode})  上游
              mcp__fwzl-mcp__queryChildFunction({funcCode})    下游
              → 功能号/类型/名称/系统/请求方式 → 供「系统交互」链路描述

④（可选说明）  serviceMD-queryGuide({funcCode}) 指引手册；serviceManage-queryFunction 含出入参（可能 Gson 报错）
              queryServiceIdlByFuncCode 查 Maven 依赖
```

> ⚠️ **凭证值形如「Bearer Token / 工号」「¥0」也正常**：
> `queryServiceParameterByFuncCode` 返回的 `defaultValue` 字段可能含 `登录后送`、`返回给股民`、
> 字典码（`Emmlb`/`Ajysall`/`Z000002` 等）或描述符，并非具体实测值，用途是契约语义而非采样值。

### 预算控制

- 单需求/单功能号查询 **≤3 次 fwzl-mcp 调用**（存在性 1 + 出入参 1 + 调用链 1，最多加 1 次系统批量）。
- 不反复试探同一功能号；来回失败时直接降级到 §4 兜底。

### 结果处理

- **命中**：功能号 / 名称 / 类型 / 所属系统 / 负责人 / 出入参 / 上下游调用关系 → 供需求文档「系统交互」章节引用。
- **字段缺失或不匹配**：接口存在但字段对不上 → 记入审计清单。
- **未查到**（工具返回空 / 业务级「指引手册不存在」等）→ 标注「服务治理 MCP 未收录」，不反证接口不存在。

---

## 2. fwzl-mcp 命名空间与鉴权说明

- 命名空间：`fwzl-mcp`（调用 `mcp__fwzl-mcp__*`）。
- 端点：`https://sg.gtht.com.cn/api/v1/mcp/byApplication/fwzlMcpServer/mcp`（远程 streamable_http）。
- **鉴权**：截至目前该端点**无需额外鉴权 header 即可访问**（探测返回业务级响应而非 401/403）。
  若后续某 agent/会话内调用返回 401/403，说明该运行环境要求补 header，把报错反馈给用户，
  由其补齐 `X-Platform-Id` / `Authorization` / `X-Api-Key` 之一后刷新再查。
- **生效前提**：`fwzl-mcp` 需在 AILink **AI能力中心 → 连接器**中已启用并刷新；
  未加载时 `mcp__fwzl-mcp__*` 工具不可用，直接走 §4 兜底。

---

## 3. 输出模板

```markdown
## 📄 接口基本信息
| 项 | 值 |
|----|----|
| 功能号 | <funcCode> |
| 功能名称 | <funcName> |
| 功能类型 | <funcType> |
| 所属系统 | <sysName> |
| 负责人 | <authorName>（<authorCode>） |
| 请求方式 | <requestMode> |

## 📥 入参（IN）
| 参数 | 类型 | 说明 | 必填 | 字典 |
|------|------|------|------|------|
| <paramName> | <paramType> | <paramDesc> | 选/必 | <dictCode> |

## 📤 出参（OT）
...同上...

## 🔗 调用链
上游：<queryParentFunction 列表>；下游：<queryChildFunction 列表>
```

---

## 4. 兜底查询（fwzl-mcp 不可用 / 未命中时）

仅当 fwzl-mcp **不可用**（401/403、网关不可达、工具未加载）或**未命中**时才启用本地脚本兜底。
本地脚本保留原有 本地毫秒级库 + 服务治理平台 Playwright 自动化 能力。

```bash
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python \
  /Users/wujin/.workbuddy/skills/接口查询/scripts/interface_query.py <关键字>
```

| 参数 | 说明 |
| --- | --- |
| `-s, --source` | `local`(仅本地) / `web`(强制平台) / `auto`(本地未命中才升级平台) |
| `--json` | 结构化输出 |
| `-n` | 平台查询显示浏览器界面 |
| `-g <分组>` | 平台按系统分组过滤（如 `低延时,集中交易`） |

> ⚠️ 本地兜底依赖外置盘 `/Volumes/Macintosh HD_Data` 与 `~/.workbuddy` 相关脚本；
> 外置盘未挂载时本地库不可用（退出码 11），直接走 `--source web` 平台查询，
> 或回到主路径排查 fwzl-mcp。详见脚本自带 `-h`。

---

## 5. 目录结构

```
接口查询/                       ← 本技能
├── SKILL.md                    ← 本文件（fwzl-mcp 优先策略）
└── scripts/
    ├── interface_query.py      # 兜底统一查询路由器（本地库 + Playwright 平台）
    ├── build_interface_cache.py# 由源 xlsx 重建本地库（源数据更新时用）
    ├── build_funcid_index.py   # 功能号注册表索引编译（源码更新时用）
    ├── low_latency_query.py    # Playwright 服务治理平台查询（被兜底路由器按需调用）
    ├── query_fast.py           # 旧版极简查询（兼容保留）
    ├── query_interface.sh      # 旧版 shell 入口（兼容保留）
    └── config.json             # 平台账号与登录配置（兜底用）
```

**约定**：本技能脚本位于 SKILL 目录 `scripts/` 自包含运行；`需求分析` 目录仅作数据源被读取。
所有脚本统一用 `/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python` 运行。