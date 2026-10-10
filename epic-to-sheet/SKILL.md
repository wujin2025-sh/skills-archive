---
name: epic-to-sheet
description: 国泰海通史诗（PG202204-xxxx / E 开头）下辖需求同步到腾讯文档「需求跟踪」在线表格：新增需求自动追加新行，已有需求内容变化仅增量更新差异列，内容无变化零写入（幂等）。输入史诗编号或需求号列表即可全链路自动完成：
  史诗取数 → kjptai 查详情 → 读表比对（新增/差异/无变化三分类）→ set_range_value 追加+增量更新 → D 列 set_link 超链接 → 回读验证。 支持 --demands
  指定需求号快速路径（跳过史诗统计）。 触发词：史诗追加表格、史诗需求追加、按史诗追加到在线文档、把史诗下的需求追加到腾讯文档、 epic-to-sheet、PG202204-xxxx
  追加需求、史诗下需求写表格、追加需求到需求跟踪、同步史诗需求到表格。
disable: false
---

# epic-to-sheet：史诗下需求追加到腾讯文档「需求跟踪」表

## 适用场景
用户希望把某史诗（如 PG202204-0313）下的全部需求同步到在线表格（含超链接）：
**新增需求自动追加新行；史诗下已有需求内容发生变化（如排期/评审状态/关联系统/描述调整）仅增量更新差异列；
内容未变化零写入（幂等，可反复执行）**。典型目标表：
https://docs.qq.com/sheet/DS2hBcE5hVWpJdXJs?tab=BB08J2「需求跟踪」。

## 前置依赖
- **kjptai MCP**：`~/.workbuddy/mcp.json` 中 kjptai 服务器配置（Bearer token 有效）
- **腾讯文档 MCP**：`~/.mcporter/credentials.json` token（供 `scripts/td_mcp.py` 使用，走 macOS 系统代理直连 docs.qq.com）
- **epic-statistics + wide-table-query**（仅 `--epic` 取史诗下需求清单时需要；`--demands` 路径不需要）

## 一键执行
```bash
cd ~/.chat/skills/epic-to-sheet/scripts

# 方式一：按史诗（自动取史诗下需求清单）
python3 epic_to_sheet.py --epic PG202204-0313 --dry-run   # 先干跑确认
python3 epic_to_sheet.py --epic PG202204-0313             # 正式追加

# 方式二：直接指定需求号（快速路径，忽略史诗统计）
python3 epic_to_sheet.py --demands R2609090038,R2609090040,R2609090045

# 其他表格：--file DS2hBcE5hVWpJdXJs --sheet BB08J2（默认即「需求跟踪」）
# 已存在强制重写：--force（默认跳过已存在）
# 史诗下刚新增需求时，必须加 --fresh 强制重导出需求清单（否则 epic_stats 缓存不会出现新需求）
python3 epic_to_sheet.py --epic PG202204-0313 --fresh --dry-run   # 史诗新增需求后首选
```

脚本全流程输出 5 步：`[1] 需求清单 → [2] kjptai 详情 → [3] 读表格比对 → [4] 新增/更新/跳过三分类 → [5] 回读验证`。
`[4]` 输出三类：`+ 新增行` / `~ 行N: 差异列→新值（更新）` / `无变化跳过 N 条`。
**建议流程**：先 `--dry-run` 展示新增与差异明细，确认后再正式执行（写入会改动线上表）。

## 「需求跟踪」表列口径（19 列，0-based 0-18）

| 列(0-based) | 表头 | 取值来源/口径 |
|-----------|------|--------------|
| 0 | 提出日期 | `detail.createTime` → `YYYY/M/D`（如 `2026/9/9`） |
| 1 | 优先级 | `detail.priority`；**P4 →「一般紧急」**（对齐表内既有 QFII 行），其余 P 值保留原样待人工确认 |
| 2 | 史诗 | `detail.epicName`（如 `CX-业务-个微QFII两融1`） |
| 3 | 需求链接 | `https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId=Rxxx&templateId=8888&flag=1`；**必须用 `set_link` 设超链接**（纯文本 URL 不可点击） |
| 4 | 需求名称 | `detail.summary`（平台全称含【】前缀，保留以区分新旧版本） |
| 5 | 需求描述 | markdown「### 描述」段 HTML→纯文本，保留「一、需求背景/二、需求内容」双段 |
| 6 | 关联系统 | 评审纪要「**改造范围**」项提取（如「低延时交易系统(两融创新域)」）；可补参数中心等 |
| 7 | 对应负责人 | 默认空 |
| 8 | 是否有依赖关系 | 评审纪要「联测涉及系统/关联需求」提取（S180 字典、复刻关系等），默认空 |
| 9 | 计划排期 | 评审「预计上线日期」→ `YYYYMMDD`（未给具体日补 `01`，如 20261201） |
| 10 | 评审状态 | 评审纪要「通过/待评审」 |
| 11 | 个微是否需要改 | 默认空，Claude 参考既有行风格（`不需要/待定/需要，新建需求`）判断填写 |
| 12-17 | 大集中* 系列 | 默认空（本次典型场景改低延时节点，不涉及大集中） |
| 18 | 是否已上线 | 默认空（未上线） |

## 幂等与差异同步（三态）
- **新增**：表格中无此需求号 → 追加新行（A-T 19 列 + D 列超链接）。
- **更新**：已有需求 → 仅比对 10 列**脚本管控列**（提出日期/优先级/史诗/需求名称/需求描述/关联系统/
  是否有依赖关系/计划排期/评审状态/灰度升级是否影响），有差异**只增量更新差异列**，并打印 `~ 行N: 列→新值`。
- **无变化**：10 列全部一致 → 零写入跳过（输出 `全部已存在且内容无变化，无需写入。`）。
- **人工维护列永不覆盖**：对应负责人/个微是否需要改/大集中系列/是否已上线 由人工维护，脚本不比对不写入；
  需求链接（D 列）基于需求号固定，仅缺失时补设。
- 比对忽略空白差异（`\r\n`/空格/全角空格做归一化），避免富文本换行导致误判。
- `--force`：已存在需求也强制同步全部管控列（人工列仍不覆盖）；`--dry-run` 只展示计划不写入。
- `--fresh`（仅 `--epic`）：强制 epic_stats 重导出需求清单。**史诗刚新增需求时必加**（epic_stats 默认走缓存，新增需求不会出现在清单中）。
- 重复执行安全：内容无变化时重复运行零写入（幂等）。

## 关键经验与坑（务必遵循）
1. **kjptai 必须内网直连**：macOS 系统代理（172.16.0.11:3128）对 `fintech.gtht.com.cn` 会隧道 502 →
   `requests.Session().trust_env=False` 直连（`kjptai_mcp.py` 已内置）。
2. **腾讯文档必须走系统代理**：`docs.qq.com` 是外网，直连超时；`td_mcp.py` 已内置代理适配。
3. **D 列超链接**：`set_range_value` 写入 URL 只是文本，**必须再调 `sheet.set_link`**（display_text 与既有行一致=完整 URL）。
4. **描述/纪要提取**：HTML→纯文本后要剔除 `**` 粗体标记，否则「改造范围/预计上线日期」正则匹配失败。
5. **行号**：0-based（表头=0），追加起始行 = 最后有数据行 + 1；`get_cell_data` 用 `return_csv=true` + `csv.reader` 解析（单元格内换行不影响）。
6. **富文本描述**：`query_requirement` 返回 `data.markdown` 含完整渲染（需求表格 + ### 描述 + ### 需求评审会议纪要），比直接拼 HTML 更稳定。
7. **三态同步语义**：新需求只追加；已存在仅按差异列增量更新（`patch_rows` 跳过空值，避免误清空）；
   无差异零写入。人工维护列（对应负责人/个微/大集中系列/是否已上线）永远不覆盖。
8. **比对归一化**：单元格与期望值先 `norm_cell`（去掉所有空白）再比较，防止 `\r\n`/全角空格导致的误判；
   需求号优先从 D 列链接提取（`demandId=Rxxx`），整行扫描兜底（R+8 位数字）。
9. **epic_stats 缓存**：`fetch_epic_demands` 默认走 epic_stats 缓存（秒级），**史诗刚新增需求时缓存不会出现新需求**，
   必须 `--fresh` 强制从大宽表重导出（约 1-2 分钟，自动转后台等待）。

## 脚本构成（scripts/）
- `epic_to_sheet.py` — 主编排（三态同步：新增追加 / 差异增量更新 / 无变化跳过；--epic / --demands / --file / --sheet / --dry-run / --force；核心函数 diff_row/patch_rows/build_index）
- `kjptai_mcp.py` — kjptai MCP 客户端（命令行 `python3 kjptai_mcp.py query_requirement '{"demandId":"Rxxx"}'` 可单发调试）
- `td_mcp.py` — 腾讯文档 MCP 客户端（模块级 `call_tool`）

## 失败降级
- epic_stats.py 不存在或超时 → 提示用户改用 `--demands Rxxx,Rxxx` 直接给需求号。
- kjptai 查询失败 → 用 Claude 侧 `use_mcp_tool`（server_name='kjptai'，tool_name='query_requirement'）兜底，
  将详情 `data.markdown`/`data.detail` 存入缓存 JSON，再让脚本 `--demands` 跳过查询（当前版本未实现缓存注入，直接人工补行）。
- 腾讯文档写入失败 → 检查 `~/.mcporter/credentials.json` token 是否过期、系统代理是否可用。
