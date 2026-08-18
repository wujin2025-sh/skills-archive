---
name: proposed-schedule-confirm
description: "拟排期确认与发邮件工具。传入排期版本号（如 20260821 或 2026-08-21），提取需求受理人为“吴进”（或指定受理人）的需求及 Story 明细，按【重点关注】优先排序（重点关注在最上方），对不含“生产”的 SIT 未完成状态（如「SIT测试待排期」、「待SIT测试」、「待SIT大远期自测」、「SIT大远期自测中」等）突出高亮标识 (🚨)，含“生产”的状态（如「SIT生产测试待排期」）判定为无风险，生成包含 13 大核心字段的高颜值 HTML 确认表（含「影响灰度」与「开发负责人」列）。当用户提到“发邮件”或带 --send-mail / --send 参数时，默认自动包含固定人员（肖慧、刘青、乔露露、常丽）及抽取的相关负责人，后台无头模式自动起草邮件并存入 Coremail 草稿箱供人工确认后发送。"
allowed-tools:
  - Bash
  - Read
  - Write
---

# 拟排期确认工具 (proposed-schedule-confirm)

> [!NOTE]
> **技能定位**：本 Skill 用于针对指定排期版本（如 `20260821`），一键提取受理人为 **“吴进”**（或指定受理人）的需求及关联 Story 拟排期数据，生成符合 `demand-detail-schedule` 高颜值风格的 HTML 确认表。当触发“发邮件”指令时，**后台无头模式自动提取确认表中所有相关人员（固定包含肖慧、刘青、乔露露、常丽）并起草邮件存入 Coremail 邮件草稿箱**，提供高颜值 HTML 正文、底部 @ 负责人列表及下班前风险反馈提醒。

---

## 🎯 触发词

当用户提到 “拟排期确认”、“拟排期确认表”、“排期确认 20260821”、“吴进 20260821 排期确认”、“拟排期风险”、“发邮件”、“发送邮件”、“存草稿”、“给测试同事发邮件”、“proposed-schedule-confirm” 时触发。

---

## 📋 13 大核心输出字段

| 列序号 | 字段名称 | 说明/来源 |
| :---: | :--- | :--- |
| **Col 1** | **史诗编号** | 对应大宽表 `epicCode` 或 `epicConcat`（同分组自动合并 rowspan） |
| **Col 2** | **需求编号** | 对应大宽表 `demandId`（同分组自动合并 rowspan） |
| **Col 3** | **Story编号** | 对应大宽表 `storyCode` |
| **Col 4** | **任务名称** | 对应 Story 标题 `storyTitle` |
| **Col 5** | **涉及系统** | 对应系统名 `storySystemName` |
| **Col 6** | **当前状态** | 对应 Story 当前状态（不含“生产”的 SIT 未完成状态突出显示 `🚨` 红色警示徽章） |
| **Col 7** | **开发负责人** | 开发负责人 `devManagePerson`（位于 SIT 负责人左侧，纯姓名标准格式） |
| **Col 8** | **SIT负责人** | SIT测试负责人 `sitTestManagePerson`（已格式化纯姓名） |
| **Col 9** | **UAT负责人** | UAT测试负责人 `uatTestManagePerson`（已格式化纯姓名） |
| **Col 10** | **业务验收人** | 对应大宽表 `businessAcceptor` / `storyBusName`（已格式化纯姓名） |
| **Col 11** | **重点关注** | 是否重点关注 `keyFocus`（高亮显示 `🔥 是`） |
| **Col 12** | **影响灰度** | 需求是否影响灰度升级 `isEffectGrayUpgrade`（高亮显示 `⚡ 是`） |
| **Col 13** | **备注** | 对应大宽表 `beizhuText` 备注文字内容（优先抓取科技平台最新融合备注） |

---

## 📧 自动提取邮件人员与草稿箱机制

1. **自动提取与固定人员补全**：
   - 自动扫描确认表中所有过滤出的 Story，提取 `开发负责人`、`SIT负责人`、`UAT负责人`、`业务验收人` 等角色。
   - 固定补充 11 位核心人员：**肖慧 (`xiaohui@gtht.com`)、刘青 (`liuqing5@gtht.com`)、乔露露 (`qiaolulu@gtht.com`)、常丽 (`changli@gtht.com`)、张帆 (`zhangfan4@gtht.com`)、茆莹莹 (`maoyingying@gtht.com`)、张志鹏 (`zhangzhipeng@gtht.com`)、薛天明 (`xuetianming@gtht.com`)、马晓鑫 (`maxiaoxin@gtht.com`)、李鹤晨 (`lihechen@gtht.com`)、周尤珠 (`zhouyouzhu@gtht.com`)**。
   - 正确矫正常用人员邮箱（如 **王岗** -> `wanggang@gtht.com`，**龚子慧** -> `gongzihui@gtht.com`）。
   - 过滤无意义字符（如 `--`、`无需业务验收`、`None` 等），并通过 `Escape` 键消隐 Coremail 联想弹窗，确保 100% 收件人 Tag 准确建立。

2. **后台无头模式 (Headless Mode) 存草稿箱与附件自动添加**：
   - 触发 `发邮件` 或 `--send-mail` 时，Playwright 在后台无头模式（`headless=True`）静默执行。
   - 自动清理失效 session cookie 彻底消除 `会话已过期` 弹窗。
   - 使用 Coremail 官方 KindEditor API (`window.KindEditor.instances[0].html(js_content)`) 将全量 HTML 确认表（含 5 大统计卡片、13 列表格、底部 @ 负责人列表及风险反馈 Prompt）完整注入正文。
   - **自动将生成的 HTML 确认表（如 `拟排期需求确认表20260821-吴进.html`）作为邮件附件上传添加**。
   - **默认存入 Coremail 邮件草稿箱**，顶部弹出 `保存草稿成功`，方便用户登录邮箱复核后手动点击发送（带 `--force-send` 才强行直接发送）。

3. **初版确认表与沟通后清单 (-r) 收件人一致性保障机制**：
   - 生成初版 `拟排期需求确认表` 时，系统自动将当前版本的全部相关人员名单持久化缓存。
   - 生成或起草 `拟排期需求明细清单` (`-r` 模式) 时，系统**自动继承并合并 (Union) 初版确认表的全部收件人**。
   - 即使部分需求在沟通反馈后被调出至后续排期版本，**被调出需求的开发、SIT、UAT、业务验收人依然会自动保留在收件人列表中**，完美匹配“*对于调出的需求也请测试老师尽快安排测试，以期在下个版本可以上线*”的触达要求。

---

## 💬 邮件正文底部 @ 提醒与下班前风险反馈提示

> [!IMPORTANT]
> **注意**：排期提醒 Block **不体现在生成的 HTML 文件中**，仅在起草或发送邮件时，自动在邮件正文 HTML 内容后单独换行追加。

邮件正文底部包含标准风险反馈 Block（**动态只提取各 Story 当前未完成状态对应的责任人；已结束/已完成/已上线状态自动过滤不 @ 负责人**）：

- SIT 未完成状态（如 `SIT测试待排期`、`待SIT测试`） -> `@ SIT负责人`
- UAT 未完成状态（如 `待UAT测试`） -> `@ UAT负责人`
- 业务验收未完成状态（如 `待业务验收`） -> `@ 业务验收人`
- 开发/设计未完成状态（如 `待开发`、`开发中`） -> `@ 开发负责人`
- **已结束/已完成/已上线/已终止状态** -> **直接跳过，不 @ 负责人**

```html
<div style="margin: 20px 32px 32px 32px; padding: 20px 24px; background-color: #fffbe6; border: 1px solid #ffe58f; border-radius: 10px; font-size: 13px; line-height: 1.8;">
  <div style="font-weight: 700; font-size: 14px; color: #d48806; margin-bottom: 8px;">
    <span>📢 当前状态对应负责人：</span>
  </div>
  <div style="font-weight: 600; color: #1d4ed8; margin-bottom: 12px; word-break: break-all;">
    @倪梦思 @刘慧雨 @刘青 @吕正仪 @孙驰 @曾娟 @李卓远 @李萍萍 @杜伟毅 @王岗 @王恒 @罗海洪 @聂章艳 @解娅宁 @高健 @齐伟华
  </div>
  <div style="color: #1f2937; font-size: 14px; font-weight: 600; background-color: #ffffff; padding: 12px 16px; border-radius: 6px; border-left: 4px solid #f59e0b; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
    💬 麻烦各位老师在今天下班前帮忙确认一下相关需求是否可以顺利排入当前版本。<br>如评估后存在无法排入或延期风险，烦请及时告知，以便我们提前协调并安排调整至后续版本。辛苦大家！
    <!-- 沟通后上线清单模式 (-r) 提示文案: 💬 以上清单为经过与业务、测试老师沟通反馈后的拟计划<版本号如0821>版本需求明细，请各位老师知悉。对于调出的需求也请测试老师尽快安排测试，以期在下个版本可以上线。如对排期有任何疑问或变动，烦请及时告知，辛苦大家！ -->
  </div>
</div>
```

---

## 💻 智能体命令行调用说明 (CLI Guide)

```bash
# 1. 生成确认表并自动起草存入 Coremail 邮件草稿箱（默认行为，后台无头模式）
python3 /Users/wujin/.workbuddy/skills/proposed-schedule-confirm/scripts/proposed_schedule_confirm.py 20260821 --send-mail

# 2. 沟通后拟计划上线清单模式（传入 -r 参数）
python3 /Users/wujin/.workbuddy/skills/proposed-schedule-confirm/scripts/proposed_schedule_confirm.py 20260821 -r

# 3. 沟通后拟计划上线清单模式并起草邮件存草稿箱
python3 /Users/wujin/.workbuddy/skills/proposed-schedule-confirm/scripts/proposed_schedule_confirm.py 20260821 -r --send-mail

# 4. 强行直接发送邮件（跳过草稿箱人工确认）
python3 /Users/wujin/.workbuddy/skills/proposed-schedule-confirm/scripts/proposed_schedule_confirm.py 20260821 --send-mail --force-send
```

---

## 📂 产物保存规范

> [!IMPORTANT]
> - 生成的 HTML 文件强保存在调用者的当前工作目录 (`os.getcwd()`) 下。
> - 默认文件命名：
>   - 普通确认表模式：`拟排期需求确认表<版本号>-<受理人>.html` (例: `拟排期需求确认表20260821-吴进.html`)
>   - 沟通后上线清单模式 (`-r`)：`拟排期需求明细清单<版本号>-<受理人>.html` (例: `拟排期需求明细清单20260821-吴进.html`)
> - 默认只生成 HTML 确认表（`.md` Markdown 文件无需默认生成，仅在显式指定 `--output_md` 或 `--table-only` 时生成）。
