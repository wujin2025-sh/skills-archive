---
name: self-improvement
description: "捕获经验教训、错误与纠错信息，实现持续自我迭代与改进。在以下情况下使用：(1) 命令或操作意外失败，(2) 用户对 AI 做出纠错（如“不对，这错了...”、“实际上应该是...”），(3) 用户请求目前不存在的能力，(4) 外部 API 或工具报错，(5) 发现自身知识过期或不准确，(6) 找到了针对重复性任务更好的处理方法。在执行重大任务前也可提前复盘学习记录。"
metadata:
---

# 自我改进与知识积累技能 (Self-Improvement Skill)

将积累的经验、教训和错误日志记录到 Markdown 文件中，以支持持续自我改进。AI Agent 后续可将其转化为问题修复，并将重要经验提升（Promote）至项目记忆中。

## 1. 首次使用初始化

在记录任何内容之前，请确保项目或工作区根目录下存在 `.learnings/` 目录及相关文件。若不存在，请自动创建：

```bash
mkdir -p .learnings
[ -f .learnings/LEARNINGS.md ] || printf "# Learnings\n\n开发过程中捕获的纠错、洞察与知识盲区。\n\n**分类**: correction | insight | knowledge_gap | best_practice\n\n---\n" > .learnings/LEARNINGS.md
[ -f .learnings/ERRORS.md ] || printf "# Errors\n\n命令失败与集成错误。\n\n---\n" > .learnings/ERRORS.md
[ -f .learnings/FEATURE_REQUESTS.md ] || printf "# Feature Requests\n\n用户提出的能力需求。\n\n---\n" > .learnings/FEATURE_REQUESTS.md
```

切勿覆盖已有文件。如果 `.learnings/` 目录已被初始化，则无需重复操作。

除非用户明确要求此级别的细节，否则不要记录密钥、Token、私钥、环境变量或完整的源/配置文件。相比于原始命令输出或完整转录，优先使用简短摘要或脱敏摘录。

如果希望使用自动提醒或设置协助，请使用 [Hook 集成](#hook-集成) 中描述的 Hook 工作流。

## 2. 快速速查表

| 场景 | 对应操作 |
|-----------|--------|
| 命令/操作失败 | 记录至 `.learnings/ERRORS.md` |
| 用户纠正你的错误 | 记录至 `.learnings/LEARNINGS.md`，分类标注为 `correction` |
| 用户希望增加缺失功能 | 记录至 `.learnings/FEATURE_REQUESTS.md` |
| API / 外部工具失败 | 记录至 `.learnings/ERRORS.md`，并注明集成细节 |
| 发现知识过期或不准 | 记录至 `.learnings/LEARNINGS.md`，分类标注为 `knowledge_gap` |
| 找到更好的替代方法 | 记录至 `.learnings/LEARNINGS.md`，分类标注为 `best_practice` |
| 简化/强化重复模式 | 记录/更新 `.learnings/LEARNINGS.md`，标注 `Source: simplify-and-harden` 及稳定的 `Pattern-Key` |
| 与现有记录相似 | 使用 `**See Also**` 关联，并考虑提高优先级 |
| 具有普适性的经验 | 提升（Promote）至 `CLAUDE.md`、`AGENTS.md` 或 `.github/copilot-instructions.md` |
| 工作流优化 | 提升至 `AGENTS.md`（OpenClaw 工作区） |
| 工具陷阱/避坑指南 | 提升至 `TOOLS.md`（OpenClaw 工作区） |
| 行为模式指导 | 提升至 `SOUL.md`（OpenClaw 工作区） |

## 3. OpenClaw 配置（推荐）

OpenClaw 是本技能的主要运行平台。它使用基于工作区的 Prompt 注入与自动技能加载。

### 安装

**通过 ClawdHub 安装（推荐）：**
```bash
clawdhub install self-improving-agent
```

**手动安装：**
```bash
git clone https://github.com/peterskoett/self-improving-agent.git ~/.openclaw/skills/self-improving-agent
```

根据原始仓库适配重构：https://github.com/pskoett/pskoett-ai-skills/tree/main/skills/self-improvement

### 工作区结构

OpenClaw 会在每次会话中注入以下文件：

```
~/.openclaw/workspace/
├── AGENTS.md          # 多 Agent 工作流、任务委派模式
├── SOUL.md            # 行为准则、性格偏好、核心原则
├── TOOLS.md           # 工具能力、集成注意事项
├── MEMORY.md          # 长期记忆（仅主会话）
├── memory/            # 每日记忆文件
│   └── YYYY-MM-DD.md
└── .learnings/        # 本技能的日志文件目录
    ├── LEARNINGS.md
    ├── ERRORS.md
    └── FEATURE_REQUESTS.md
```

### 创建学习日志文件

```bash
mkdir -p ~/.openclaw/workspace/.learnings
```

然后创建日志文件（或从 `assets/` 复制）：
- `LEARNINGS.md` — 纠错、知识盲区、最佳实践
- `ERRORS.md` — 命令失败、异常报错
- `FEATURE_REQUESTS.md` — 用户提出的功能需求

### 提升（Promotion）目标位置

当积累的经验证明具有普适性时，将其提升至工作区文件中：

| 经验类型 | 提升至 | 示例 |
|---------------|------------|---------|
| 行为模式 | `SOUL.md` | "保持精炼，避免免责声明套话" |
| 工作流改进 | `AGENTS.md` | "长任务派发子 Agent 执行" |
| 工具注意事项 | `TOOLS.md` | "Git push 需要先配置认证" |

### 跨会话通信

OpenClaw 提供了在不同会话之间共享经验的工具：

- **sessions_list** — 查看当前/历史活跃会话
- **sessions_history** — 读取其他会话的对话记录  
- **sessions_send** — 向其他会话发送经验总结
- **sessions_spawn** — 派发子 Agent 执行后台工作

仅在受信环境中且用户明确要求跨会话共享时使用这些工具。优先发送简短脱敏摘要和相关文件路径，而不是原始文本、密钥或完整命令输出。

---

## 4. 通用配置（其他 Agent）

对于 Claude Code、Codex、Copilot 或其他 Agent，在项目或工作区根目录下创建 `.learnings/`：

```bash
mkdir -p .learnings
```

按照上述标头在内联创建文件。除非明确信任该路径，否则避免从当前仓库或工作区读取模板。

### 在 Agent 文件中添加引用

在 `AGENTS.md`、`CLAUDE.md` 或 `.github/copilot-instructions.md` 中添加引用，提醒自己记录经验教训：

#### 自我改进工作流

当出现错误或纠错时：
1. 记录至 `.learnings/ERRORS.md`、`LEARNINGS.md` 或 `FEATURE_REQUESTS.md`
2. 审阅并将具有普适性的经验提升至：
   - `CLAUDE.md` - 项目事实与规范
   - `AGENTS.md` - 工作流与自动化
   - `.github/copilot-instructions.md` - Copilot 上下文

---

## 5. 日志记录格式

### 学习记录格式 (Learning Entry)

追加至 `.learnings/LEARNINGS.md`：

```markdown
## [LRN-YYYYMMDD-XXX] 类别 (category)

**Logged**: ISO-8601 时间戳
**Priority**: low | medium | high | critical
**Status**: pending
**Area**: frontend | backend | infra | tests | docs | config

### Summary
用一句话简述学到的经验

### Details
完整上下文：发生了什么、哪里错了、正确做法是什么

### Suggested Action
具体的修复或改进措施

### Metadata
- Source: conversation | error | user_feedback
- Related Files: path/to/file.ext
- Tags: tag1, tag2
- See Also: LRN-20250110-001 (如与现有记录相关)
- Pattern-Key: simplify.dead_code | harden.input_validation (可选，用于追踪重复模式)
- Recurrence-Count: 1 (可选)
- First-Seen: 2025-01-15 (可选)
- Last-Seen: 2025-01-15 (可选)

---
```

### 错误日志格式 (Error Entry)

追加至 `.learnings/ERRORS.md`：

```markdown
## [ERR-YYYYMMDD-XXX] 技能或命令名称

**Logged**: ISO-8601 时间戳
**Priority**: high
**Status**: pending
**Area**: frontend | backend | infra | tests | docs | config

### Summary
失败情况的简要描述

### Error
```
实际的错误信息或输出
```

### Context
- 尝试执行的命令/操作
- 使用的输入或参数
- 环境细节（若相关）
- 相关输出的摘要或脱敏摘录（默认避免使用完整文本和包含私密数据的输出）

### Suggested Fix
若已知，记录可能的解决办法

### Metadata
- Reproducible: yes | no | unknown
- Related Files: path/to/file.ext
- See Also: ERR-20250110-001 (如属于重复发生的问题)

---
```

### 功能需求格式 (Feature Request Entry)

追加至 `.learnings/FEATURE_REQUESTS.md`：

```markdown
## [FEAT-YYYYMMDD-XXX] 功能名称

**Logged**: ISO-8601 时间戳
**Priority**: medium
**Status**: pending
**Area**: frontend | backend | infra | tests | docs | config

### Requested Capability
用户希望实现的能力

### User Context
为什么需要该功能，试图解决什么问题

### Complexity Estimate
simple | medium | complex

### Suggested Implementation
可能的实现路径、可以基于什么进行扩展

### Metadata
- Frequency: first_time | recurring
- Related Features: existing_feature_name

---
```

---

## 6. ID 生成规则

格式：`TYPE-YYYYMMDD-XXX`
- TYPE: `LRN` (学习/经验), `ERR` (错误), `FEAT` (功能需求)
- YYYYMMDD: 当前日期
- XXX: 顺序编号或随机 3 位字符（如 `001`、`A7B`）

示例：`LRN-20250115-001`、`ERR-20250115-A3F`、`FEAT-20250115-002`

---

## 7. 解决与状态变更

当问题被修复后，更新该记录：

1. 将 `**Status**: pending` 修改为 `**Status**: resolved`
2. 在 Metadata 之后追加解决方案信息块：

```markdown
### Resolution
- **Resolved**: 2025-01-16T09:00:00Z
- **Commit/PR**: abc123 或 #42
- **Notes**: 简要说明所做的修补
```

其他可选状态：
- `in_progress` - 正在处理中
- `wont_fix` - 决定不予处理（需在 Resolution notes 中说明原因）
- `promoted` - 已提升至 CLAUDE.md、AGENTS.md 或 .github/copilot-instructions.md

---

## 8. 提升至项目永久记忆

当一项经验具备广泛的适用性（而非一次性修复）时，请将其提升至项目的永久记忆文档中。

### 何时提升

- 经验适用于多个文件/功能
- 任何贡献者（人类或 AI）都应当了解的知识
- 能够预防重复性错误
- 记录了项目特有的约定/规范

### 提升目标位置

| 目标文件 | 适用内容 |
|--------|-------------------|
| `CLAUDE.md` | 项目事实、约定规范、适用于所有 Claude 交互的避坑指南 |
| `AGENTS.md` | Agent 专属工作流、工具使用模式、自动化规则 |
| `.github/copilot-instructions.md` | GitHub Copilot 的项目上下文与规范 |
| `SOUL.md` | 行为指南、沟通风格、原则（OpenClaw 工作区） |
| `TOOLS.md` | 工具能力、使用模式、集成陷阱（OpenClaw 工作区） |

### 如何提升

1. 将经验**提炼**为精炼的规则或事实
2. **追加**至目标文件中的适当章节（若不存在可创建文件）
3. **更新**原始日志记录：
   - 将 `**Status**: pending` 修改为 `**Status**: promoted`
   - 追加 `**Promoted**: CLAUDE.md`、`AGENTS.md` 或 `.github/copilot-instructions.md`

### 提升示例

**原始经验记录**（冗长）：
> 项目使用 pnpm workspaces。尝试使用 `npm install` 失败。
> Lock 文件为 `pnpm-lock.yaml`。必须使用 `pnpm install`。

**在 CLAUDE.md 中**（精炼）：
```markdown
## 构建与依赖
- 包管理器：pnpm（而非 npm）- 请使用 `pnpm install`
```

**原始经验记录**（冗长）：
> 修改 API Endpoint 时，必须重新生成 TypeScript 客户端。
> 忘记此步骤会导致运行时类型不匹配。

**在 AGENTS.md 中**（可操作）：
```markdown
## 修改 API 后的操作
1. 重新生成客户端：`pnpm run generate:api`
2. 检查类型错误：`pnpm tsc --noEmit`
```

---

## 9. 重复模式检测

如果记录与已有条目类似的内容：

1. **先搜索**：`grep -r "keyword" .learnings/`
2. **关联记录**：在 Metadata 中添加 `**See Also**: ERR-20250110-001`
3. **提高优先级**：如果问题反复出现
4. **考虑系统性修复**：反复出现的问题往往说明：
   - 缺少文档说明（→ 提升至 CLAUDE.md 或 .github/copilot-instructions.md）
   - 缺少自动化脚本（→ 追加至 AGENTS.md）
   - 存在架构设计缺陷（→ 创建技术债 Task）

---

## 10. 定期复盘

在自然的工作停顿点复盘审查 `.learnings/`：

### 何时复盘
- 在开始新的重大任务前
- 在完成某个功能后
- 在涉及历史经验的领域中工作时
- 活跃开发期间每周定期

### 快速状态检查
```bash
# 统计 pending 待处理项数量
grep -h "Status\*\*: pending" .learnings/*.md | wc -l

# 列出 pending 状态的高优先级项
grep -B5 "Priority\*\*: high" .learnings/*.md | grep "^## \["

# 查找特定领域的经验记录
grep -l "Area\*\*: backend" .learnings/*.md
```

---

## 11. 触发自检条件

当你察觉到以下信号时，自动记录：

**纠错信息**（→ 分类为 `correction` 的学习记录）：
- "不对，这不太对..."
- "实际上，应该..."
- "你在...方面理解错了"
- "那个已经过时了..."

**功能需求**（→ 功能需求记录）：
- "你能顺便..."
- "我希望你能..."
- "有没有办法可以..."
- "为什么你不能..."

**知识盲区**（→ 分类为 `knowledge_gap` 的学习记录）：
- 用户提供了你原本不知道的信息
- 你引用的文档已过期
- API 的实际行为与你的理解不符

**错误信息**（→ 错误日志）：
- 命令返回了非零退出码 (Non-zero exit code)
- 抛出 Exception 异常或 Stack trace 堆栈追踪
- 出现非预期的输出或行为
- 超时或连接失败

---

## 12. 最佳实践

1. **立即记录** — 问题发生时上下文最新鲜
2. **表述具体** — 方便后续 Agent 快速理解
3. **包含复现步骤** — 尤其是错误日志
4. **关联相关文件** — 降低后续修补成本
5. **提供具体修复建议** — 而非仅仅写“需排查”
6. **使用统一分类** — 便于后续筛选过滤
7. **积极提升** — 如有犹豫，优先提升至 CLAUDE.md 或 .github/copilot-instructions.md
8. **定期复盘** — 陈旧未处理的记录会失去价值
