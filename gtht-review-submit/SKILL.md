---
name: gtht-review-submit
description: >-
  国泰海通科技平台（fintech.gtht.com.cn）需求评审纪要自动提取与提交落地技能。
  自动定位并解析 `ba-to-dev` 生成的需求分析 Markdown 文档，提取【评审纪要】正文小节、需求编号、预计上线版本与评审结论，
  在科技平台进行极速 API 直连提交（≤1s，幂等安全，以当前登录人身份新增记录）。
  触发词：提交评审纪要、提交需求评审、评审落地、落地评审纪要、提交评审、完成评审、gtht-review-submit。
---

# 国泰海通需求评审纪要提交技能 (gtht-review-submit)

自动从 `ba-to-dev` 产出的需求 Markdown 文档中提取【评审纪要】正文内容，在国泰海通科技平台（fintech.gtht.com.cn）中一键提交评审落盘。

> ⚡ **性能与安全**：
> - **API 直连（默认）**：打 `POST conclusion/saveDemandReviewInfo` 接口提交，**≤1s 极速落盘**；
> - **安全幂等**：以当前登录人身份新增/更新记录，**绝不覆盖或篡改他人创建的评审记录**；
> - **UI 兜底**：指定 `--browser` 时可走 Playwright 条件等待表单渲染提交。

---

## 📌 架构与脚本依赖

- **底层脚本位置**：
  ```bash
  SCRIPT="~/.workbuddy/skills/gtht-review-submit/scripts/submit_review.py"
  ```
- **配置与会话**：
  复用 `gtht-skills` 的凭据 (`~/.config/gtht/config.json`) 与会话 (`~/.local/share/gtht/session.json`)。

---

## 🚀 两种主要使用模式

### 模式一：`ba-to-dev` 需求文档自动化联动（最常用推荐）

当用户完成 `ba-to-dev` 需求分析并生成 Markdown 文档后，或用户说「提交评审纪要」、「提交需求评审」时：

1. **自动定位需求文档**：优先读取当前对话或 `/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析/` 目录下最新修改的需求 Markdown 文档。
2. **提取要素与正文**：
   * **`req_id`**：读取 Front Matter `req_id: R26xxxxxxx` 或 Markdown 标题/链接中的需求编号；
   * **评审纪要正文 (`--minutes`)**：自动截取 **`#### 评审纪要`** （或 `## 评审纪要`）小节下的**全量正文内容**（包含沟通时间与人员、1~9 评审纪要条目）；
   * **上线版本 (`--version`)**：提取 `预计上线日期：YYYY年MM月上线`（推断该月第三个周五为发布日，如 `20260918`）；
   * **需求类型 (`--type`)**：标题或内容含“缺陷”填 `缺陷`，否则填 `普通业务功能`；
   * **评审结论 (`--result`)**：从纪要首行文本提取，默认填 `通过`。
3. **极速 API 提交落盘**：
   ```bash
   python3 "$SCRIPT" <req_id> \
       --type <普通业务功能|缺陷> \
       --version <YYYYMMDD> \
       --result <通过|有条件通过|驳回> \
       --minutes "<评审纪要正文>"
   ```

---

### 模式二：命令行 / 对话直接提交

用户显式指定需求编号与评审纪要正文：

```bash
# 示例：为 R2608070008 提交评审通过纪要
python3 "$SCRIPT" R2608070008 \
    --type 缺陷 \
    --version 20260918 \
    --result 通过 \
    --minutes "2026年08月10日经与**技术研发部** 郑立朋和单大卫沟通评审通过。...\n1. 需求补充说明：无..."
```

#### 参数说明表

| 参数 | 必填 | 格式与说明 | 默认值 |
|---|---|---|---|
| `<req_id>` | **是** | 需求编号，如 `R2608100032` | - |
| `--minutes` | **是** | 评审纪要正文（`ba-to-dev` MD 中的评审纪要正文段落） | - |
| `--version` | 否 | 目标版本排期 `YYYYMMDD`，如 `20260918` | 今日或排期推断 |
| `--type` | 否 | 一级需求类型：`普通业务功能` \| `缺陷` | `普通业务功能` |
| `--result` | 否 | 评审结论：`通过` \| `有条件通过` \| `驳回` | `通过` |
| `--dry-run` | 否 | 仅打印 payload 预览，不实际提交落库 | `False` |
| `--browser` | 否 | 强制走 Playwright 界面自动化进行填报 | `False` |

---

## 💬 对话交互示例

| 用户口令 | 技能处理动作 |
|---|---|
| 「**帮我把刚才 `ba-to-dev` 的评审纪要提交到科技平台**」 | 自动找到最新需求 MD，抽取 `req_id`、版本号与 `#### 评审纪要` 下全量正文，运行 `submit_review.py` 秒级提交 |
| 「**落地评审纪要 R2608100032**」 | 提取该需求 MD 中的评审纪要正文并一键落盘 |
