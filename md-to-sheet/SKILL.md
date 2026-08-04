---
name: md-to-sheet
description: >-
  将Obsidian需求MD文件批量写入腾讯文档在线表格。读取指定目录下的需求MD文件，解析需求名称、描述、涉及系统等字段，
  去重后追加到腾讯文档表格中，自动处理超链接、多系统换行、背景色等格式。
  触发词：MD写入表格、需求导入表格、MD到腾讯文档、@tdoc配合MD文件、追加需求到表格。
  当用户同时提供腾讯文档表格引用（@tdoc）和本地MD文件路径，并要求将MD内容写入表格时触发。
---

# MD需求文件写入腾讯文档表格

将本地Obsidian需求MD文件的结构化内容，批量解析并写入腾讯文档在线表格。

## 触发场景

- 用户提供 `@tdoc:"表格名"` 引用腾讯文档表格，同时有本地MD需求文件需要导入
- 用户说"把MD写入表格"、"把需求导入到腾讯文档"等
- 用户说"追加需求到表格"、"同步需求到表格"

## 表格列结构（0-indexed）

| 列号 | 列名 | 说明 | 写入方式 |
|------|------|------|---------|
| 0 | 提出日期 | 需求提出日期 | `set_range_value` STRING |
| 1 | 优先级 | 下拉选项 | `set_range_value` STRING，值"正常"（下拉需用户手动格式刷） |
| 2 | 需求链接 | Fintech平台链接 | `set_link` 设置超链接+显示文本 |
| 3 | 需求名称 | 完整需求标题 | `set_range_value` STRING |
| 4 | 需求描述 | 背景+内容 | `set_range_value` STRING，设置自动换行（背景色需JS脚本） |
| 5 | 涉及系统 | 🔴多系统换行（关键） | `set_range_value` STRING，设置自动换行，系统间**必须**用 `\n` 分隔 |
| 6 | 关联系统 | 关联系统 | `set_range_value` STRING，系统间用 `\n` 分隔 |
| 7 | 计划排期 | 上线计划 | `set_range_value` STRING |
| 8 | story拆分 | 是否拆分 | `set_range_value` STRING，默认"否" |
| 9 | 评审状态 | 评审结果 | `set_range_value` STRING，默认"待评审" |
| 10 | 备注 | 补充说明 | `set_range_value` STRING，默认留空 |
| 11 | 参会人员 | 参会人 | `set_range_value` STRING，留空 |

## 工作流程

### Step 1: 读取表格结构

1. 用 `get_sheet_info` 获取文件的所有子表信息（sheet_id、名称）
2. 用 `get_cell_data` 读取目标sheet的表头（row 0）和已有数据行，确定：
   - 列结构是否匹配上述标准
   - 最后一行数据的位置（新数据从 `lastRow + 1` 开始写入）
   - 已有需求名称列表（用于去重）

### Step 2: 读取MD文件

1. 从用户指定的目录读取MD文件，默认路径：`/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析/`
2. MD文件命名格式：`YYYYMMDD-需求-【系统名】需求标题.md`
3. 解析每个MD文件，提取以下字段：

**从文件名提取：**
- 提出日期：文件名前8位 `YYYYMMDD` → 转为 `YYYY/M/D` 格式
- 需求名称：文件名中 `需求-` 后的部分（去掉 `.md` 扩展名）

**从文件内容提取：**
- 需求描述：取"需求背景"和"需求内容"两个章节的正文，拼接为 `一、需求背景\n...\n\n二、需求内容\n...` 格式。省略"技术实现方案"和"评审纪要"章节
- 涉及系统：从MD内容中的系统标识提取（如"集中清算"、"低延时两融"、"参数中心"、"集中交易"等）。**关键：多个系统名必须用 `\n` 换行符连接，每个系统独占一行。严禁使用空格、顿号(、)、逗号(,) 或空格分隔符连接。**正确示例：`"低延时\n集中交易\n参数中心"`，错误示例：`"低延时 集中交易 参数中心"`
- 关联系统：如内容中提到"低延时已切换"等关联关系，提取为关联系统。多系统同样用 `\n` 换行符连接
- 计划排期：从"计划2026年XX月上线"提取为"X月份"
- 评审状态：从"评审结果：通过/不通过"提取，无则默认"待评审"
- 需求链接：从MD内容中的需求编号（如 `R2605250010`）拼接为 `https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId=RXXXXXXXXX&templateId=8888&flag=1`

### Step 3: 原地更新与追加 (Update & Append)

对比 MD 文件的需求名称与表格已有的需求名称（col 3）：
1. **有则更新**：若在线表格已存在同名需求，获取其所在行号。写入时仅覆盖更新提取到的动态属性（提出日期、描述、涉及系统、关联系统、排期、评审状态、超链接），但**保留**已有的“优先级”、“story拆分”、“备注(K列)”和“参会人员(L列)”字段，避免覆盖人工调整的数据。
2. **无则追加**：若不存在，则在表格第一个检测到的全空行位置追加写入新行。

### Step 4: 写入数据

采用批量化设计以最大化同步速度（减少 MCP 调用次数）。主要流程：

1. **批量单元格写入**：将所有需求数据（除C列超链接外）整理至单个 `set_range_value` 的 values 列表中，一次性写入。
2. **合并脚本执行**：将格式同步、C列超链接、全列自动换行合并为一个 JavaScript 脚本，通过单个 `operation_sheet` 接口提交给腾讯文档执行。

**E列背景色与特殊列格式修复（CRITICAL）：**
在复制整行样式（`setBackgrounds`）后，部分已设格式单元格（如 E列 的描述背景色，B列 的优先级背景）可能出现丢失或显示为黑色。需在脚本中遍历特定列并显式调用 `setBackground`、`setFontColor`、`setFontSize` 进行强力覆盖修复。

2. **格式修复**：使用 `set_cell_style` 修复行样式及列格式。

**E列背景色与对齐样式修复的 Python MCP 实现：**
由于腾讯云 WAF 误杀机制会拦截含有复杂 JS 代码（如 `operation_sheet`）的请求并引发 501 报错，因此必须全面使用原生 Python MCP API 进行单元格样式及行高设置。

具体实现方案：
1. **全列垂直居中与自动换行**：使用 `sheet.set_cell_style` 原生工具，对整段行区间 `[min_row, max_row]` 的 `0-11` 列（A-L）批量设置 `vertical_align: "center"` 和 `wrap_text: True`。
2. **Column E（需求描述）顶端对齐与背景色**：使用 `sheet.set_cell_style` 原生工具，对第 `4` 列（E），在 `[min_row, max_row]` 区间批量设置 `vertical_align: "top"`, `horizontal_align: "left"`, `bg_color: "FFFFF9E3"` 和 `wrap_text: True`。确保多行描述文本紧贴单元格顶部展示。
3. **自适应动态行高设置**：根据需求描述文本行数，计算建议行高并调用 `sheet.set_dimension_size` 批量设置行高尺寸，防止文本裁切。

```python
# 1. 批量整行垂直居中与自动换行
call_mcp("sheet.set_cell_style", {
    "file_id": file_id,
    "sheet_id": sheet_id,
    "start_row": min_row,
    "end_row": max_row,
    "start_col": 0,
    "end_col": 11,
    "vertical_align": "center",
    "wrap_text": True
})

# 2. 批量 Column E 顶端对齐与浅黄底色
call_mcp("sheet.set_cell_style", {
    "file_id": file_id,
    "sheet_id": sheet_id,
    "start_row": min_row,
    "end_row": max_row,
    "start_col": 4,
    "end_col": 4,
    "vertical_align": "top",
    "horizontal_align": "left",
    "bg_color": "FFFFF9E3",
    "wrap_text": True
})

# 3. 批量调整自适应行高
call_mcp("sheet.set_dimension_size", {
    "file_id": file_id,
    "sheet_id": sheet_id,
    "dimensions": row_dims
})
```

**B列（优先级下拉）与 F列（涉及系统）换行限制：**
1. B列下拉指示器：腾讯文档API不支持下拉列表验证规则的读写，B列值默认写入"正常"即可，下拉指示器需要用户在网页上手动使用格式刷复制。
2. F列多系统换行：系统名之间必须使用 `\n` 换行符连接，严禁使用空格、顿号(、)、逗号(,)连接。例如：`"低延时\n集中交易"`。

### Step 5: 验证

写入完成后，用 `get_cell_data` 读取新写入的行，确认数据正确性，向用户汇报写入结果。

## 运行同步脚本

已在 `scripts/md_to_sheet.py` 中封装了完整的解析与同步控制，可以通过以下命令行方式运行：

```bash
# 默认模式（等同于 rzrq）：仅读取及同步融资融券当日的需求 MD 文件
# 默认访问：https://docs.qq.com/sheet/DVGtPSXpzWU1zYXNi?tab=BB08J2 (融资融券需求跟踪)
python3 ~/.workbuddy/skills/md-to-sheet/scripts/md_to_sheet.py
# 或显式传入 rzrq
python3 ~/.workbuddy/skills/md-to-sheet/scripts/md_to_sheet.py rzrq

# 股票质押模式：仅读取及同步股票质押当日的需求 MD 文件
# 访问：https://docs.qq.com/sheet/DVEtyb05taEFDc0xL?tab=BB08J2 (股票质押需求跟踪)
python3 ~/.workbuddy/skills/md-to-sheet/scripts/md_to_sheet.py gpzy

# 其他模式：仅读取及同步其他类型的当日需求 MD 文件
# 访问：https://docs.qq.com/sheet/DVE9Gb0daTmtzUE9H?tab=BB08J2 (其他需求跟踪)
python3 ~/.workbuddy/skills/md-to-sheet/scripts/md_to_sheet.py qt

# 同步指定日期的股票质押需求
python3 ~/.workbuddy/skills/md-to-sheet/scripts/md_to_sheet.py gpzy --date 20260602

# 同步所有历史日期的融资融券需求
python3 ~/.workbuddy/skills/md-to-sheet/scripts/md_to_sheet.py rzrq --date all

# 预览模式（只解析预览，不实际修改表格）
python3 ~/.workbuddy/skills/md-to-sheet/scripts/md_to_sheet.py gpzy --dry-run
```

## 已知限制

1. **下拉选项**：腾讯文档API不支持数据验证（Data Validation）的读写，B列下拉需手动格式刷
2. **E列背景色**：`set_cell_style` 和 `clear_range_all` 对部分已设格式单元格无效，需用 `operation_sheet` JS脚本操作
3. **诊断数据清理**：`operation_sheet` JS脚本执行时如需写入诊断信息，务必在脚本最后用 `range.clear()` 清理，避免残留垃圾数据
4. **C列超链接**：`set_link` 会清除该单元格原有文本，必须设置 `display_text` 参数
5. **行号约定**：腾讯文档API和SpreadsheetApp的行列号均为1-based，`get_cell_data`/`set_range_value` 为0-based

## 使用样例与典型调用示例

### 场景 1：导入今日两融需求 (rzrq)
* **用户输入**：
  * `@tdoc:"融资融券需求跟踪" 把今天的两融需求写入表格`
  * `同步今天的两融需求MD到在线文档`
* **默认执行指令**：
  ```bash
  python3 ~/.workbuddy/skills/md-to-sheet/scripts/md_to_sheet.py rzrq
  ```
  *(注：如果不指定业务参数，脚本默认也是 `rzrq`)*

### 场景 2：导入今日股票质押需求 (gpzy)
* **用户输入**：
  * `@tdoc:"股票质押需求跟踪" 把今天的股票质押需求写入表格`
  * `同步今天的股质需求到在线表格`
* **默认执行指令**：
  ```bash
  python3 ~/.workbuddy/skills/md-to-sheet/scripts/md_to_sheet.py gpzy
  ```

### 场景 3：导入今日其他需求 (qt)
* **用户输入**：
  * `@tdoc:"其他需求跟踪" 把今天的其他非信用需求写入表格`
  * `同步今天的其他通用需求`
* **默认执行指令**：
  ```bash
  python3 ~/.workbuddy/skills/md-to-sheet/scripts/md_to_sheet.py qt
  ```

### 场景 4：同步特定日期的历史需求
* **用户输入**：
  * `@tdoc:"融资融券需求跟踪" 同步20260602的两融需求`
  * `把20260602的股质需求写入表格`
* **默认执行指令**（根据指定的日期和业务类型执行）：
  ```bash
  python3 ~/.workbuddy/skills/md-to-sheet/scripts/md_to_sheet.py rzrq --date 20260602
  python3 ~/.workbuddy/skills/md-to-sheet/scripts/md_to_sheet.py gpzy --date 20260602
  ```

### 场景 5：同步所有历史需求
* **用户输入**：
  * `@tdoc 同步所有历史两融需求`
  * `同步全部的历史其他需求`
* **默认执行指令**：
  ```bash
  python3 ~/.workbuddy/skills/md-to-sheet/scripts/md_to_sheet.py rzrq --date all
  python3 ~/.workbuddy/skills/md-to-sheet/scripts/md_to_sheet.py qt --date all
  ```

---

## 执行通用流程说明
1. 助手检测到触发词后，根据用户的意图（业务类型和日期参数），映射为对应的本地 Python 命令进行调用。
2. 脚本运行中会自动获取表格结构、读取本地对应日期的 MD 文件。
3. 对数据进行结构化解析后，智能判定“有则更新，无则追加”，批量执行单元格写入、链接设定，全列自动换行，并同步交替行背景色等格式。
4. 写入完成后，用 `get_cell_data` 校验正确性并向用户汇报写入结果。
5. **流水线闭环提醒**：写入在线表格完成后，提示用户：“在在线表格中完成评审（填写备注、参会人员并将评审状态置为通过）后，可随时执行 `/sheet-to-md` 快速将最新评审结论与备注语义融合反写至本地 Markdown 需求文档。”
