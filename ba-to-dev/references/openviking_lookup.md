# OpenViking 业务知识库检索指南 (OpenViking Lookup Reference)

本文档为 `ba-to-dev` 技能的 **OpenViking 业务知识库检索** 专项参考，与 [`graph_lookup.md`](file:///Users/wujin/.chat/skills/ba-to-dev/references/graph_lookup.md)（代码知识图谱）、[`db_lookup.md`](file:///Users/wujin/.chat/skills/ba-to-dev/references/db_lookup.md)（数据库）配套使用，构成 **三域知识检索闭环**。

**核心理念**：知识图谱回答「代码怎么写的」，数据库回答「数据/参数实际是什么」，OpenViking 回答「**交易所业务规则与既有需求上下文是什么**」。撰写**第三章技术实现**与**评审纪要**前，先用 OpenViking 检索业务规则原文、既有需求/方案/用例，校准业务口径与边界，**杜绝大模型凭空推断交易所规则或业务语义**。

---

## 1. OpenViking 是什么

- 火山引擎开源的 Agent 上下文数据库（Agent Context Database），GTHT 内部部署于 `csgl.gtht.com.cn`；
- MCP 端点：`https://csgl.gtht.com.cn/openviking/server/mcp`，鉴权头 `X-Api-Key`（`Authorization: Bearer` 亦可）；
- 内容为「需求/语料/文档」性质的内部知识库：交易所业务私域规则、历史需求原文与附件、方案设计、测试用例等。

---

## 2. 接入与调用（NO_PROXY 是硬前提）

调用脚本（已内置鉴权 Key）：`/Users/wujin/.workbuddy/skills/openviking-query/openviking_mcp.py`

```bash
PY=/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python
SCRIPT=/Users/wujin/.workbuddy/skills/openviking-query/openviking_mcp.py

# ⚠️ NO_PROXY 必须设置：Python urllib 直连内网地址默认走代理，会握手失败（返回 None/超时，2026-11-01 实测）
export NO_PROXY="csgl.gtht.com.cn,fintech.gtht.com.cn"
export no_proxy="csgl.gtht.com.cn,fintech.gtht.com.cn"

# 语义检索（先粗筛相关文档，返回带摘要的 Top15）
$PY $SCRIPT find "担保品返还"
# 列目录（先看清资源结构，glob 前必做）
$PY $SCRIPT list "viking://resources/"
# 按文件名通配（务必限定在某个 resource 内，全库 glob 易超时）
$PY $SCRIPT glob "**/*担保品*" "viking://resources/行业测试大模型语料库/深交所.zip/"
# 读正文（read 支持多个 URI，逗号分隔）
$PY $SCRIPT read "viking://resources/行业测试大模型语料库/深交所.zip/深交所/业务私域文件/融资融券系统/担保品划转/.overview.md"
```

> 🚀 **已在 WorkBuddy 连接器启用时**（MCP 工具 `mcp__openviking__*` 已加载），可直接走 `use_mcp_tool` 调用同名工具（find/list/glob/read），免 NO_PROXY 环境变量问题；未启用时一律用上述脚本。

---

## 3. 命令速查与真实输出示例

| 子命令 | 用途 | 典型输出 | 注意事项 |
| :--- | :--- | :--- | :--- |
| `find <语义词>` | 跨库语义检索（Top15） | `- [resource 86%] viking://resources/.../<文件>.md` + 摘要 | 偏向高频近义词，「按文件名找」请用 glob |
| `list <uri>` | 列目录 | `[dir] 深交所.zip` / `viking://resources/...` | **glob 前必做**，用于定位资源名 |
| `glob <pattern> <uri>` | 限定资源内文件名通配 | `Found 17 file(s): viking://resources/...` | **严禁不限资源全局 glob**（chunked 超时） |
| `read <uri>` | 读文档正文 | 文档 Markdown 全文（可多 URI 逗号分隔） | 目录级别 read 返回 `.overview.md` |

**实测示例**（`find "担保品返还"`，2026-11-01）：
```
- [resource 86%] viking://resources/requirement.zip/合规风控/统一监管报送平台/.../回购类别明细表_2.md
- [resource 85%] viking://resources/行业测试大模型语料库/深交所.zip/深交所/业务私域文件/融资融券系统/担保品划转/.overview.md
- [resource 85%] viking://resources/行业测试大模型语料库/深交所.zip/深交所/业务私域文件/融资融券系统/担保品买卖/.overview.md
...
Use the read tool to expand a URI.
```

> ✅ 对 BA 分析最有效的路径：**`find <业务概念>` 粗筛 → 锁定交易所资源 → glob 限定目录精确定位 → read 读规则/用例正文**，将「担保品返还」这类业务词命中到 `深交所/业务私域文件/融资融券系统/担保品划转/业务用例文档/` 的真实规则文档。

---

## 4. 资源全景与检索路径

| 资源（`viking://resources/`） | 内容 | 适用场景 |
| :--- | :--- | :--- |
| **`行业测试大模型语料库/`** | **六大交易所/股转业务私域知识**：`深交所.zip` `上交所.zip` `北交所.zip` `深港通.zip` `沪港通.zip` `股转.zip`（各含业务私域文件，如 `融资融券系统/担保品划转`、`集中交易系统/债券赎回`…） | ⭐ **交易所业务规则原文、业务用例、测试用例**——两融/质押/回购/ETF 等需求涉及交易所规则时首选 |
| **`requirement.zip/`** | 历史需求归档：`财富管理_xxx.zip` `机构与交易_xxx.zip` `营运_xxx.zip` `信用` `合并专属` | **同类/前序需求原文与附件**（如算法策略、监管报送、数据接口规范） |
| **`科技平台需求知识-20260622.zip`** | 科技平台需求知识库 | 需求知识/条目检索 |
| **`交易结算创新`** | 交易结算创新方案 | 创新域/前瞻性方案参考 |
| **`方案设计_账户新一代OTC账户相关改造需求设计_V1.1`** | 账户/OTC 方案设计 | OTC 账户类需求 |
| **`2026年6月份周末测试文档`** | 周末测试相关文档 | 测试相关需求 |

> 资源列表以 `list "viking://resources/"` 实际返回为准（可能随版本更新增删）；本文档为 2026-11-01 快照。

---

## 5. 检索 → 分析 → 落盘闭环（三域协同）

**触发时机（P0 第 18 条）**：撰写**第三章技术实现**与**评审纪要**前，先完成三域检索，让检索结论带着证据进入分析上下文。

```
① OpenViking（业务规则域）    find/glob/read 交易所规则原文、既有需求/方案、用例
        ↓ 校准「做什么/为什么」：规则口径、业务边界、触发条件
② 知识图谱（代码域）          CBM 定位真实函数/模块/表名（graph_lookup.md）
        ↓ 校准「在哪改/怎么改」：改造点、数据结构
③ 数据库（数据域）            调用「数据库查询」SKILL（/db-schema-query，dbq <profile>）验证表结构/参数当前值/字典中文名（db_lookup.md）
        ↓ 校准「数据/参数实际值」：影响面、参数默认值
④ 落盘「三、技术实现」+「评审纪要」：检索证据按章融入
```

**证据融入规范**：
1. **交易所规则原文**：定位到规则直接引用原文编号（如《深圳证券交易所融资融券交易实施细则》第 X 条），写入第三章核心业务逻辑与第五章知识积累「交易规则」小节，并在评审纪要【业务关注点】用业务语言体现规则约束；
2. **既有需求/方案**：同类需求口径、历史方案决策（写入「相关链接」或第五章知识积累「跨系统数据链路」）；
3. **检索不到/命中噪声**：归一化写「(具体规则口径以业务确认为准)」，**严禁凭记忆编造规则条文与表名**（P0 第 1 条绝对忠于事实同样适用）；
4. **评审纪要业务化**：openviking 检索到的规则/用例结论在评审纪要中一律用业务语言表达，**技术细节（表名/函数/接口号）仅置第三章**（P0 第 4 条铁律）；
5. **熔断红线（P0）**：openviking 检索失败（超时/网络/NO_PROXY 遗漏）**不得阻塞落盘**——至多 2~3 轮检索即收敛，命中即止，未命中按规范标注后继续产出 md（与溯源熔断同源，见 SKILL P0 第 16 条）。

---

## 6. 踩坑记录（2026-11-01 实测沉淀）

1. **NO_PROXY 遗漏 → 握手失败**：Python urllib 直连内网地址默认经系统代理，`initialize` 返回 500/None（`AttributeError: 'NoneType' object has no attribute 'get'`）；必须 `export NO_PROXY="csgl.gtht.com.cn,fintech.gtht.com.cn"`（curl 不受影响，可直接 200）；
2. **全局 glob 超时**：`glob "**/*担保品*"`（不限资源）HTTP chunked 读超时；必须先 `list viking://resources/` 定位资源名，再限定 `glob <pattern> <uri>`；
3. **find 语义偏向**：`find` 是语义检索，对「上海董监高文件」这类词偏向召回「机构」等高频近义词，不一定命中文件名——按文件名找用 glob 限定资源目录最稳；
4. **乱码/无法解析**：部分 docx 附件转 md 后为乱码（`文档内容无法解析`），属语料质量问题，跳过该文件即可，不阻塞分析；
5. **目录 read 只能读 `.overview.md`**：目录级 read 返回目录概览（或「not generated」），要读具体规则正文须 glob 到叶子文件再 read。
