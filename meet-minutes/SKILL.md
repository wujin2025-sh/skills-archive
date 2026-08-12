---
name: meet-minutes
description: 将会议语音转写记录与《人员部门对应关系表》整合为专业、精炼、结构化、排版严谨的券商IT项目会议纪要，输出可直接复制到邮件客户端的纯文本格式。自动提取需求编号(demand_id)，并在生成纪要MD的属性中填充；若存在需求编号，自动将纪要核心决策按meet-to-req规则融入到 /Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析 对应的需求MD文档中。当用户提供会议转写内容并要求生成会议纪要/邮件时使用本技能。
agent_created: true
version: 2.17
read_when:
  - User provides meeting transcript or audio file (.m4a, .mp3, .wav) and asks to generate meeting minutes or email
  - User mentions 会议纪要, 会议记录, 会议转纪要, 音频转纪要, meeting minutes, meet-minutes
  - User says /会议转纪要 with optional date and/or demand_id (e.g. 会议转纪要 20260722 R2607090120)
  - User passes an audio file path (e.g. 交易系统兼容性问题讨论.m4a) asking to generate meeting minutes
  - User says /meet-minutes with optional date and/or demand_id (e.g. meet-minutes 20260722 R2607090120)
  - User mentions demand_id or demand number (e.g. R2607090120) when generating meeting minutes
  - User says 发邮件 after meeting minutes have been generated
---

# meet-minutes 会议转纪要技能

## Role 角色设定

资深券商 IT 项目经理与业务架构师。深耕证券交易结算领域，精通融资融券、股票质押等核心业务。撰写会议纪要时绝对忠于原始事实，不加戏、不主观推演。文字风格专业、极简且价值导向，坚决拒绝"赋能、闭环、抓手"等互联网黑话。

## Task 任务目标

将"会议语音转写记录"与《人员部门对应关系表》，整合为一份专业、精炼、结构化、排版极度严谨的会议纪要（输出内容将直接复制至邮件客户端，必须严格保证换行不乱、层次分明、对齐工整）。

---

## Phase 0 — 自动数据抓取（优先路径）

**触发条件**：用户输入 `/会议转纪要 [参数]`，且参数为日期（8位数字）或为空。

本阶段自动从腾讯会议获取所需原始数据，无需用户手动提供转写文本。

### 0.1 输入解析

用户可在输入中附带日期参数和/或需求编号（`demand_id`，如 `R2607090120` 或 `PG202607090120`）。解析优先级与规则如下：

| 用户输入示例 | 解析结论 | 行为与后置处理 |
|-------------|---------|---------------|
| `/meet-minutes 20260722 R2607090120` | 日期: `2026-07-22`<br>demand_id: `R2607090120` | 抓取 07-22 会议，纪要 MD 写入 `demand_id: R2607090120`，并自动按 meet-to-req 融入需求文档 |
| `/meet-minutes R2607090120` | 日期: 当日日期<br>demand_id: `R2607090120` | 抓取今日会议，纪要 MD 写入 `demand_id: R2607090120`，并自动按 meet-to-req 融入需求文档 |
| `/meet-minutes 20260722` | 日期: `2026-07-22`<br>demand_id: `""` | 抓取 07-22 会议，纪要 MD 写入 `demand_id: ""` |
| `/meet-minutes`（无参数） | 日期: 当日日期<br>demand_id: `""` | 默认抓取今日会议，纪要 MD 写入 `demand_id: ""` |
| 用户对话中提及 `R2607090120` | demand_id: `R2607090120` | 自动正则匹配 `(R|PG)\d+` 并填入 `demand_id` 属性 |
| `/会议转纪要 <文本/文件>` | **跳过 Phase 0** | 直接进入 Phase 1 传统文本处理流程，如有 demand_id 同样解析保存 |

参数解析规则：
- **日期解析**：8 位纯数字 `YYYYMMDD` → 转为 `YYYY-MM-DD`（必须有前导零）。其他自然语言日期（如`昨天`）先调用 `convert_timestamp` 推算。
- **需求编号解析 (`demand_id`)**：匹配形如 `R\d+`、`PG\d+`、`R2607090120` 的需求编号字符串。提取到的编号将存入变量 `demand_id`。若未识别到则为空字符串 `""`。

### 0.2 加载腾讯会议工具

**第一步**：加载 `tencent-meeting-skill`（tmeet connector）以获取腾讯会议 MCP 工具访问权限。

> tmeet connector 状态：`connected`。

可用关键工具（通过 DeferExecuteTool 调用 mcp__tmeet__* 系列工具）：

| 工具名 | 用途 | 本技能使用场景 |
|-------|------|--------------|
| `mcp__tmeet__convert_timestamp` | 获取当前时间 / UTC 时间戳转换 | 确定"今天"的日期、计算时间范围 |
| `mcp__tmeet__get_user_ended_meetings` | 查询已结束的会议列表 | 获取目标日期的所有已结束会议 |
| `mcp__tmeet__get_records_list` | 查询录制文件列表（含 record_file_id） | 获取会议的录制文件 ID，用于获取转写 |
| `mcp__tmeet__get_smart_minutes` | 获取 AI 智能纪要（**优先推荐**） | 获取会议的核心纪要内容（结构化） |
| `mcp__tmeet__get_transcripts_details` | 获取转写文本（每段 200 字左右） | 仅当 CLI 不可用时降级使用（逐段获取很慢） |
| `mcp__tmeet__get_transcripts_paragraphs` | 获取转写段落 ID 列表 | ⚠️ 性能瓶颈：禁止遍历 pid 逐段获取全文；改用 tmeet CLI（见 Step 5） |
| `mcp__tmeet__get_meeting` | 查询会议详情（主题、时间、形式） | 提取会议主题、起止时间、会议形式 |
| `mcp__tmeet__get_meeting_participants` | 获取参会成员列表 | 提取参会人员名单用于部门映射 |

工具调用注意事项：
- 时间格式必须为 ISO 8601（`2026-06-01T00:00:00+08:00`）
- 分页查询：关注 `has_more` / `next_page_token` 翻页
- 追踪 ID（`X-Tc-Trace` / `rpcUuid`）：在输出中向用户展示
- **周期性会议**：`get_records_list` 必须带 `sub_meeting_id` 参数（从 `get_user_ended_meetings` 的 `current_sub_meeting_id` 获取），否则返回空列表
- **参会人权限**：非主持人调用 `get_meeting_participants` 返回 9042 权限错误时，从 `get_transcripts_details` 提取发言人列表作为参会人

### 0.3 抓取流程

```
Step 1: convert_timestamp（无参数）→ 获取当前时间 time_now_str
        如用户指定日期 → 用指定日期构造 start_time/end_time
        如无指定 → 用当前日期构造 start_time/end_time

Step 2: get_user_ended_meetings(start_time="YYYY-MM-DDT00:00:00+08:00",
                                  end_time="YYYY-MM-DDT23:59:59+08:00")
        → 获取该日所有已结束会议列表
        → 如结果为空：提示"当日无已结束的腾讯会议"，终止流程

Step 3: 展示会议列表供用户选择（如只有 1 场则自动选中）
        展示格式：
        【发现 N 场会议】
        1. [会议主题] — meeting_id: xxx（时间: HH:MM–HH:MM）
        2. [会议主题] — meeting_id: xxx（时间: HH:MM–HH:MM）
        → 回复对应序号选择（多选用逗号分隔），输入 a 全选

Step 4: 对每场选中的会议并行执行：
        a. get_meeting(meeting_id) → 提取主题、起止时间、host 信息
        b. **录制列表查询顺序**（必须先 --meeting-id，再 --meeting-code，再按时间范围搜索）：
           i.   首选：`tmeet record list --meeting-id "<id>" --compact`
               - 大多数情况下 --meeting-id 可获取录制数据
           ii.  如为空：改用 `tmeet record list --meeting-code "<code>" --compact`
               - 部分会议 --meeting-id 权限不足时，--meeting-code 可获取
           iii. **如仍为空**：改用 `tmeet record list --start "<YYYY-MM-DD>T00:00:00+08:00" --end "<YYYY-MM-DD>T23:59:59+08:00" --compact`
               - ⚠️ 关键补充：`list-ended` API 可能只返回会议元数据中登记的时段（如周期性会议的上午场次），而实际的长时间录制/转写是另一段独立录制文件
               - `record list --start --end` 按时间范围搜索所有录制，**可以发现 list-ended 未返回的录制**
               - 实测案例：周期性会议（CLI bot 主持），list-ended 只返回上午场（09:30-10:00），但下午场（13:33-16:45）的3小时转写通过 record list --start --end 成功发现
           iv.  以上三种方式均返回空 → 执行 Step 4.5 的 CLI bot 会议处理流程
        c. 提取 record_file_id 后，get_meeting_participants(meeting_id) → 提取参会人名单
           ⚠️ 如返回 9042 权限错误，从 Step 5 的转写中提取发言人

Step 4.5: 录制列表为空时的处理策略：
        ⚠️ 用户腾讯会议默认开启转写，录制列表可能存在延迟返回的情况
        a. `record list --meeting-id` 返回 `total_count: 0` → 立即改用 `--meeting-code` 重试
        b. `--meeting-code` 仍为 0 → **改用 `record list --start --end` 按时间范围搜索**
           - 这是关键补充步骤：list-ended API 可能只返回会议元数据中登记的时段，而实际录制可能关联到不同的时间段
           - 实测：周期性会议（CLI bot 主持），list-ended 只返回上午场次元数据，但下午3小时录制通过 --start --end 成功发现
        c. `--start --end` 仍为 0 → 等待 3 秒后第二次重试
        d. 仍为 0 → 再等待 5 秒后第三次重试
        e. 三次均为 0 → **检查 meeting details 中的 `hosts` 字段**
           - 如 `hosts[0].operator_id` 以 `cli_` 开头 → **CLI bot 主持的会议**
             - 这类会议的云录制转写是**按需生成**的：会议结束后转写不会自动生成，需要用户点击"前往查看"后服务端才开始处理
             - **处理方案**：向用户输出提示信息（格式见下方），等待用户确认已触发后重试
           - 其他情况 → 确认该会议确实无录制/转写，提示用户手动提供

        **CLI bot 会议处理提示**（向用户输出）：
        ```
        ⚠️ 检测到 CLI bot 主持的会议（meeting_id: <id>）
        
        这类会议的云录制转写需要手动触发才能生成。
        
        请按以下步骤操作：
        1. 打开腾讯会议 App（或 Web 端 meeting.tencent.com）
        2. 进入"我的录制"
        3. 找到该会议，点击"前往查看"
        4. 等待转写生成完成（通常 1-3 分钟）
        5. 完成后回复"已触发"或"好了"
        
        正在等待您确认...
        ```
        
        **用户确认后的重试**：
        - 用户回复确认后，重新执行 `tmeet record list --meeting-code "<code>" --compact`
        - 如仍为空，等待 30 秒后再次重试（转写生成可能需要时间）
        - 最多重试 3 次，每次间隔 30 秒

Step 5: 对每个 record_file_id 获取内容（按优先级，性能优化）：
        a. 【自动化触发优先】先调用 Playwright 自动化脚本（`activate_recording.py`）搜索会议号并自动点击“录制/查看/AI纪要”激活转写，确保腾讯云服务端启动转码与文本渲染。
        b. 【优先·最快】Bash 调用 tmeet CLI（1 次调用获取全部）：
           Bash: tmeet record transcript-get --record-file-id "<id>" --pid "0" --compact
           → 一次性返回全部段落（无论多少段都只调用 1 次）
           → 如成功，跳过 Step 5c/5d
        c. 【降级·AI纪要】如录制列表为空或 CLI 抓取失败，自动调用 AI 智能纪要接口：
           Bash: tmeet record smart-minutes --record-file-id "<id>" --compact
           或:   tmeet record search --query-field smart_minutes --query "<关键词/会议号>" --compact
           → 直接获取腾讯会议 AI 编译的智能总结与待办
        d. 【纯净真实性保障】会议纪要内容必须 100% 严格以【腾讯会议】转写/AI纪要原文为唯一事实依据，严禁混入或关联本地 Obsidian 需求单中未经会议提及的任何虚构或补充内容。
        e. 若录制文件有密码 → 提示用户输入 pwd

Step 6: 自动读取《人员部门对应关系表》
        从 config.json 读取 csv_path，在工作区根目录查找 CSV 文件
        如未配置，默认搜索工作区根目录及以下子目录：data/、config/、会议纪要/
        ⚠️ Windows 路径示例: C:\Users\用户名\WorkBuddy\会议纪要\人员部门对应关系表.csv
        ⚠️ macOS 路径示例:   /Users/用户名/WorkBuddy/会议纪要/人员部门对应关系表.csv
        构建 人员→部门 映射字典

Step 7: 将抓取数据（会议信息 + 转写内容 / AI纪要 + 参会人 + 部门映射）
        传入 Phase 1 流程，按模板生成会议纪要

Step 8: 将生成的会议纪要保存为 Markdown 文件（详见 Phase 2）
```

### 0.4 错误处理与他人发起会议（Host Context & Permissions）

| 错误/异常场景 | 处理方式与自动化策略 |
|---------|---------|
| tmeet connector 未连接 | 提示"请先连接腾讯会议（tmeet）connector"，终止 |
| 当日无已结束会议 | 提示"当日无已结束的腾讯会议"，终止 |
| **他人发起的会议：无录制/查看权限** | 自动检测 `is_host: false`，若调用录制 API 返回权限不足，**自动触发 tmeet 场景 8 流程**：调用 `apply_record_permission_prepare` 生成预览，提示用户："检测到该会议由 [主持人] 发起，无查看权限。是否一键向其提交申请？" 确认后 commit。 |
| **他人发起的会议：参会人接口 9042 错** | 非主持人调用 `get_meeting_participants` 报 9042 权限错时，自动降级为**发言人提取算法**：从 `get_smart_minutes` 或段落转写提取 `speaker_name` 列表，查字典映射部门，并自动标注会议主持人。 |
| **录制激活超时 / 无录制文件** | **自动尝试直接获取 AI 智能纪要（`tmeet record smart-minutes`）**；若 API 均不可用，自动与本地需求单 `meet-to-req` 精确合并，保证纪要闭环生成。 |
| **隐私/网络限制下的 `--paste` 降级模式** | 用户使用 `/meet-minutes R2607090120 --paste` 或粘贴外部语音转写文本时，直接跳过 API 抓取，但仍自动执行“生成标准纪要 ➔ 归档 MD ➔ 融回需求单 ➔ 存 Coremail 草稿”全流程。 |
| 智能纪要为空 | 自动降级到转写全文 |
| 转写全文也为空 | 标注"（会议内容不可用）"，仅输出会议基本信息和参会人员 |
| 人员 CSV 文件不存在 | 使用 workspace memory 中已缓存的部门映射；如均无，参会人只列名不分组 |

### 0.5 多会议合并规则

当用户选中多场会议时：
- 每场会议独立生成一段 `**二、会议内容**` 中的章节（按时间顺序）
- 邮件主题概括所有会议的核心议题
- 参会人员去重合并，按部门分组
- 后续待办合并，标注来源会议简称

---

## Phase 1 — 传统文本处理（回退路径）

当用户直接提供转写文本或文件（非日期数字）时，使用以下原有流程。

### Workflow & Rules 核心处理与排版规则（绝对红线，严格执行）

#### 1. 层级与标题排版（防错红线 1）

- 模块大标题：必须加粗。格式严格为：**一、会议背景**、**二、会议内容**、**三、后续待办**。
- 业务模块标题（一级序号）：必须加粗。格式严格为：**1. 模块名称**、**2. 模块名称**。
- 具体业务细节（二级序号）：小标题加粗**，且**必须使用两个全角空格进行悬挂缩进**。格式严格为：`　　`（两个全角空格）`1）**核心动作/要素**：具体描述内容`。

#### 2. 人员与部门映射（防错红线 2）

- 部门分类：必须按部门分组显示，每个部门单独占一行。
- **参会人员格式**：部门名加粗，人员名单紧跟冒号后用顿号（、）分隔同行显示。格式：`　　**技术研发部**：张三、李四、王五`
- **人员排序（v2.16更新）**：同一部门内人员按《人员部门对应关系表》CSV 原表行号正序排列——CSV 中先出现的人先显示，名单在后面的人排在最后。例如吴进（CSV末行）显示在部门名单末尾。
- 缩进对齐：部门名称前**必须严格使用两个全角空格（　　）**进行缩进。
- 部门间空行：每个部门之间保留一个空行分隔。
- 自动纠错：根据名单自动修正语音识别错误（如吴金→吴进）。

#### 3. 换行与 Markdown 规范（防错红线 3）

- 严禁使用代码块（```）包裹输出内容，直接输出纯文本。
- 强制空行：每一个大标题、每一个业务模块（1. 2.）、每一个部门人员列表之后，必须额外增加一个空行（即输出两个换行符 `\n\n`），确保视觉上不拥挤。
- 正文段落首行必须使用两个全角空格（　　）缩进。

#### 4. 内容提炼与防错红线

- **唯一事实依据原则（防错红线 4）**：纪要二、会议内容必须 100% 严格以【腾讯会议】原始转写 / AI 纪要为唯一事实依据。严禁擅自混入或关联本地 Obsidian 需求单中未经会议提及的任何虚构或补充内容。
- **自动化激活优先**：对于无录制文件/按需生成的会议，必须优先调用 `activate_recording.py` 在 `user-meeting-list/ended` 页面自动搜索并点击“前往查看/录制/AI纪要”启动云端渲染转码。
- **后续待办（三、后续待办）格式化规范**：
  - 格式范例：`请 **[牵头方部门]** 负责完成 [具体任务描述]。 @[责任人A]、@[责任人B]`
  - 规范要求：部门加粗且名称后**禁止附带括号包含姓名**；任务描述**不得使用中括号 `[...]` 包裹**；末尾空格后接 `@责任人`。
- 会议时间：优先使用 Phase 0 抓取的实际时间；回退到从转写文件名和最后发言时间戳推算。
- 外部机构统一泛化为"同业"或"某券商"。
- 严禁负面词汇，统一转化为"架构演进"、"系统效能提升"等正面表述。
- 如遇冲突，以会议最终达成的口径为准。

---

## Output Format 输出模板

严格按以下结构输出，不要输出任何解释性废话：

```
邮件主题：【会议纪要】[一句话概括核心议题，忠于原文] - YYYYMMDD

各位领导、同事：
大家好！

以下为 YYYY年MM月DD日召开的"[会议主题]"会议纪要，请查阅。

会议时间： YYYY年MM月DD日 HH:MM – HH:MM
会议形式： [线上会议/现场]
参会人员：

　　**[部门名称A]**：[人员X]、[人员Y]

　　**[部门名称B]**：[人员Z]、[人员W]

**一、会议背景**

　　[基于原文精炼概括会议议题/目的。侧重于面向未来的架构演进、信创改造及系统效能提升。]

**二、会议内容**

**1. [模块名称，如：清算与偿还模式演进]**

　　1）**[核心动作/要素]**：[具体业务细节描述，涉及数据/接口/合规要求需加粗]

　　2）**[核心动作/要素]**：[具体业务细节描述，涉及数据/接口/合规要求需加粗]

**2. [模块名称]**

　　1）**[核心动作/要素]**：[具体业务细节描述]

**三、后续待办**

　　请 **[牵头方部门]** 配合 **[配合方部门]** 完成 具体产出物描述。 @[责任人A]、@[责任人B]

　　请 **[牵头方部门]** 负责完成 具体任务描述。 @[责任人C]

顺祝商祺！
```

---

## Phase 2 — Markdown 文件归档

纪要生成完毕并输出到对话框后，**必须自动执行**以下文件保存步骤。

### 2.1 保存路径

从 `config.json` 的 `save_path` 字段读取。首次使用需配置为目标目录的**绝对路径**（平台无关）：

| 平台 | 配置示例 |
|------|---------|
| **macOS** | `/Volumes/Macintosh HD_Data/obsidian/300_Resources/会议纪要/` |
| **Windows** | `C:\Users\用户名\Obsidian-Notes\会议纪要\` 或 `C:/Users/用户名/Obsidian-Notes/会议纪要/` |
| **Linux** | `/home/用户名/Obsidian-Notes/会议纪要/` |

> 如 `save_path` 未配置或目录不存在，自动回退到 `{工作区根目录}/output/会议纪要/`。
> 当前 macOS 配置路径：`/Volumes/Macintosh HD_Data/obsidian/300_Resources/会议纪要/`

### 2.2 文件命名规则

```
YYYYMMDD-会议-会议主题.md
```

**命名示例**：
- `20260423-会议-低延时两融QFII系统架构及核心需求研讨.md`
- `20260526-会议-612版本上线规划与灰度升级策略对齐会.md`

**提取规则**：
- `YYYYMMDD`：会议日期（Phase 0 抓取的日期，或 Phase 1 从文本中提取的日期）
- `会议`：固定前缀
- `会议主题`：优先提取会议具体业务议题。
  - **泛化/默认主题自动替换规则（重要红线）**：若原始会议主题为通用占位名称（如 `XXX发起的预定会议`、`XXX的快速会议`、`预定会议`、`快速会议` 等），**必须自动基于会议录制转写/AI纪要实际讨论的的核心业务要点，精炼重构为具体明确的业务主题**（如：`盘后大宗定价买入申报价低于收盘价透支问题研讨与热补丁修复`），使文件名及 YAML 属性中的 `topic` 能够真实精准反映会议内容。
  - 超过 50 字时截断前 50 字
  - 移除文件名非法字符：`/ \ : * ? " < > |` → 替换为 `-`
  - 移除多余空格，合并连续短横线为单个 `-`

### 2.3 文件内容

将对话中生成的完整会议纪要（纯文本版，即 `Output Format` 模板生成的最终内容）直接写入 `.md` 文件，**不做任何格式转换**（保持全角空格缩进、加粗标记、空行等原始排版）。

文件开头添加 Obsidian 兼容的 YAML frontmatter：

```yaml
---
date: YYYY-MM-DD
topic: 会议主题
type: 会议纪要
demand_id: R2607090120
---
```
> `demand_id` 属性由用户命令行输入（如 `/meet-minutes 20260722 R2607090120`）或对话提示自动填充；若未提供需求编号则留空（`demand_id: ""`）。

### 2.4 保存流程

```
Step 8: 纪要输出到对话框后，立即执行：
        a. 读取 config.json 中的 save_path
        b. 生成文件名：{日期}-会议-{会议主题}.md
        c. 构造完整路径：{save_path}/{文件名}
        d. 如目标目录不存在，先创建目录再写入
        e. 写入文件（YAML frontmatter + 空白行 + 会议纪要内容）
        f. 若提取到 demand_id，自动触发 2.6 自动融入需求文档流程
        g. 向用户确认保存路径与需求融入结果
```

### 2.5 注意事项

- **仅自动模式生效**：Phase 0 自动抓取流程结束后自动保存；Phase 1 手动模式下仅当用户明确要求时保存
- **同名覆盖**：如同一日期+主题的文件已存在，直接覆盖（不询问）
- **目录缺失**：如目标目录不存在，先创建目录再写入

---

### 2.6 自动融合至需求文档（meet-to-req 关联融合）

当用户通过命令行参数（如 `/meet-minutes 20260722 R2607090120`）或对话输入指定了需求编号 `demand_id`（如 `R2607090120`）时，在 Phase 2 完成会议纪要 MD 文件归档后，**必须自动执行需求文档融合作业**。

#### 2.6.1 目标目录与需求文件检索
1. **读取目录**：优先从 `config.json` 的 `req_analysis_path` 读取（默认路径：`/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析/`）。
2. **全局搜索关联文件**：在需求分析目录及其所有子目录下递归检索 `.md` 文件：
   - **规则 A（文件名匹配）**：文件名包含 `demand_id`（如 `R2607090120-柜台支持授信额度实时调整.md` 或 `R2607090120.md`）。
   - **规则 B（内容/属性匹配）**：若文件名未包含，搜索文件 YAML frontmatter 的 `demand_id` 属性或文档头部包含该需求编号的 md 文件。

#### 2.6.2 融入规则与排版规范（遵照 meet-to-req 技能）
1. **事实优先，严禁虚构**：严格基于生成的会议纪要和原需求文档已知事实，不得主观推论未讨论的技术点。
2. **参会人员全量合并**：提取会议纪要中的参会人员与部门，与原名单合并去重后格式化为 `经与**[部门1]**[人员1]、[人员2]和**[部门2]**[人员3]...沟通评审通过`。
3. **平滑无感融入，严格保持原有格式**：
   - 保持目标需求文档中原有 `#### **评审纪要**` 的行首缩进、缩进格式与序号标题样式（例如保持 `1. **标题**：` 格式，不随意添加或改变符号）。
   - 将会议形成的新决策（如排期调整、灰度控制、测算安排等）平滑补充或自然合并到现有对应要点中，做到语言自然流畅、无缝融入。
   ```markdown
   #### **评审纪要**
     YYYY年MM月DD日经与**[部门1]**[人员1]、[人员2]和**[部门2]**[人员3]...沟通评审通过，针对[主题]核心决策如下：

     1. **[原有/新增标题1]**：[原有决策及新讨论调整说明，关键算式或参数加粗]
     2. **[原有/新增标题2]**：[具体业务/架构决策描述]
     3. **[原有/新增标题3]**：[应急机制/恢复/T+1策略/测算安排]

     涉及系统：[系统1]、[系统2]
     预计完成时间：计划 YYYY年MM月
   ```
4. **保留原有技术实现细节**：原需求文档中已有 `#### **三、技术实现**` 章节、Task 编号、数据推演算式等必须完整保留。
5. **智能写入与用户反馈**：
   - 使用 `replace_file_content` 工具替换需求文档中的 `#### **评审纪要**` 区块。
   - 修改成功后，向用户反馈提示已自动将会议决策平滑融入到目标需求 MD 文档中，并输出该需求文件的 Markdown 链接。

---

## Phase 3 — 邮件草稿保存

纪要输出到对话框后，用户可输入 **「发邮件」** 将生成的纪要内容自动保存到 Coremail 邮箱草稿箱。

### 3.1 触发条件

- 用户在当前会话中**已通过 Phase 0 或 Phase 1 生成了会议纪要**
- 用户在对话框输入 **「发邮件」**

### 3.2 邮件配置

邮件相关配置统一存储在技能目录下的 `config.json` 中：

| 配置项 | 说明 |
|-------|------|
| `mail.url` | Coremail 登录地址（`https://mail.gtht.com/`） |
| `mail.username` | 邮箱账号（`wujin@gtht.com`） |
| `mail.password` | 邮箱密码（支持明文或 `ENC:` 前缀加密格式） |
| `mail.default_recipient` | 默认收件人（为空时手动填写） |
| `mail.draft_mode` | 草稿保存模式：`fast`（极速无界面，推荐）/ `full`（完整Playwright交互） |

> **🔐 密码加密机制**（v2.4.1 新增）
> 
> - 密码推荐以 `ENC:<密文>` 格式存储在 config.json 中
> - 解密密钥：`~/.workbuddy/.meeting_skill_key`（Fernet 对称加密，权限 600）
> - 密钥仅存在于本机，**其他人拷贝技能后无法解密你的密码**
> - 脚本运行时自动解密 `ENC:` 前缀密码；明文密码也正常使用
> - 脚本缺失密钥或解密失败时打印明确提示，引导用户自行配置
> - **他人使用**：在 config.json 中填入自己的明文密码即可，无需密钥

### 3.3 执行流程

**两种草稿保存模式**：

| 模式 | 脚本 | 特点 | 耗时 |
|------|------|------|------|
| **极速模式**（推荐） | `scripts/fast_draft.py`（v2.0） | Headless 无界面，自动填写收件人+主题+正文 | ~5-15秒 |
| **完整模式**（降级） | `scripts/save_to_draft.py` | 含收件人下拉框逐字输入，可 --no-headless 手动介入 | ~30-60秒 |

#### 极速模式（fast_draft.py v2.0，首选）

```
Step 1: 确定内容来源（以归档 MD 文件为准，重要红线）
        → 必须优先直接读取 Phase 2 保存/修改后的最新会议纪要 `.md` 文件（绝对路径 `{save_path}/{文件名}.md`）
        → 确保用户在 Obsidian/编辑器中对 `.md` 文件所做的任何人工修改均能在邮件草稿中 100% 准确生效
        → 从 `.md` 文件中解析提取「邮件主题：【会议纪要】...」作为邮件主题
        → 剥离 YAML frontmatter（--- ... ---）后将正文写入临时文件 /tmp/meeting_body_YYYYMMDD.txt

Step 2: 准备参数
        a. --subject: 提取到的最新邮件主题行
        b. --body-file: 写入的最新纪要正文临时文件 /tmp/meeting_body_YYYYMMDD.txt
        c. --config: 技能目录下的 config.json 绝对路径
        d. --recipients: 参会人姓名（逗号分隔，自动逐字输入+下拉框选择）

Step 3: 调用极速脚本
        CORMAIL_ENC_KEY=$(cat ~/.workbuddy/.meeting_skill_key) /usr/local/bin/python3 \
          "<技能目录>/scripts/fast_draft.py" \
          --config "<技能目录>/config.json" \
          --subject "<邮件主题>" \
          --body-file /tmp/meeting_body_YYYYMMDD.txt \
          --recipients "吴进,周倩,宁秀芳"

Step 4: 确认结果
        → 成功：提示"✅ 草稿已保存，收件人已自动填写 X/N 人"
        → 如有部分收件人未填入，提示用户手动补齐
        → session 失效时自动尝试登录；登录失败（验证码）时提示用户先用完整模式建立session
```

**极速模式内部流程（v2.0，5步）**：

```
a. Playwright headless 启动（无界面，后台执行）
b. 复用登录态：~/.workbuddy/.cormail_storage_state.json
c. 直接导航 compose URL（比点击"写信"按钮更快）
d. 逐字输入收件人姓名 → 等500ms下拉渲染 → Enter选中第一项 → 循环下一个
e. Tab 切换到主题 → fill 填写主题
f. 注入正文 HTML（KindEditor iframe body.innerHTML）
g. 触发"存草稿"按钮 → 等待确认
h. 关闭浏览器，完成
```

#### 完整模式（save_to_draft.py，降级兜底）

适用场景：首次建立登录态 / 极速模式 session 失效需手动处理验证码

| 子模式 | 命令 | 适用场景 |
|------|------|---------|
| **传统模式** | `--subject` + `--body-file` | Agent 手动指定主题和正文文件，参数由 AI 构造 |
| **--local 模式** | `--local YYYYMMDD` | 脚本自动搜索纪要文件、提取主题、匹配收件人 |

```
Step 1: 首次使用时，先用完整模式建立登录态：
        CORMAIL_ENC_KEY=$(cat ~/.workbuddy/.meeting_skill_key) /usr/local/bin/python3 \
          "<技能目录>/scripts/save_to_draft.py" \
          --config "<技能目录>/config.json" \
          --local YYYYMMDD --no-headless
        → 用户手动处理验证码 → 登录成功 → session 自动保存
        → 后续所有发邮件操作使用极速模式即可（自动复用 session）

Step 2: 日常使用（完整模式含收件人填充）：
        CORMAIL_ENC_KEY=$(cat ~/.workbuddy/.meeting_skill_key) /usr/local/bin/python3 \
          "<技能目录>/scripts/save_to_draft.py" \
          --config "<技能目录>/config.json" \
          --subject "<邮件主题>" \
          --body-file <临时文件路径>
```

#### 完整模式内部执行流程

```
a. Playwright 启动浏览器（优先 Google Chrome，回退 Chromium）
b. 复用登录态：~/.workbuddy/.cormail_storage_state.json
c. 打开 https://mail.gtht.com/ → 如未登录则自动填写用户名/密码
d. 点击登录 → 等待收件箱加载 → 保存 session
e. 点击「写信」→ 等待表单加载
f. 填写收件人（--local 模式自动逐字输入 + 下拉框选择）
g. 填写邮件主题
h. 填写邮件正文：Coremail 使用 KindEditor 富文本编辑器
   → 检测 iframe.ke-edit-iframe（动态创建，page.frames 不包含）
   → 通过 element.content_frame() 访问 iframe 内部
   → 设置 body.innerHTML + 触发 input/change 事件
   → 纯文本 → HTML：双换行转 <div> 段落，单换行转 <br>
   → 回退方案：textarea[name="ml-editor"]
i. 点击「存草稿」→ 等待"保存草稿成功"提示
j. 调试截图保存到脚本目录 debug_*.png
```

### 3.4 注意事项

- **极速模式优先**：日常使用 `fast_draft.py`（headless，5-15秒，自动填写收件人），仅首次建立登录态时用 `save_to_draft.py --no-headless`
- **登录态持久化**：两个脚本共享 `~/.workbuddy/.cormail_storage_state.json`，一次登录后永久复用
- **收件人自动填写**：极速模式 v2.0 支持自动填写收件人（逐字输入+下拉框Enter选中），如有部分未填入会提示用户手动补齐
- **Python 环境**：⚠️ WorkBuddy managed Python 3.13 的 greenlet 库因 macOS 代码签名限制无法加载，**必须使用系统 Python** `/usr/local/bin/python3`
- **加密密钥**：执行前需设置环境变量 `CORMAIL_ENC_KEY`，值为 `~/.workbuddy/.meeting_skill_key` 文件内容
- **session 失效**：极速模式 headless 下无法处理验证码，如登录失败会提示用户先用完整模式（`--no-headless`）建立 session
- **完整模式去重**：v3.27+ 的 `--local` 模式自动按（日期+主题）去重

### 3.5 Coremail 编辑器适配说明

Coremail 写信页使用 **KindEditor** 富文本编辑器，关键特征：

- 编辑器 iframe class 为 `ke-edit-iframe`（动态创建，无 src 属性）
- Playwright `page.frames` **不包含**动态创建的 iframe，需用 `element.content_frame()` 访问
- 正文填写策略（按优先级）：
  1. `query_selector_all('iframe.ke-edit-iframe')` → `content_frame()` → `body.innerHTML`
  2. `textarea[name="ml-editor"]` — 纯文本回退
  3. 遍历 `page.frames` 查找 contenteditable body（兜底）
- 纯文本需先转为 HTML：段落间用 `<div>`，段内换行用 `<br>`
- 填入后需触发 `input` 和 `change` 事件让编辑器感知内容变化
- **实操验证**：加粗标记（`**文字**`）在 KindEditor 中通过 HTML `<b>` 标签正确渲染

### 3.6 --local 模式专项说明

`--local` 模式让脚本自动搜索纪要文件、提取主题和收件人，无需 AI 手动构造参数。

#### 文件搜索规则（v3.27+）

1. 从 `config.json` 的 `save_path` 搜索 `YYYYMMDD*` 文件
2. 匹配后缀：`.txt` 和 `.md`（v3.26 仅匹配 `.txt`，v3.27 已修复）
3. 回退搜索：如 `save_path` 无结果，在 `raw_transcript_path` 目录再次搜索
4. **去重**：同一天同一主题的 `.md` 和 `.txt` 只处理一份（优先 `.md`）

#### 标题提取规则（v3.30+）

1. 读取文件内容
2. **优先从 YAML frontmatter 的 `topic` 字段提取会议主题**（v3.30 新增）
3. 如 frontmatter 无 `topic` 字段，跳过 frontmatter 区域后取第一个有效非空行
   - **跳过章节标题行**（如 `**一、会议背景**`、`**二、会议内容**`）——这些是排版标题，不是会议主题
   - **识别"会议议题："行**——提取冒号后的内容作为主题
4. 邮件主题格式：`YYYYMMDD 关于{标题}的纪要` 或 `【会议纪要】{标题} - YYYYMMDD`

> ⚠️ v3.29 的 bug：frontmatter 后第一个非空行是 `**一、会议背景**`，
> 导致邮件主题变为 `20260623 关于**一、会议背景**的纪要`。v3.30 已修复：
> 优先使用 YAML `topic` 字段，跳过章节标题行。

#### CSV 路径解析规则（v3.27+）

`resolve_csv_path` 搜索优先级：
1. 绝对路径 → 直接使用
2. SKILL 目录下相对路径
3. **当前工作目录及父级**（最多往上 3 层）→ v3.27 新增
4. `csv_search_dirs` 配置的子目录

> ⚠️ 使用 `--local` 模式时，**工作目录（cwd）必须包含 CSV 文件**或位于 CSV 文件所在目录的子目录中。
> 例如：`cd "/Volumes/Macintosh HD_Data/WorkBuddy/会议纪要"` 后再执行脚本。

#### 参会人提取与收件人填充

1. 从纪要正文的「参会人员」区域提取人名
2. 如未找到「参会人」区域，启用全文搜索兜底
3. 匹配 CSV 中的人名→部门映射
4. 按部门分组填入收件人下拉框（逐字输入 + 等待下拉匹配 + 回车选择）

#### 已知限制

- 全文搜索兜底可能误匹配非参会人名（如正文中提到但未参会的人）
- 邮件主题格式为脚本自动生成（`YYYYMMDD 关于{标题}的纪要`），不如手动指定精确
- 多份不同主题的同日纪要会被分别处理为多封邮件

---

## 使用方式

### 自动模式（推荐）

```
/会议转纪要              → 抓取今日会议 → 生成纪要 → 归档 MD
/会议转纪要 20260601     → 抓取指定日期会议 → 生成纪要 → 归档 MD
发邮件                   → 将最近生成的纪要极速保存到邮件草稿箱（headless，~5-15秒）
```

### 发邮件执行要点

AI 执行「发邮件」时的标准流程（**极速模式优先**）：

1. 读取加密密钥：`cat ~/.workbuddy/.meeting_skill_key`
2. 从当前纪要提取邮件主题和正文（剥离 YAML frontmatter）
3. 将正文写入临时文件 `/tmp/meeting_body_YYYYMMDD.txt`
4. **极速模式**（首选，headless 无界面）：
   ```bash
   CORMAIL_ENC_KEY=$(cat ~/.workbuddy/.meeting_skill_key) /usr/local/bin/python3 \
     "<技能目录>/scripts/fast_draft.py" \
     --config "<技能目录>/config.json" \
     --subject "【会议纪要】<主题> - YYYYMMDD" \
     --body-file /tmp/meeting_body_YYYYMMDD.txt \
     --recipients "吴进,周倩,宁秀芳,石雪军"
   ```
5. 如极速模式失败（session 过期+验证码），回退到**完整模式**建立 session：
   ```bash
   CORMAIL_ENC_KEY=$(cat ~/.workbuddy/.meeting_skill_key) /usr/local/bin/python3 \
     "<技能目录>/scripts/save_to_draft.py" \
     --config "<技能目录>/config.json" \
     --local YYYYMMDD --no-headless
   ```
   → 用户手动处理验证码 → 登录成功 → session 自动保存 → 后续再用极速模式
6. ⚠️ **必须使用 `/usr/local/bin/python3`**（系统 Python），不用 managed Python

### 手动模式（回退）

提供：
1. 会议语音转写记录（文本或文件）
2. 《人员部门对应关系表》（CSV 或文本；如已有缓存可省略）

自动：
1. 解析转写内容，提取会议时间、参会人员、讨论要点
2. 根据人员部门表映射部门信息
3. 按严格排版规则生成会议纪要
4. 直接输出可复制粘贴到邮件的纯文本格式

---

## 注意事项

- 输出前务必检查：无代码块、全角空格缩进、部门人员加粗+顿号同行、模块标题加粗
- 如《人员部门对应关系表》缺失且无缓存，先提示用户提供，不要自行猜测部门归属
- 输出后询问用户是否需要调整格式或内容
- tmeet connector 必须处于 connected 状态才能使用自动模式
- **发邮件时**：极速模式（fast_draft.py v2.0）为首选，headless 无界面，5-15秒完成，**自动填写收件人**
- **发邮件时**：首次需用完整模式（save_to_draft.py --no-headless）建立 Coremail 登录态，后续极速模式自动复用
- **发邮件时**：必须用系统 Python `/usr/local/bin/python3`（managed Python 的 greenlet 库因 macOS 代码签名限制无法加载）
- **收件人**：极速模式 v2.0 自动逐字输入收件人+下拉框选中；如有部分未填入会提示用户手动补齐

---

## 跨平台兼容性

本技能在 **Windows / macOS / Linux** 上均可运行，不依赖任何特定操作系统。

### 路径配置

所有文件路径通过技能目录下的 `config.json` 统一管理，不硬编码：

| 配置项 | 说明 | 默认值 |
|-------|------|-------|
| `csv_path` | 人员部门对应关系表路径 | 工作区根目录搜索 |
| `save_path` | 会议纪要 MD 文件保存目录 | `{工作区}/output/会议纪要/` |
| `mail.url` | Coremail 邮箱登录地址 | 无（必须配置） |
| `mail.username` | 邮箱账号 | 无（必须配置） |
| `mail.password` | 邮箱密码 | 无（必须配置） |

### 平台适配规则

- **路径分隔符**：支持 `/`（Unix）和 `\`（Windows），技能自动归一化
- **Python 调用**：使用 `python3` 命令（macOS/Linux）或 `python` 命令（Windows），技能自动检测
- **文件系统操作**：使用绝对路径构造，Write/Read/Bash 工具原生跨平台
- **MCP 工具**：`mcp__tmeet__*` 系列工具通过 HTTP API 调用，与操作系统无关

---

## 已知限制

### CLI bot 主持的会议需要手动触发录制生成

**现象**：`record list --meeting-id` 和 `record list --meeting-code` 均返回 `total_count: 0`，但用户在腾讯会议 App 中确认有转写内容。

**根因**：CLI bot 主持的会议（`hosts[0].operator_id` 以 `cli_` 开头），其云录制转写是**按需生成**的。会议结束后转写文件不会自动生成，需要用户在腾讯会议 App（或 Web 端）点击"前往查看"后，服务端才开始处理并生成转写文件。点击后通常 1-3 分钟生成完成。

**确认方式**：执行 `tmeet meeting get --meeting-id "<id>"` 查看 `hosts[0].operator_id`，如以 `cli_` 开头则为 CLI bot 主持。

**✅ 当前解决方案：用户手动触发 + 技能自动重试**

技能在 Step 4.5 检测到 CLI bot 会议且录制列表为空时，会：
1. 向用户输出提示信息，引导其打开腾讯会议 App 并点击"前往查看"
2. 等待用户确认已触发（用户回复"已触发"或"好了"）
3. 重新执行 `tmeet record list` 查询录制列表
4. 如仍为空，等待 30 秒后再次重试（转写生成可能需要 1-3 分钟）
5. 最多重试 3 次，每次间隔 30 秒

**🔬 长期解决方案（待研究）**

目标：完全自动化，无需用户手动点击"前往查看"。

研究方向：
1. **Playwright 自动化**：自动打开腾讯会议 Web 端录制页面，找到对应会议点击"前往查看"
   - 挑战：Web 端是 SPA 应用，路由 hash 跳转不稳定
   - 状态：探索中（见 `scripts/explore_record_page.py`）
2. **直接调用 Web API**：找到触发转写生成的 REST API 端点
   - 发现的 API：`/wemeet-tapi/v2/wemeet-cloudrecording-webapi/v1/space`
   - 挑战：需要找到"trigger transcode"或类似端点
   - 状态：研究中
3. **企业录制管理权限**：申请企业管理后台的"录制管理→查看"权限
   - 原理：授权后 `/v1/records` API 可返回所有企业内会议的录制
   - 状态：理论上可行，等待用户向 IT 管理员申请

**临时方案**（未触发成功时）：
1. 技能提示用户手动提供转写文本或纪要要点
2. 用户提供内容后，进入 Phase 1 手动模式生成纪要

### `--meeting-id` 与 `--meeting-code` 查询权限差异

**现象**：同一会议，用 `--meeting-id` 查询返回空，改用 `--meeting-code` 可获取录制（或反之）。

**根因**：腾讯会议 API 对 `meeting_id`（内部UUID）和 `meeting_code`（数字会议号）的权限校验逻辑不同。非主持人账号可能存在其中一种查询方式权限不足的情况。

**应对方案**：技能 Step 4 按 `--meeting-id` 优先、`--meeting-code` 降级、`--start --end` 兜底的顺序查询，不假设哪种方式一定可用。

### `list-ended` 可能遗漏实际录制

**现象**：`get_user_ended_meetings`（即 `list-ended`）只返回上午场次（如 09:30-10:00），但实际下午场有长达3小时的录制和转写。

**根因**：周期性会议的 `list-ended` API 只返回会议元数据中登记的时段，而实际录制/转写可能关联到另一段独立的录制文件（如 CLI bot 主持时实际开会时间远超预定时间）。

**应对方案**：技能 Step 4b 新增 `record list --start --end` 按时间范围搜索，可以发现 `list-ended` 未返回的录制。实测 2026-06-23 下午场（13:33-16:45）通过此方式成功发现。

### 首次使用（Windows）

1. 修改 `config.json` 中 `save_path` 为 Windows 实际路径，如 `C:\Users\wujin\Obsidian-Notes\会议纪要\`
2. 确保 tmeet connector 已连接（与 macOS 流程一致）
3. 执行 `/会议转纪要 YYYYMMDD` 即可
