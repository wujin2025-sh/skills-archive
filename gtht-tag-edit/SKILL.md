---
name: gtht-tag-edit
description: 国泰海通科技平台（fintech.gtht.com.cn）需求自定义标签设置与修改技能（kjptai MCP 版）。 通过 kjptai MCP 的 `add_requirement_tag`
  工具为需求（`R26xxxxxxx`）设置自定义标签， 支持逗号分隔多标签、追加去重， 并支持自动解析 `ba-to-dev` 需求 Markdown 中的
  `tags` 列表同步落盘。 触发词：修改需求标签、设置需求标签、需求标签、添加需求标签、需求自定义标签、修改标签、标签修改、史诗标签修改、gtht-tag-edit。
disable: false
---


# 国泰海通需求自定义标签修改技能 (gtht-tag-edit)

自动按对话指令或 `ba-to-dev` 产出的需求 Markdown 文档中的 `tags` 字段，在国泰海通科技平台（fintech.gtht.com.cn）中设置需求的自定义标签。

> ⚡ **特性与性能（2026-09-10 重构为 kjptai MCP 版）**：
> - **访问方式（纯 MCP）**：通过 kjptai MCP 的 `add_requirement_tag` 工具设置标签，服务端鉴权，无需本机登录态、无需浏览器、无需网页抓取；
> - **极速**：REST/MCP 直连秒级完成，无需 Playwright；
> - **两段式确认**：写操作先 prepare 展示摘要，用户确认后携带令牌提交（与 `gtht-accept-review` 同机制）；
> - **多标签追加去重**：`content` 支持逗号分隔多个标签，追加模式自动去重（已有标签不重复）。

---

## 📌 架构与依赖

- **访问方式（唯一推荐）**：kjptai MCP 的 `add_requirement_tag` 工具（工具名前缀 `mcp__kjptai__`）。
- **前提条件**：`kjptai` 连接器已信任启用（端点 `https://fintech.gtht.com.cn/kjptai/api/mcp`，X-Platform-Id `kjpt_prod_...`）。
- **两段式确认令牌提取**：复用 `gtht-accept-review` 的 `scripts/kjptai_prepare.py`（HTTP 直连 kjptai MCP 一步完成 prepare + 摘要 + 令牌提取）。
  ```bash
  KJPTAI_PREPARE="/Users/wujin/.workbuddy/skills/gtht-accept-review/scripts/kjptai_prepare.py"
  PY="/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python"
  ```

### `add_requirement_tag` 工具参数

| 参数 | 必填 | 说明 |
|---|---|---|
| `demandId` | **是** | R 开头完整需求编号，如 `R2609090040` |
| `content` | **是** | 自定义标签，多个用**逗号分隔**，如 `CX-信用-两融,CX-业务`；追加去重 |

---

## 🚀 执行流程（单笔需求，两段式确认）

### Step 1：Prepare（脚本一步取摘要+令牌）

```bash
$PY "$KJPTAI_PREPARE" --tool add_requirement_tag \
  --args '{"demandId":"R2609090040","content":"CX-信用-两融,CX-业务"}'
```

脚本打印确认摘要（需求编号、操作、标签、变更前/后标签数）并写入 `/tmp/kjptai_confirm_params.json`（含 `confirmationToken` / `sessionId` / `requestId` / `args`）。

向用户展示摘要，**等待用户在对话中明确确认**。

### Step 2：携带令牌提交（落库）

读取 `/tmp/kjptai_confirm_params.json`，在对话内调用 `mcp__kjptai__add_requirement_tag`，携带：
- `demandId` + `content`（原样业务字段）
- `confirmationToken` + `requestId` + `confirmed=true`
- `_meta.sessionId`（文件中的 sessionId）

> ⚠️ **注意**：`add_requirement_tag` 的 prepare 返回中 `expectedUpdateTime` 为空，提交时**不需要**该字段（与 `accept_requirement`/`review_requirement` 不同）。
> ⚠️ **幂等/令牌时效**：同一次编辑重试必须复用原 `confirmationToken` 与 `requestId`；任何成功写库都会使需求 `updateTime` 前移，旧令牌失效，需重新 prepare。

---

## 🚀 三种主要使用模式

### 模式一：`ba-to-dev` 需求文档自动化联动（推荐）

当用户完成 `ba-to-dev` 需求分析并生成 Markdown 文档后，或用户说「修改需求标签」「同步标签」时：

1. **自动定位需求文档**：优先读取当前对话或 `/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析/` 目录下最新修改的需求 Markdown 文档。
2. **提取要素**：
   * **`req_id`**：读取 Front Matter `req_id: R26xxxxxxx` 或标题中的需求编号；
   * **`tags`**：读取 Front Matter 中的 `tags: [标签1, 标签2]` 列表，拼接为逗号分隔的 `content`（如 `CX-信用-两融,CX-业务`）。
3. **业务领域标签自动推断规则**（若 `tags` 为空或需补充）：
   * **两融业务**：若需求涉及「融资融券」「两融」「信用交易」「信用两融」，自动追加 **`CX-信用-两融`**；
   * **股票质押**：若需求涉及「股票质押」「股质」「质押」，自动追加 **`CX-信用-质押`**；
   * **股权激励**：若需求涉及「股权激励」「行权」，自动追加 **`CX-股权激励`**；
   * **期权业务**：若需求涉及「期权」，自动追加 **`CX-期权`**；
   * **道合大宗**：若需求涉及「道合」「大宗」，自动追加 **`CX-道合大宗`**。
4. **极速更新**：按「执行流程」走 `add_requirement_tag` 两段式提交。

### 模式二：单笔需求对话修改

用户显式提供需求编号和自定义标签列表：

```bash
# 示例：为 R2608100032 设置自定义标签 CX-使能B,CX-业务
$PY "$KJPTAI_PREPARE" --tool add_requirement_tag \
  --args '{"demandId":"R2608100032","content":"CX-使能B,CX-业务"}'
```

### 模式三：按史诗编号批量修改下属需求标签

`add_requirement_tag` 仅支持**单笔需求**。史诗（`E`/`PG` 开头）批量时：

1. **先获取史诗下属需求列表**：通过 `query_requirement` / 大宽表热缓存 / 平台史诗详情获取该史诗关联的所有需求编号；
2. **逐个调用** `add_requirement_tag`（每个需求独立 prepare + 提交，两段式确认）；
3. 汇总输出每个需求的设置结果。

---

## 💬 对话交互示例

| 用户口令 | 技能处理动作 |
|---|---|
| 「**帮我把刚才需求的标签改成 CX-使能B,CX-业务**」 | 自动找到最新需求 MD 提取 `req_id`，走 `add_requirement_tag` 两段式提交 |
| 「**修改需求标签 R2608100032 CX-道合大宗,CX-股期**」 | 单笔需求标签更新（prepare → 确认 → 提交） |
| 「**按史诗 PG202204-0261 批量修改标签 CX-道合大宗,CX-股期**」 | 先取史诗下属需求列表，逐个 `add_requirement_tag` |

---

## 🚨 注意事项

- 端点必须为 `kjptai/api/mcp`（需求平台）；指向 `devopsai/api/mcp` 时只有 5 个流水线工具，`add_requirement_tag` 不可用；
- 改 `mcp.json` 后需**重启/新建会话**并重新信任 kjptai 连接器；
- **两段式确认是硬约束**：写操作先 prepare 展示摘要，默认需用户在对话中明确确认后携带令牌提交，禁止擅自落库；
- `add_requirement_tag` 的 `content` 为**追加去重**模式（追加到现有标签，已有标签不重复），如需覆盖完整标签集，传入完整目标列表即可；
- 若 kjptai MCP 工具不可用，提示检查 kjptai 连接器信任状态，不尝试用网页绕过。