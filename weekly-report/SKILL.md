---
name: weekly-report
description: "Generate a weekly C-level/cross-department briefing from recent Obsidian work notes, focused on margin trading, low-latency trading, clearing, and related fintech delivery outcomes."
version: 2.3.0
tags: [obsidian, fintech, weekly-report, business-briefing]
---

# weekly-report

Senior BA weekly briefing skill: scans recent Obsidian vault notes and produces an ultra-short C-level/cross-department weekly report. The report is designed for a 3-minute oral briefing, not for detailed reading.

## Persona used during extraction

Act as a senior IT Business Architect / BA with 15 years in securities — especially securities margin trading, stock pledge, and retail/institutional micro-trading. Extract only actionable, concrete progress; infer business meaning from code or data dictionaries.

## Invocation

```bash
python3 "/Volumes/Macintosh HD_Data/obsidian/.agents/skills/weekly-report/scripts/weekly_report.py"
```

## Inputs / paths

Vault root: `/Volumes/Macintosh HD_Data/obsidian`

Include:
- `/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析`
- `/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求管理`
- `/Volumes/Macintosh HD_Data/obsidian/100_Projects/设计文档`
- `/Volumes/Macintosh HD_Data/obsidian/100_Projects/进度跟踪`
- `/Volumes/Macintosh HD_Data/obsidian/100_Projects/邮件管理`
- `/Volumes/Macintosh HD_Data/obsidian/300_Resources/会议纪要`
- `/Volumes/Macintosh HD_Data/obsidian/300_Resources/邮件管理`
- `/Volumes/Macintosh HD_Data/obsidian/300_Resources/电话纪要`

Exclude:
- `/Volumes/Macintosh HD_Data/obsidian/100_Projects/设计文档/个微交易引擎细则/images`
- `/Volumes/Macintosh HD_Data/obsidian/300_Resources/复盘总结`
- `*_Index.md`, `*Index*.md`, `AGENTS.md`, `profile.md`

Output directory: `/Volumes/Macintosh HD_Data/obsidian/300_Resources/工作周报`

File name: `YYYYMMDD-工作周报.md` (e.g. `20260717-工作周报.md`)

## Mandatory extraction rules (strict)

> [!IMPORTANT]
> **核心原则：【全量扫描 + 3分钟自然口语短句】—— 直接作为 C-level 口头汇报底稿。**

- Do NOT fabricate. If a section has no material evidence, output exactly: `本周未记录` or `暂无卡点与资源诉求`
- Surface concrete system names, interface names, core rule changes, and data migration/validation results.
- Remove communication-action sentences (e.g., “开会讨论了”, “给xx发了邮件”, “各位领导”、“参会人员”等). Keep only the final conclusion.
- When encountering code, tables, or long data dictionaries, compress to a compact business-meaningful sentence.
- Each output item must be a single highly-compressed spoken sentence (≤80 words), no deep technical detail.
- **全量覆盖原则（Full Coverage Rule）**：`100_Projects/需求分析`、`100_Projects/需求管理`、`300_Resources/会议纪要`、`邮件管理` 及 `300_Resources/电话纪要` 目录下的所有本周变动点（近 5 天内修改或文件名包含本周日期），必须在周报【核心推进】章节中全量逐一呈现，不得截断遗漏。（注意：`300_Resources/复盘总结` 不纳入周报扫描）。



- **### 汇报要点（C-level 3分钟口头汇报底稿）**：位于 `**周期**` 下方、分隔符 `---` 上方。专为 3 分钟口头汇报设计。
  - **只说事实，不发表评价（Fact-Only Rule）**：必须严格以客观事实为唯一依据，只陈述具体的动作、结论与交付结果，**严禁使用任何主观评价或形容词词汇**（如“大幅提升”、“强力拦截”、“准确展示”、“完美解决”等）。
  - **通俗口语化**：使用自然口语与通俗平直的日常汇报表达（如：“重点解决了25年滞留的历史遗漏问题”、“下周组会沟通方案”、“还需要我们逐个协调推进”），严禁出现英文需求单号（如 R2607210113）、机械报文接口号或冗长的书面专有名词。可以直接作为开会口头念诵的发言稿。
  - **单一事项原则（Single Focus Rule）**：每一个【汇报要点】**必须且只能聚焦于一件核心需求或独立事项**，严禁将多项不同的需求或无关动作强行拼凑合并在一句话中。
  - **严格一句话短句**：每一个编号点**必须且只能为一句话短句**（仅含一个句号 `。`），表达完整自洽。
  - **语句完整与逻辑自洽**：结构完整、语气流畅（包含“主体/动作 + 客观事实/交付产出”），具备明确的因果与业务逻辑闭环。



- **Section 1 (Executive Summary)**: Must use `1) 2) 3)` numbered list format, strictly covering 1) 系统稳定性, 2) 核心交付, 3) 进度预警.
- **Section 2 (Key Projects & Impact)**: Must use `1. 2. 3.` numbering, and each item MUST start with bold bracket category tag `**【模块/系统】**` (e.g. `1. **【个微两融/柜台】** ...`), strictly limited to 1 sentence. All scanned items from 需求分析、会议纪要及复盘总结 MUST be presented fully.
- **Section 3 (Blockers & Asks)**: Must use `1. 2. 3.` numbering, starting with bold bracket category tag `**【卡点分类/系统】**`, and explicitly state `诉求：<需要领导协调的事项>`, strictly limited to 1 sentence.
- **Section 4 (Next Actions)**: Must use `1. 2. 3.` numbering, starting with bold bracket category tag `**【模块/方向】**`, strictly limited to 1 sentence. Include unresolved Action Items from GOBE reflections.



## Mandatory output template (do not alter section names)

```text
**周期**：MM/DD - MM/DD

### 汇报要点

1. <提炼要点 1：通俗口语化表达，控制在一句话长度（含主体/动作/结果）>
2. <提炼要点 2：通俗口语化表达，控制在一句话长度（含主体/动作/结果）>
3. <提炼要点 3：通俗口语化表达，控制在一句话长度（含主体/动作/结果）>

---

**1. 本周核心结论**

1) 系统稳定性：<系统稳定性及隐患排查总结，如：本周核心系统运行平稳，无生产事故；提前封堵了X隐患。>
2) 核心交付：<重大项目/需求交付进展，如：本周「X项目」取得决定性进展，核心Story已完成开发并“结束发布”上线。>
3) 进度预警：<逾期或阻塞情况，如：部分下游系统仍存在逾期或阻碍，需协调X团队加速排期联调。>

---

**2. 核心推进 (Key Projects & Impact)**

1. **【模块/系统】** <业务价值与技术动作：具体动作，支撑了B业务/降低了C风险/提升了D性能。>
2. **【模块/系统】** <交付状态与影响：当前所处阶段（如：开发中/已提测/已上线），对下游的影响。>
3. **【模块/系统】** <协同进展与风险防范：完成了关键技术对接或评审，保障交付节点。>

---

**3. 关键阻塞点与资源诉求 (Blockers & Asks)**

1. **【阻塞/卡点/关联系统】** <卡点陈述：客观陈述问题与逾期事项。>。诉求：<明确指出需要领导协调的部门或资源。>

---

**4. 下周核心 Action**

1. **【模块/方向】** <核心交付点：确保项目如期推进的决定性动作。>
2. **【模块/方向】** <关键支撑点：重点关注的业务逻辑、规则落地或数据校验。>
3. **【模块/方向】** <改进/协同点：技术效率提升或跨团队联调。>
```

## 汇报逻辑建议
- 汇报模版建议详见 `references/briefing-logic.md`，核心遵循“结论先行、业务化表达、机会式汇报”。
- Each item must fit on one spoken sentence when read aloud.
- Section 1 uses `1) 2) 3)` numbered list format, NOT a single paragraph. Each entry covers one angle: stability / core delivery / risk alert.
- Sections 2–4 use `1. 2. 3. ...` numbering, and every item MUST start with bold category tags `**【模块/系统】**`.
- Section 3 MUST include explicit `诉求：...` for leadership resource coordination.
- The report is optimized for a 3-minute verbal executive summary.

## Post-generation user amendment rules

- **手工修改与补充保护原则（Manual Modification Preservation Rule）**：周报 md 生成后，若用户在文件内部或对话框里对【汇报要点】或正文内容进行了手工修改、替换或追加，**绝对不得自动删除或覆盖用户手工修改的内容**。用户的手工修改是对自动生成周报的权威补充。AI 的职责是在 100% 保留用户补充内容的前提下，优化组织语言（使其符合通俗口语化、单句短句、纯事实陈述等规范），并将其与自动梳理的内容有机融合。
- **用户追加/修改内容融入**：当用户提供追加/修改内容时，必须先读取已有周报文件，保留用户手工修改的要点与补充，将用户内容自然融入对应章节（业务化表达、风格统一），覆盖写入，不得新建文件。
- **触发重新调整**：当用户在对话框输入 `已修改` 或 `upt` 时，表示用户已在本地直接编辑了周报文件。此时必须：① 读取最新周报文件；② 严格保留用户新增/修改的汇报要点，仅对语言组织、标点与单句结构进行润色；③ 覆盖写入，不得新建文件。
- **写入工具**：始终使用文件写入工具或覆盖写入周报。


