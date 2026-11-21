---
name: gtht-req-design-doc
description: '基于低延时/QFII 两融等专项笔记、会议纪要、常青规范与腾讯在线文档，生成券商系统总体设计文档，采用两阶段工作流（Phase1 生成 Markdown 内容草稿 → 用户评审完善 → Phase2 生成正式 .doc 文档）。支持腾讯在线文档（docs.qq.com）补充完善：用户提供链接后读取内容并提炼有价值信息补充进设计文档。Triggers: "生成设计文档"、"设计文档初稿"、"系统总体设计"、/gtht-req-design-doc、腾讯文档链接（docs.qq.com）补充完善。'
disable: false
---

# GTHT 需求设计文档生成（gtht-req-design-doc）

> **角色**：资深券商 IT 业务分析师（BA）/ 系统设计师  
> **目标**：将分散的笔记、会议纪要、常青规范与在线协作文档，综合沉淀为面向研发/测试/业务三方的**系统总体设计文档**。

---

## ⚡ 何时使用本技能

- 用户要求"生成设计文档 / 设计初稿 / 系统总体设计"，素材为**本地笔记 + 会议纪要**（非单条科技平台 `req_id` 需求驱动）。
- 用户要求"用腾讯在线文档补充/完善设计文档"，并给出 `docs.qq.com` 链接。
- **单条 `req_id` 需求文档**（一/二章需 100% 平台原文）请改用 `/ba-to-dev`，本技能专注"综合设计文档"与"在线文档补充"。

---

## 🔄 两阶段工作流

### Phase 1：生成 Markdown 内容草稿

1. **素材收集**：检索 `100_Projects/需求分析/`、`300_Resources/会议纪要/`、`200_Knowledge/` 常青规范，按主题聚合（会议纪要/规范/FAQ/参数跟踪）。
2. **文档结构**（章节式 + Mermaid 图，可据主题裁剪）：
   - 概述与背景（业务背景 / 建设目标 / 演进路线）
   - 总体架构设计（部署与节点域 / 一户两地与分仓 / 指标体系 / 系统交互拓扑 / 架构图）
   - 功能模块设计
   - 接口设计
   - 参数设计
   - 数据流转与关键规则（Mermaid 时序图）
   - 非本组负责系统（第三方/他组，仅列业务目标与责任方）
   - 待确认事项（Open Items，逐项列责任方与来源）
   - 风险与合规要点
   - 附录 · 事实来源与关联文档
3. **图表优先原则**（核心规范，Phase 1 草稿阶段执行）：
   - **能用图表则不用纯文字**：凡涉及流程/顺序/判定/拓扑/时间线/数据流/对比/矩阵/分层等结构化信息，**优先用 Mermaid 图表**替代或补充纯文字描述，让文档更直观可读。
   - **每章至少评估一次**：逐章审视内容，识别可图表化点（见下方"图表类型选择指南"），主动插入图表而非等用户要求。
   - **图表与文字互补**：图表用于直观展示结构与关系，文字用于补充细节与边界条件；图表前保留简短引导句（如"偿还顺序如下："），图表后保留必要文字说明。
   - **Mermaid 语法要求**：使用 `flowchart TD/LR/TB` 画流程/决策/拓扑；`sequenceDiagram` 画时序；统一用 `classDef` + `class` 做颜色分组（每图 2~5 色）；节点文字用 `<br/>` 换行；主数据流用 `==>` 粗箭头、辅助流用 `-->` 细箭头、虚线用 `-.->`。
4. **落盘**：`100_Projects/设计文档/<主题>系统总体设计.md`，含**修订记录表**（首行 V0.1 初稿）。
5. **标注规则**（忠于事实）：源素材未明确的系统名 / 接口号 / 表名 / 字段名，统一注 `（具体实现以研发设计为准）`；凡可澄清的待确认项汇总至"待确认事项"章节。
6. **表格注解规范**（Markdown 源文件层面）：
   - **表格阅读说明**（列标记解释、口径说明，如 `★ = QFII 设计目标模式`）→ 放表格**上方**
   - **来源/引用说明**（如 `> 来源：腾讯在线文档…`）→ 放表格**下方**（表注）
   - **章节引言式来源**（含上下文描述的 `> 来源：…`，非纯表格注解）→ 保持章节标题下方，不移动
   - 理由：读者看表前需知道列标记含义；来源出处是追溯用，看表后需要时再查
7. **标题精简规范**：章节标题保持简洁干净，**移除括号补充说明**（口径标注、数量标注、技术路径、数据流向、英文翻译、文件名等），括号内信息移至标题下方正文首句说明。标题是导航锚点，越短越易索引；细节放正文。
   - ✅ `演进路线（史诗口径）` → `演进路线`
   - ✅ `需求跟踪清单（内部跟踪表全量）` → `需求跟踪清单`
   - ✅ `待确认事项（Open Items）` → `待确认事项`
   - ✅ `集中度预警推送（Kafka → 金证 FIX）` → `集中度预警推送`
   - ✅ `白名单配置链路（S180 → 低延时）` → `白名单配置链路`
   - ❌ 不移除：括号内容为标题核心组成（如 `应急旁路撤单工具（BSSAPI）` 中 BSSAPI 为工具专有名 → 建议也移至正文，标题写 `应急旁路撤单工具`）
8. **系统名标注精简**：正文中系统名后**不加括号拼音/英文缩写**（如 jzjy、jzqs、dys、cszx 等），直接用中文系统名。拼音缩写属内部技术编码，不宜出现在面向业务/研发/测试三方的设计文档中；如需标注系统编码，移至参数表或附录的"系统编码对照表"统一列示。
   - ✅ `集中交易（jzjy）` → `集中交易`
   - ✅ `集中清算（jzqs）` → `集中清算`
   - ✅ `低延时（dys）` → `低延时`
   - ❌ 不移除：括号内为业务术语或技术协议名（如 `（T+0 下发内存）`、`（S180 字典 20）`、`（Kafka → 金证 FIX）` 属业务规则/协议路径，保留）
9. **暂停等待**：Phase 1 完成后向用户呈现草稿，**等待评审完善确认指令**，不直接进入 Phase 2。
10. **术语与缩略语表**：专业设计文档应在修订记录后、正文前设"术语与缩略语"章节，统一定义全文涉及的专有缩略语与系统代号（QFII、CTE、GRISK 等）。正文首次出现缩略语时无需展开，读者可查阅缩略语表。该章节标题须加入脚本的 `SKIP_HEADING_TEXTS` 集合以排除自动编号。
11. **图表统一编号**：全文 Mermaid 图和表格必须统一编号（图1/图2/…、表1/表2/…），图编号置于图下方（`**图N　标题**`），表编号置于表上方（`**表N　标题**`），正文交叉引用用"见表N""如图N所示"。元数据表（文档修订记录、术语与缩略语表）不编号。脚本须新增 `format_figure_table_captions` 函数，将 `**图N` / `**表N` 开头的粗体段落格式化为居中、黑体、小五号标题样式。
12. **章节导读段与术语统一**：各章（H2 标题）开头加 1-2 句导读段（引用块 `>` 格式），概括本章覆盖内容与逻辑定位。全文术语须统一：系统代号（如 CTE）仅在架构图与系统交互表中使用，正文一律用中文系统名（如"低延时交易节点"）；"自研低延时"仅在与厂商系统对比语境中保留，其余语境用"低延时"。
13. **Mermaid 图表宽高比优化**（防图片在 Word 中不显示）：
    - **满页宽 + 最大高度约束**：`beautify_images()` 中设 `PAGE_USABLE_EMU=14.64cm`（满页宽）和 `MAX_HEIGHT_EMU=20cm`（安全最大高度），先缩放至满页宽，若高度超 20cm 则等比缩小至 20cm，`wp:extent` 和 `a:ext` 同步更新。
    - **纵向链式图（`flowchart TD`）节点数 ≤4 用单行文本**：节点文字去掉 `<br/>` 改为单行长句（如 `"① 账户级费用：锁券逾期违约费罚息等，无法归集到具体合约"`），增加图片宽度降低高度，避免 ratio>3.0 的极端窄高图。
    - **横向链式图（`flowchart LR`）节点数 ≤6 改纵向**：5 个节点的横向链产出的图片 ratio<0.15（如 3798×438px），缩放至满页宽后高度仅 1.7cm 文字不可读；改为 `flowchart TD` 并合并多行 `<br/>` 为单行，产出 ratio≈2.5 的图片，经最大高度约束后 7.6×20cm 可读。
    - **目标宽高比**：0.3 ≤ ratio ≤ 3.0 为理想区间；ratio>3.0（超高）或 ratio<0.15（过矮）均需调整 Mermaid 源码方向或节点文本布局。
14. **样式定义完整性**（防图片/内容不显示）：pandoc 转换后会为段落分配多种样式（`FirstParagraph`、`BodyText`、`Compact`、`BlockText`、`CaptionedFigure`、`ImageCaption`、`TableCaption` 等），但参考模板的 `styles.xml` 可能**未定义其中部分样式**。Word 遇到引用未定义 `pStyle` 的段落时，会渲染异常——段落内容（含图片）虽在 XML 中结构完整，但视觉上完全空白。必须确保 `add_missing_pandoc_styles()` 覆盖 **pandoc 所有默认段落样式**（不仅是 `CaptionedFigure` 等 3 个），且图片段落 `pStyle` 强制设为已定义的 `CaptionedFigure`。生成后须运行 `verify_docx_integrity()` 验证：解压 docx 检查 `document.xml` 中所有 `pStyle` 的 `w:val` 均在 `styles.xml` 中有对应 `w:styleId` 定义。

### 🌐 腾讯在线文档补充完善（Phase 1 后 / 评审中均可触发）

> 用户提供 `docs.qq.com` 链接后执行本流程，将在线文档中**有价值的信息**补充进设计文档。这是本技能的核心增强能力。

1. **读取在线文档**（依赖 `tencent-docs` 技能，宿主票据鉴权）：
   - 从链接提取 `file_id`：URL 形如 `…/doc/<id>`、`…/sheet/<id>`、`…/slide/<id>`，`?tab=` 后为子表标识。
   - **按品类路由工具**（严禁跨品类）：`sheet`（表格）→ `sheet-mcp`；`doc`（Word）→ `doc-mcp`；`slide`（PPT）→ `slide-mcp`；内容抓取也可走主服务 `tencent-docs` 的 `get_content`。
   - 调用前先 `python3 tencentdocs.py tdoc_init` 确认 `READY`；用 `tdoc_schema <service> <tool>` 查参数后再 `tdoc_call`；工具清单 `tdoc_list <service>`。
   - **读取失败处理**（如隧道 `502 Bad Gateway`、需登录）：**明确告知用户，不得臆造内容**；建议：稍后重试、请用户直接粘贴表格文本、或导出 xlsx 本地读取。
   - **出网代理失效的「代理模式」兜底**：本环境 `tencentdocs.py` 默认走 `HTTP(S)_PROXY` 指向的本地出网代理（如 `127.0.0.1:51242`）。若该代理返回 `502` / 不可达（`curl -x <代理> <外网>` 超时），说明出网代理已死，需改走**企业/系统代理**：
     1. 查系统代理：`networksetup -getwebproxy "Wi-Fi"` / `-getsecurewebproxy "Wi-Fi"`（本机已知企业代理 `172.16.0.11:3128`，但应以当前查询结果为准，勿硬编码）。
     2. 验证可达：`curl -x http://<企业代理>:3128 https://docs.qq.com/openapi/mcp` 应返回 `401`（穿透到服务端）而非超时。
     3. 调用时统一覆盖四套代理变量（urllib 会读小写值，仅覆盖大写会失效）：
        `HTTPS_PROXY=http://<企业代理>:3128 HTTP_PROXY=http://<企业代理>:3128 http_proxy=http://<企业代理>:3128 https_proxy=http://<企业代理>:3128 python3 tencentdocs.py tdoc_call <service> <tool> '[json_args]'`
     4. token 仍从本地 `connector-proxy` 网关（`127.0.0.1:51446`）获取，不受出网代理影响。`--no-proxy` + 宿主直连在沙箱/宿主均无外网出口时无效，勿依赖。
2. **提炼有价值信息**：对照设计文档现有章节，识别在线文档可补充的内容——规则对比表、参数取值与口径、接口字段、边界条件、待确认项澄清、流程差异等。
3. **补充 / 修订**：
   - 将信息并入对应章节（如"负债偿还规则对比"表 → 第 3 章 清算与负债偿还机制；参数表 → 第 5 章）；
   - 更新**修订记录表**（新增版本行或更新 V0.1 描述，注明"补充腾讯在线文档《XXX》"）；
   - **附录 · 事实来源**增列在线文档链接（标注标题与访问日期）。
4. **不臆造**：在线文档未覆盖的内容，不得凭空补全；可标注"（以在线文档/评审确认为准）"。

### Phase 2：生成正式 doc 文档

- **触发条件**：用户明确确认定稿（如"确认，生成 doc"）。
- **格式标准**：参照 `/Volumes/Macintosh HD_Data/WorkBuddy/tmp/` 下的参考文档（PG202204-0215 等），生成国泰海通标准格式 Word 文档。
- **生成工具**：`design_doc_to_docx.py` 脚本（位于本 SKILL 目录），自动完成以下全流程：
  1. **Mermaid 图渲染**：提取 Markdown 中的 `mermaid` 代码块，通过 `mmdc` + Playwright Chromium headless 渲染为 PNG（ Managed Node + NODE_PATH 指向 mmdc node_modules，puppeteer-config 指向 Playwright chromium_headless_shell）。
  2. **Markdown 预处理**：`[[wikilinks]]` → 纯文本、`![[embeds]]` → 参考标注、Obsidian callout 语法清理。
  3. **pandoc 转换**：使用参考文档（`--reference-doc`）作为样式模板，`pandoc 3.9` 转换为 .docx 基础文档。
  4. **python-docx 后处理**（核心格式化）：
     - **封面页**：标题表格（灰底居中、黑体 22pt）+ 史诗编号/部门/日期 + Logo 占位区
       - ⚠️ **行高需充足**：标题行 `trHeight` 设 4000 twips（≈7cm），并设单元格内边距 `tcMar` 上下各 400 twips，否则大字号（22pt）文字上半部分被裁剪
       - ⚠️ **禁止 `w:jc` 于 `w:trPr`**：行级 `w:jc` 在部分 Word 版本会导致渲染异常，表格居中由 `tblPr/jc` 控制
     - **修订记录表**：从 Markdown 解析修订记录，生成标准 5 列表（日期|版本|修订人|修订说明|审核人），表头灰底加粗；自动过滤空行与占位行（如版本号为空的 V2.0 预留行）
     - **目录（TOC）**：插入 Word TOC 域代码（`TOC \o "1-3" \h \z \u`），用户在 Word 中右键"更新域"即可生成目录
     - **标题自动编号**：添加 Word 多级编号定义（`1、` / `1.1` / `1.1.1` / `1.1.1.1`），自动剥离 Markdown 标题中已有的章节号（如"第 1 章"、"1.1"），通过 numPr 引用实现 Word 原生自动编号
       - ⚠️ **层级映射**：H1（`#`）= 文档标题 → **不编号**（`numId=0`）；H2（`##`）→ `ilvl=0`（`1、`）；H3（`###`）→ `ilvl=1`（`1.1`）；H4（`####`）→ `ilvl=2`（`1.1.1`）；H5 → `ilvl=3`
       - ⚠️ **元数据标题不编号**："文档修订记录"等非章节 H2 标题设 `numId=0` 跳过编号
       - ⚠️ **移除样式级 numPr**：pandoc 参考模板的 Heading 样式自带 `numPr`（numId=1），若不移除会与段落级编号冲突，导致标题显示旧编号
       - ⚠️ **清理标题版本标记**："（初稿）""（定稿）""（V0.x）"在编号前从标题文本中移除
     - **缺失样式补全**：pandoc 引用但参考模板未定义的样式需手动注入 styles.xml，否则 **图片/正文段落不显示**。须覆盖 pandoc 全部默认段落样式：`FirstParagraph`（首段正文）、`BodyText`（正文）、`Compact`（紧凑列表项）、`BlockText`（引用块）、`CaptionedFigure`（图片段落，居中+上下间距）、`ImageCaption`（图注）、`TableCaption`（表注）。图片段落 `pStyle` 强制设为 `CaptionedFigure` 而非 pandoc 默认的 `FirstParagraph`。
     - **样式修复**：正文 宋体/Times New Roman 12pt 两端对齐、标题 黑体/Arial 加粗、表格网格边框、表头行加粗
     - **页面设置**：A4 纸张、上下边距 2.54cm、左右边距 3.18cm
  5. **完整性验证**（`verify_docx_integrity()`）：生成后自动验证三项完整性，发现问题打印告警：
     - **样式定义完整性**：检查 `document.xml` 中所有 `pStyle` 的 `w:val` 是否在 `styles.xml` 中有对应 `w:styleId` 定义（未定义→段落内容不显示）
     - **图片段落与尺寸**：检查图片段落 `pStyle` 是否为 `CaptionedFigure`；图片宽度 ≤14.64cm、高度 ≤20cm
     - **图片关系完整性**：检查每张图片的 `r:embed` 是否有对应 relationship 且 `target_part.blob` 非空
  6. **清理**：删除临时 PNG 文件，保留 `images/` 子目录的渲染图供 Obsidian 预览。
- **表格图片美化**（`beautify_tables()` + `beautify_images()` + `colorize_status_cells()`）：
  - **P0 基础美化**：表头灰底（D9D9D9）居中加粗深蓝字（1F4E79）10.5pt + 单元格内边距（上下 2pt / 左右 5.4pt）+ 数据行最小行高 14pt 垂直居中 + 图注自动提取描述性标题 + 图片上下间距
  - **P1 进阶美化**：斑马纹（≥8 行表格偶数行 F2F2F2）+ 窄表居中（≤4 列）+ 正文单元格宋体 10pt 统一 + 边框分级（外框 0.5pt 黑 / 内框 0.25pt 浅灰 BFBFBF）
  - **P2 高阶美化**：Mermaid 高清渲染（`-w 2400 --scale 2`，DPI 翻倍）+ 状态列条件着色（已上线绿 / 待上线橙 / 无状态灰）+ 图注 9pt 小于正文
  - **列宽智能分配**（`optimize_column_widths()`）：基于内容长度（中文字符按 2 宽度、英文按 1）计算每列权重，归一化为 dxa 列宽并同步更新 `tblGrid/gridCol` 和单元格 `tcW`；约束最小 5%、最大 50%；消除等分列宽导致的文本过度换行和空间浪费

#### 表格图片美化参数速查表

> 以下参数均定义在 `design_doc_to_docx.py` 顶部常量区与 `beautify_tables()` / `beautify_images()` / `colorize_status_cells()` 函数内，后续微调直接改常量或函数内硬编码值即可。

**颜色常量**（`COLOR_*` 系列）：

| 常量 | 值 | 用途 |
|------|------|------|
| `COLOR_GRAY_BG` | `D9D9D9` | 封面标题背景灰 / **表头行背景灰** |
| `COLOR_ZEBRA` | `E8E8E8` | 斑马纹偶数行浅灰底（加深以提升可见度） |
| `COLOR_HEADER_TEXT` | `1F4E79` | 表头文字深蓝色 |
| `COLOR_HEADER_BORDER` | `BFBFBF` | 表格内框线浅灰 |
| `COLOR_STATUS_GREEN` | `2E7D32` | 状态列"已上线"绿色 |
| `COLOR_STATUS_ORANGE` | `E65100` | 状态列"待上线/SIT/UAT"橙色 |
| `COLOR_STATUS_GRAY` | `757575` | 状态列"—/不需要"灰色 |
| `COLOR_IMG_BG` | `F8F9FA` | 图片背景极浅灰（预留） |
| `COLOR_IMG_BORDER` | `D0D0D0` | 图片边框灰（预留） |

**尺寸参数**（twips，1 twip = 1/20 pt = 1/1440 inch）：

| 参数 | 值 | 用途 |
|------|------|------|
| 表头行高 | 360 twips (18pt) | `trHeight hRule=atLeast` |
| 数据行最小行高 | 280 twips (14pt) | `trHeight hRule=atLeast` |
| 单元格上/下内边距 | 40 twips (2pt) | `tblCellMar top/bottom` |
| 单元格左/右内边距 | 108 twips (5.4pt) | `tblCellMar left/right` |
| 表头字号 | 10.5pt (sz=21) | 加粗 + 深蓝色 |
| 正文单元格字号 | 10pt (sz=20) | 宋体/Times New Roman |
| 图注字号 | 9pt (sz=18) | 居中，小于正文 |
| 图片段落上间距 | 180 twips (9pt) | `spacing before` |
| 图片段落下间距 | 60 twips (3pt) | `spacing after` |
| 图注上间距 | 60 twips (3pt) | `spacing before` |
| 图注下间距 | 240 twips (12pt) | `spacing after` |

**触发条件**：

| 规则 | 条件 | 实现 |
|------|------|------|
| 斑马纹启用 | 表格行数 ≥ 8 | `use_zebra = num_rows >= 8` |
| 斑马纹着色 | 偶数数据行（ridx % 2 == 0） | 浅灰 `F2F2F2` |
| 窄表居中 | 列数 ≤ 4 | `tblPr/jc=center` |
| 边框分级 | 全部表格 | 外框 `single/4`（0.5pt 黑）/ 内框 `single/2 BFBFBF`（0.25pt 浅灰） |
| 状态列识别 | 表头含"状态"或"上线"关键词 | `status_col_indices` 匹配 |
| Mermaid 高清 | 全部 Mermaid 图 | `-w 2400 -H 1200 --scale 2` |
| 描述性图注 | Mermaid 图前最近的 `#` 标题 | 正则提取，格式"图N  标题" |
| 列宽智能分配 | 全部 ≥2 行表格 | `optimize_column_widths()` 按内容长度（中文 2/英文 1）加权分配，约束 5%–50% |

---

## 📊 图表类型选择指南（Phase 1 草稿阶段参考）

> **核心原则**：能用图表则不用纯文字。以下为内容特征 → 图表类型的映射参考，Phase 1 逐章审视时按此表主动识别可图表化点。

### 按内容特征选择图表类型

| 内容特征 | 推荐图表类型 | Mermaid 语法 | 示例场景 | 颜色分组建议 |
|:---------|:------------|:------------|:---------|:------------|
| 多期次/多阶段 + 时间维度 | **时间轴 / 甘特图风格 flowchart** | `flowchart TD` + 节点含日期 | 演进路线、版本计划、上线排期 | 按状态分色：已上线绿/排期黄/暂停蓝/预研紫 |
| 递进式流程（①→②→③→④） | **流程图** | `flowchart TD` | 偿还顺序、清算流程、审批流程 | 起止绿/处理蓝/结束红 |
| 多分支判定（if/else 级联） | **决策树流程图** | `flowchart TD` + `{菱形}` 判定节点 | 风控拦截逻辑、白名单豁免、权限校验 | 判定黄/通过绿/拒绝红/告警橙 |
| 系统间数据流向 | **数据流图** | `flowchart LR` | 集中度推送链路、指标计算流、文件导出链路 | 按系统域分色：前端蓝/服务紫/核心绿/风控橙 |
| 部署/节点分布 | **拓扑图** | `flowchart TB` + subgraph | 节点域划分、机房分布、双节点隔离 | 按域分色：信创蓝/创新绿/源节点橙 |
| 分层/切分模型 | **分层示意图** | `flowchart LR/TB` | JVS切蛋糕、指标体系分层、权限层级 | 集中层紫/下发层黄/节点层绿 |
| 多系统 × 多场景对比 | **对比矩阵图** | `flowchart TB` + subgraph 分组 | 跨系统偿还规则对比、功能支持矩阵 | 目标模式高亮绿/对比项蓝 |
| 全天时间点排列 | **时间轴图** | `flowchart LR` + 节点含时间 | 盘前/盘后文件导出、定时任务节奏 | 文件类蓝/交易类绿/收尾黄 |
| 风险按影响分级 | **风险矩阵（分层）** | `flowchart TD` + subgraph 分层 | 风险与合规要点、问题严重度分级 | 高影响红/中影响黄/低影响绿 |
| 系统交互时序 | **时序图** | `sequenceDiagram` + `autonumber` | 白名单配置链路、接口调用顺序 | 按 actor/participant 自动配色 |
| 系统全景架构 | **架构图（五色分组）** | `flowchart TD` + subgraph + classDef | 总体架构图、系统交互拓扑 | 前端蓝/服务紫/核心绿/风控橙/管理青 |

### 图表插入规范

1. **位置**：图表插入在对应章节文字描述**之后**（先文字引导，再图表展示），不替代必要的文字说明。
2. **图注**：由 `render_mermaid_diagrams()` 自动从最近的 `#` 标题提取，格式"图N  标题"，无需手动编写。
3. **数量建议**：10~20 页设计文档建议 5~10 张图表（图文比 8%~15%），太少则信息密度低、太多则喧宾夺主。
4. **颜色规范**（classDef 配色体系，已验证可读性良好）：

| 色彩角色 | classDef 名 | 填充色 | 边框色 | 适用场景 |
|:---------|:-----------|:-------|:-------|:---------|
| 绿（通过/已上线/低风险） | `done`/`pass`/`low` | `#C8E6C9` | `#2E7D32` | 已完成状态、通过判定、低影响风险 |
| 黄（进行中/排期/中风险） | `active`/`mid` | `#FFF9C4` | `#F9A825` | 排期中、中影响风险 |
| 蓝（待定/前端/信息流） | `pending`/`fe` | `#E3F2FD` | `#1565C0` | 待上线、前端柜台、信息类节点 |
| 紫（集中层/服务层） | `svc`/`cake` | `#F3E5F5` | `#6A1B9A` | JVS集中层、参数中心 |
| 橙（风控/告警/高风险） | `risk`/`warn`/`high` | `#FFF3E0` | `#E65100` | 风控中心、告警、高影响风险 |
| 红（拒绝/结束/高危） | `reject`/`end` | `#FFEBEE` | `#C62828` | 拒单、流程终止、高危风险 |
| 青（管理端） | `mgmt` | `#E0F2F1` | `#00695C` | 集中营运、账户系统 |

5. **渲染参数**（已固化到 `design_doc_to_docx.py`，勿回退）：
   - `fontSize: 20px`（mermaid-config.json）
   - `--scale 3 -w 3200 -H 1800`（高清渲染）
   - 图片满页宽 14.64cm（A4 可用宽度）
   - `TMPDIR=/tmp`（Homebrew mmdc mkdtemp 路径修复）

---

#### Phase 2 调用示例与参数

- **调用示例**：
  ```bash
  /Users/wujin/.chat/runtimes/darwin-x64/python/versions/3.13.12/bin/python3 \
    /Users/wujin/.workbuddy/skills/gtht-req-design-doc/design_doc_to_docx.py \
    "<input.md>" "<output.docx>" \
    --title "文档标题" --epic "PG202204-0269" \
    --author "吴进" --dept "技术研发部" --date "2026-11-09" \
    --ref-doc "/Volumes/Macintosh HD_Data/WorkBuddy/tmp/PG202204-0215-低延时银保节点余券划转T+1可用方案设计概要.docx"
  ```
- **关键参数**：
  - `--ref-doc`：pandoc 参考模板（从 `WorkBuddy/tmp/` 选择格式最接近的参考文档）
  - `--skip-mermaid`：跳过 Mermaid 渲染（文档无图时加速）
  - `--title`/`--subtitle`：封面标题/副标题
  - `--epic`：史诗编号（封面显示）
- **依赖**：`python-docx`（已安装于 managed Python）、`pandoc`（系统 `/usr/local/bin/pandoc`）、`mmdc`（Homebrew `/usr/local/Cellar/mermaid-cli/11.15.0` + Managed Node + Playwright Chromium）
- **更新修订记录**：V1.0 定稿行（填写人/批准人/日期）在 Phase 1 Markdown 中更新，Phase 2 自动从 Markdown 解析并渲染到封面页修订表。
- **输出路径**：`100_Projects/设计文档/<主题>系统总体设计.docx`

#### Phase 2 已知坑点与解决方案（踩坑记录）

> 以下是实际生成过程中遇到的问题及修复方案，均已固化到 `design_doc_to_docx.py`，后续修改脚本时勿回退。

| # | 现象 | 根因 | 修复 |
|---|------|------|------|
| 1 | **Mermaid 图片不显示**（架构图/时序图空白） | pandoc 生成的段落引用 `CaptionedFigure`/`ImageCaption` 样式，但参考模板 styles.xml 未定义这些样式 → Word 找不到样式 → 图片段落渲染失败 | `add_missing_pandoc_styles()` 手动注入 `CaptionedFigure`（居中+上下间距）、`ImageCaption`、`TableCaption` 样式定义 |
| 2 | **封面大标题上半部分被裁剪** | 标题行高 `trHeight=2762` twips（≈4.9cm）不足以容纳 22pt 黑体；行级 `w:jc` 导致渲染异常 | 行高增至 `4000` twips（≈7cm）；添加 `tcMar` 上下各 400 twips 内边距；移除 `w:trPr/w:jc` |
| 3 | **标题编号层级错位**（H1 被编号"1、"，H2 编号"1.1"） | `apply_heading_numbering` 按 heading level 直接映射 ilvl（H1→0, H2→1），但 H1 是文档标题不应编号 | H1 设 `numId=0`（不编号）；H2→`ilvl=0`（`1、`），H3→`ilvl=1`（`1.1`），H4→`ilvl=2`，H5→`ilvl=3` |
| 4 | **"文档修订记录"被编号** | 该 H2 标题是元数据而非内容章节，但编号逻辑未区分 | `SKIP_HEADING_TEXTS` 集合匹配，命中的标题设 `numId=0` 跳过编号 |
| 5 | **标题残留"（初稿）"等版本标记** | 版本标记分散在多个 run 中，逐 run strip 无效 | 合并所有 run 文本 → 正则清理 → 写回第一个 run，其余 run 清空 |
| 6 | **标题显示旧编号**（如"1.1"重复出现） | pandoc 参考模板的 Heading 样式自带 `numPr`（`numId=1`），段落级编号与样式级编号叠加 | 遍历所有 heading 样式，移除其 `pPr/numPr`，编号仅由段落级 `numPr` 控制 |
| 7 | **修订记录表多出空 V2.0 行** | Markdown 修订表中有版本号为空的预留行 | `parse_revision_entries` 过滤：版本号为空或其余列全空的行跳过 |
| 8 | **mmdc 崩溃**（V8 fatal error） | AILink 内置 Node 的 V8 引擎与 mmdc 不兼容 | 使用 Managed Node（`~/.chat/runtimes/darwin-x64/node/versions/22.22.2/bin/node`）+ `NODE_PATH` 指向 mmdc 的 `node_modules` + puppeteer-config 指向 Playwright `chromium_headless_shell` |
| 9 | **表头与数据行视觉无区分** | 原始 pandoc 表格表头无背景色、无加粗、无居中 | `beautify_tables()`：表头行灰底 D9D9D9 + 居中 + 加粗 + 深蓝色 1F4E79 + 10.5pt + 垂直居中 + 行高 360 twips |
| 10 | **长表（≥8 行）阅读易跳行** | 数据行无交替底色，视觉追踪困难 | 斑马纹：`use_zebra = num_rows >= 8`，偶数数据行加浅灰底 F2F2F2 |
| 11 | **图注仅"图1"无描述** | Mermaid 替换时 alt text 固定为"图N" | `render_mermaid_diagrams()` 从 Mermaid 代码块前最近的 `#` 标题提取描述性标题，格式"图N  标题" |
| 12 | **状态列无颜色区分** | 上线状态全黑字，已上线/待上线/无状态视觉无差异 | `colorize_status_cells()`：表头含"状态"或"上线"的列，按关键词匹配着色（已上线→绿 2E7D32 / 待上线·SIT·UAT→橙 E65100 / —·不需要→灰 757575） |
| 13 | **单元格文字紧贴边框** | pandoc 表格无 `tblCellMar` 定义 | `beautify_tables()` 统一注入 `tblCellMar`：上下 40 twips(2pt)、左右 108 twips(5.4pt) |
| 14 | **Mermaid 图打印模糊** | 默认 `-w 1200` 渲染分辨率仅 ~207 DPI | 升级为 `-w 2400 -H 1200 --scale 2`，DPI 翻倍；文件从 ~60KB 增至 ~250KB 可接受 |
| 15 | **表格列宽全部等分** | pandoc 生成的 `tblGrid` 每列等宽，不考虑内容长度 → 长文本列过度换行（行高 5cm+）、短文本列浪费 80%+ 空间 | `optimize_column_widths()`：按内容长度（中文 2/英文 1）计算权重 → 归一化为 dxa 列宽 → 同步更新 `tblGrid/gridCol` + 单元格 `tcW`；约束最小 5%、最大 50% |
| 16 | **斑马纹不可见** | `F2F2F2` 在白底上对比度仅 1.12:1，肉眼几乎不可见 | 加深为 `E8E8E8`，对比度提升至 ~1.3:1，清晰可辨且不干扰阅读 |
| 17 | **目录位置错误** | `add_toc_field()` 用 `body.append()` 把目录追加到文档末尾，pandoc 正文已在 body 中，导致目录排在正文之后 | 改为 `add_toc_field(doc, after_element=page_break_p._element)`，将目录插入到封面+修订记录的分页符之后、正文之前；并在 TOC 域后再插入分页符分隔目录与正文 |
| 18 | **表格来源说明位置不规范** | 来源说明（如"来源：腾讯在线文档…"）放在表格**上方**，读者未看表就先看到引用出处，且与表格阅读说明（如"★ = 目标模式"）混在一起 | **Markdown 源文件规范**：表格阅读说明（列标记、口径解释）放表格上方；来源/引用说明放表格**下方**（表注）；章节引言式来源（含上下文描述）不在此列，保持章节标题下方 |
| 19 | **文档含源码级引用引发合规风险** | 设计文档中包含源文件名（`.cpp`/`.h`）、代码行号（`:8659`）、代码路径（`biz_impl/...`）、代码变量名（`is_multi_appoint`/`contract_date`）等源码级引用，可能泄露内部实现细节，引发合规审计风险 | **Phase 1 Markdown 编辑规范**：移除所有源码级引用（文件名、行号、代码路径、代码变量名）；设计级标识符（表名如 `node_crdcustcompwhitelist`、参数名如 `qp`/`NewExpiredDays`、配置文件名如 `credit_scale.xml`）保留，因其属系统设计配置描述而非源码；移除无关关联需求时同步清理其全部引用（跟踪清单行、章节正文、交叉引用链接、待确认事项、附录、修订记录描述），确保零残留 |
| 20 | **来源引用格式不学术规范** | 正文来源说明以 Markdown blockquote 形式散落各章节（如"> 来源：腾讯在线文档《…》（docs.qq.com/…，经企业代理读取）"），含技术细节（代理 IP、端口），不符合正式设计文档的学术引用规范；待确认事项"来源"列写日期编号（如"20260519"）或"跟踪表 R26xxxx"，无统一引用体系 | **论文脚注/尾注式改造**：正文来源改为 pandoc 上标 `^[N]^`（Markdown `^text^` 语法）；文末统一"参考文献"章节，按 GB/T 7714 格式列出（在线文档 `[EB/OL]`、会议纪要 `[Z]`、规范 `[S]`）；待确认事项"来源"列全部改为 `[N]` 引用编号；`format_references()` 函数：宋体/TNR 9pt、1.5 倍行距、悬挂缩进 0.74cm；`SKIP_HEADING_TEXTS` 增加"参考文献"排除编号 |
| 21 | **`^[N]^` 被 pandoc 误解析为脚注** | Markdown 中 `^[1]^` 本意是 pandoc 上标语法（`^text^`），但 `^[` 恰好也是 pandoc 内联脚注语法 `^[脚注内容]^`，导致 `[1]` 被解析为脚注内容而非上标文字，末尾残留 `^` 字符散布全文 | pandoc `--from` 参数增加 `-inline_notes` 禁用内联脚注扩展，使 `^[1]^` 正确解析为上标 `[1]`（`vertAlign=superscript`） |
| 22 | **架构图文字太小不可读** | Mermaid 默认 `fontSize=13px` 太小；`--scale 2` + `-w 2400` 渲染分辨率偏低（图片仅 2378×950px）；Word 中图片未设满页宽，缩放后文字更小 | 三维度优化：① mermaid-config.json `fontSize` 从 13px 增至 20px；② `--scale` 从 2 提至 3、`-w/-H` 从 2400×1200 提至 3200×1800（图片增至 3567×1443px）；③ `beautify_images()` 新增图片满页宽逻辑（A4 可用宽度 14.64cm = 5270400 EMU），遍历 `wp:extent` 和 `a:ext` 设置 `cx` 为满页宽并等比缩放 `cy` |
| 23 | **表格窄列文字被截断** | `optimize_column_widths` 中 `MIN_COL_PCT=0.05`（5%）下限太低，7 列表中最窄列仅 0.73cm（415 twips），中文 2 字标题换行严重；`MAX_COL_PCT=0.50` 允许单列占半页，挤压其他列 | `MIN_COL_PCT` 从 0.05 提至 0.08（8%）；`MAX_COL_PCT` 从 0.50 降至 0.45；新增 `MIN_COL_TWIPS=700`（≈1.23cm）绝对最小列宽，与百分比取较大者；修复后所有表格列宽均 ≥1.0cm |
| 24 | **TOC 与正文间连续空段落** | pandoc 转换后 TOC 域与正文之间存在 3+ 个连续空段落（分页符区域），影响排版紧凑性 | 新增 `cleanup_empty_paragraphs(doc)` 函数：遍历 `w:p` 检测无文本/无图片/无域的连续空段落，保留首个作为间距，删除后续空段落；含分页符（`w:br`）的段落跳过不清除 |
| 25 | **Mermaid 图表批量渲染失败（commander 模块缺失）** | npm-global 安装的 mermaid-cli（符号链接到 Gemini/testskills/mermaid-cli 源码目录）缺少 `node_modules`（`commander` 等依赖未安装），`npm install` 因内网镜像 401 / 公网 ETIMEDOUT 失败；Homebrew 安装的 mermaid-cli（`/usr/local/Cellar/mermaid-cli/`）有完整 `node_modules` 但 puppeteer 找不到 Chrome | 将 `mmdc_src`/`mmdc_dir` 从 npm-global 路径改为 Homebrew 路径 `/usr/local/Cellar/mermaid-cli/11.15.0/libexec/lib/node_modules/@mermaid-js/mermaid-cli/`；`env` 新增 `TMPDIR=/tmp`（Homebrew mmdc 的 mkdtemp 路径异常）；puppeteer-config 仍指向 Playwright `chromium_headless_shell`（Homebrew puppeteer 需额外安装 Chrome，Playwright 已有）；批量渲染 11 张 Mermaid 图表全部成功 |
| 26 | **每张图出现两条图注（pandoc 自动图注 + 手动图注重复）** | pandoc `implicit_figures` 扩展（`+implicit_figures`）将图片 alt 文本自动转为图注（如"图5 清算与负债偿还机制"），同时手动添加的 `**图5　负债偿还顺序流程图**` 形成第二条图注，导致重复 | pandoc `--from` 参数将 `+implicit_figures` 改为 `-implicit_figures` 禁用隐式图注；`render_mermaid_diagrams()` 中图片 alt 文本设为空（`![](img.png)`）；手动 `**图N　...**` 图注由 `format_figure_table_captions()` 统一格式化为唯一图注 |
| 27 | **部分图片在 Word 中显示不出来**（如图2 部署与节点域划分） | `beautify_images()` 仅设置满页宽（14.64cm）但**未限制图片最大高度**，超高图片（如图5 原 52.72cm，源图 888×3198px ratio=3.60）远超 A4 可用高度（24.6cm），Word 渲染异常或无法显示；同时部分 Mermaid 图表因 `flowchart TD/LR` 方向选择不当导致极端宽高比（LR 5 节点链→3798×438px ratio=0.12 过矮文字不可读；TD 6 节点链→888×3198px ratio=3.60 过高超页） | ① `beautify_images()` 新增 `MAX_HEIGHT_EMU=20cm` 约束：先缩放至满页宽，若高度超 20cm 则等比缩小至 20cm（`wp:extent` 和 `a:ext` 同步更新）；② Mermaid 源码优化：纵向链式图改横向（`TD→LR`）或加宽节点文本（去掉 `<br/>` 改单行长句），横向链式图改纵向（`LR→TD`）并合并多行文本为单行；③ 验证：所有 10 张图高度均 ≤20cm、宽度 ≤14.64cm |
| 28 | **所有图片在 Word 中都不显示**（空白段落） | pandoc 为段落分配 `FirstParagraph`/`BodyText`/`Compact`/`BlockText` 等样式，但参考模板（`--ref-doc`）的 styles.xml **未定义这些样式**。Word 遇到未定义 `pStyle` 的段落时，部分版本（尤其 WPS）会渲染异常甚至不渲染段落内容，导致图片段落虽含完整 `<w:drawing>` 元素但视觉空白 | ① `add_missing_pandoc_styles()` 补全 `FirstParagraph`/`BodyText`/`Compact`/`BlockText` 四个 pandoc 默认正文样式定义（含字体、字号、行距、缩进），确保所有段落样式在 styles.xml 中有定义；② `beautify_images()` 将图片段落 `pStyle` 强制设为已定义的 `CaptionedFigure`（居中+上下间距），而非 pandoc 默认的 `FirstParagraph`；③ 验证：解压 docx 检查 `document.xml` 中所有 `pStyle` 引用的 `w:val` 均在 `styles.xml` 中有对应定义 |

---

## 📌 落盘与记录规范

| 类别 | 路径 / 动作 |
| :--- | :--- |
| 设计文档 | `100_Projects/设计文档/<主题>系统需求设计概要.md` |
| 操作登记 | `999_Meta/log.md`（摘要 + 来源引用，含在线文档链接） |
| 引用范式 | `100_Projects/设计文档/` 既有设计文档（章节式 + Mermaid） |

## ⚠️ 核心红线（与 ba-to-dev 同源）

1. **绝对忠于事实**：未明确者统一注 `（具体实现以研发设计为准）`，严禁凭空捏造系统名/接口号/表名字段。
2. **非本组系统不替其细化**：第三方/他组系统仅列业务目标与责任方，不编造实现细节。
3. **在线文档内容真实优先**：补充信息必须来自实际读取的在线文档，失败时显式说明，绝不臆造。
4. **两阶段门禁**：Phase 1 后必须暂停等待用户评审确认，未经确认不生成正式 doc。
