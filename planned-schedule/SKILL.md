---
name: planned-schedule
description: 拟排期确认与发邮件工具。传入排期版本号（如 20260821 或 2026-08-21），提取需求受理人为“吴进”（或指定受理人）的需求及
  Story 明细，按【史诗编号】分组排序（同一史诗 Story 连续排列，史诗与需求编号单元格自动 rowspan 合并；组内重点关注优先），对不含“生产”的 SIT 未完成状态（如「SIT测试待排期」、「待SIT测试」、「待SIT大远期自测」、「SIT大远期自测中」等）突出高亮标识
  (🚨)，含“生产”的状态（如「SIT生产测试待排期」）判定为无风险，生成包含 14 大核心字段的高颜值 HTML 计划表（含「影响灰度」「原始提出人」与「开发负责人」列，需求编号与 Story
  编号均支持点击跳转平台详情页）。当用户提到“发邮件”或带
  --send-mail / --send 参数时，默认自动包含固定人员（肖慧、刘青、乔露露、常丽）及抽取的相关负责人，后台无头模式自动起草邮件并存入 Coremail
  草稿箱供人工确认后发送。
disable: false
---


# 拟排期确认工具 (planned-schedule)

> [!NOTE]
> **技能定位**：本 Skill 用于针对指定排期版本（如 `20260821`），一键提取受理人为 **“吴进”**（或指定受理人）的需求及关联 Story 拟排期数据，生成符合 `demand-detail-schedule` 高颜值风格的 HTML 计划表。支持 `--upload` 自动上传到腾讯文档「版本计划排期」文件夹（**同名覆盖 / 不同名新增**）。当触发“发邮件”指令时，**后台无头模式自动提取计划表中所有相关人员（固定包含肖慧、刘青、乔露露、常丽）并起草邮件存入 Coremail 邮件草稿箱**，提供高颜值 HTML 正文、底部 @ 负责人列表及下班前风险反馈提醒。

---

## 🎯 触发词

当用户提到 “拟排期确认”、“拟排期确认表”、“排期确认 20260821”、“吴进 20260821 排期确认”、“拟排期风险”、“发邮件”、“发送邮件”、“存草稿”、“给测试同事发邮件”、“上传腾讯文档”、“上传到腾讯文档”、“发布到腾讯文档”、“planned-schedule” 时触发。

---

## 📋 14 大核心输出字段

| 列序号 | 字段名称 | 说明/来源 |
| :---: | :--- | :--- |
| **Col 1** | **史诗编号** | 对应大宽表 `epicCode` 或 `epicConcat`（同分组自动合并 rowspan） |
| **Col 2** | **需求编号** | 对应大宽表 `demandId`（同分组自动合并 rowspan） |
| **Col 3** | **Story编号** | 对应大宽表 `storyCode`，**支持点击跳转 Story 详情页**（链接 `storyNo` 参数取 `dataUniqueNo`/`storyNo`，如 R2604160112-1，非 S 编号） |
| **Col 4** | **任务名称** | 对应 Story 标题 `storyTitle` |
| **Col 5** | **涉及系统** | 对应系统名 `storySystemName` |
| **Col 6** | **当前状态** | 对应 Story 当前状态（不含“生产”的 SIT 未完成状态突出显示 `🚨` 红色警示徽章） |
| **Col 7** | **开发负责人** | 开发负责人 `devManagePerson`（位于 SIT 负责人左侧，纯姓名标准格式） |
| **Col 8** | **SIT负责人** | SIT测试负责人 `sitTestManagePerson`（已格式化纯姓名） |
| **Col 9** | **UAT负责人** | UAT测试负责人 `uatTestManagePerson`（已格式化纯姓名） |
| **Col 10** | **业务验收人** | 对应大宽表 `businessAcceptor` / `storyBusName`（已格式化纯姓名） |
| **Col 11** | **原始提出人** | 需求原始提出人 `orgUserName`（位于业务验收人右侧）。此字段**不在大宽表缓存**中，由主脚本按需求编号调用科技平台需求详情接口 `/api/demand-service/demandsub/queryDemandsubInfo` 补充，本地缓存 `.org_user_cache.json` 加速；平台该需求无原始提出人时显示 `--`。例如 R2604160080 → 刘志林 |
| **Col 12** | **重点关注** | 是否重点关注 `keyFocus`（高亮显示 `🔥 是`） |
| **Col 13** | **影响灰度** | 需求是否影响灰度升级 `isEffectGrayUpgrade`（高亮显示 `⚡ 是`） |
| **Col 14** | **备注** | 对应大宽表 `beizhuText` 备注文字内容（优先抓取科技平台最新融合备注） |

---

## 📧 自动提取邮件人员与草稿箱机制

1. **自动提取与固定人员补全**：
   - 自动扫描计划表中所有过滤出的 Story，提取 `开发负责人`、`SIT负责人`、`UAT负责人`、`业务验收人` 等角色。
   - 固定补充 15 位核心人员（2026-10-20 用户指示新增 陈曦、姬攀毅、罗洁、黄增增）：**肖慧 (`xiaohui@gtht.com`)、刘青 (`liuqing5@gtht.com`)、乔露露 (`qiaolulu@gtht.com`)、常丽 (`changli@gtht.com`)、张帆 (`zhangfan4@gtht.com`)、茆莹莹 (`maoyingying@gtht.com`)、张志鹏 (`zhangzhipeng@gtht.com`)、薛天明 (`xuetianming@gtht.com`)、马晓鑫 (`maxiaoxin@gtht.com`)、李鹤晨 (`lihechen@gtht.com`)、周尤珠 (`zhouyouzhu@gtht.com`)、陈曦 (`chenxi10@gtht.com`)、姬攀毅 (`jipanyi@gtht.com`)、罗洁 (`luojie@gtht.com`)、黄增增 (`huangzengzeng@gtht.com`)**。
   - 正确矫正常用人员邮箱（如 **王岗** -> `wanggang@gtht.com`，**龚子慧** -> `gongzihui@gtht.com`）。
   - 过滤无意义字符（如 `--`、`无需业务验收`、`None` 等），并通过 `Escape` 键消隐 Coremail 联想弹窗，确保 100% 收件人 Tag 准确建立。

2. **收件人邮箱定位规则（部门+人员 定位邮箱，2026-10-20 优化）**：
   - 邮箱定位**严格按「部门 + 人员」判断**，数据源优先级：
     1. `KNOWN_EMAIL_MAP` 精确映射（人工维护，最高优先）；
     2. 《人员部门对应关系表.csv》（`/Volumes/Macintosh HD_Data/WorkBuddy/会议纪要/人员部门对应关系表.csv`）中**带邮箱的记录**（如 孙鹰=`sunying5@gtht.com`、陈超[技术研发部]=`chenchao8@gtht.com`）；
     3. 拼音兜底（`姓名拼音@gtht.com`，仅用于表中无该姓名或无邮箱记录时，并在控制台输出 `[PYINYIN_FALLBACK]` 提示人工核对）。
   - **同一部门姓名重复时才需从 CSV 区分邮箱**：脚本启动时自动加载人员部门表构建 `姓名 → [(部门, 邮箱), ...]` 映射；同名跨部门人员（如「陈超」同时存在于系统运行部与技术研发部），自动采用带邮箱部门的记录，并在收件人明细中打印全部部门归属供人工核对；人员表**已收录但无邮箱**者同样输出部门归属提示，便于按部门补全正确邮箱。
   - 运行时控制台逐条打印：`📧 姓名（部门）→ 邮箱 [来源]`，方便核对收件人是否精准。

2. **后台无头模式 (Headless Mode) 存草稿箱与附件自动添加**：
   - 触发 `发邮件` 或 `--send-mail` 时，Playwright 在后台无头模式（`headless=True`）静默执行。
   - 自动清理失效 session cookie 彻底消除 `会话已过期` 弹窗。
   - 使用 Coremail 官方 KindEditor API (`window.KindEditor.instances[0].html(js_content)`) 将全量 HTML 计划表（含 5 大统计卡片、13 列表格、底部 @ 负责人列表及风险反馈 Prompt）完整注入正文。
   - **自动将生成的 HTML 计划表（如 `拟排期需求计划表20260821-吴进.html`）作为邮件附件上传添加**。
   - **默认存入 Coremail 邮件草稿箱**，顶部弹出 `保存草稿成功`，方便用户登录邮箱复核后手动点击发送（带 `--force-send` 才强行直接发送）。

3. **初版计划表与沟通后清单 (-r) 收件人一致性保障机制**：
   - 生成初版 `拟排期需求计划表` 时，系统自动将当前版本的全部相关人员名单持久化缓存。
   - 生成或起草 `拟排期需求明细清单` (`-r` 模式) 时，系统**自动继承并合并 (Union) 初版计划表的全部收件人**。
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
# 1. 生成计划表并自动起草存入 Coremail 邮件草稿箱（默认行为，后台无头模式）
python3 /Users/wujin/.workbuddy/skills/planned-schedule/scripts/proposed_schedule_confirm.py 20260821 --send-mail

# 2. 沟通后拟计划上线清单模式（传入 -r 参数）
python3 /Users/wujin/.workbuddy/skills/planned-schedule/scripts/proposed_schedule_confirm.py 20260821 -r

# 3. 沟通后拟计划上线清单模式并起草邮件存草稿箱
python3 /Users/wujin/.workbuddy/skills/planned-schedule/scripts/proposed_schedule_confirm.py 20260821 -r --send-mail

# 4. 强行直接发送邮件（跳过草稿箱人工确认）
python3 /Users/wujin/.workbuddy/skills/planned-schedule/scripts/proposed_schedule_confirm.py 20260821 --send-mail --force-send

# 5. 生成计划表并自动上传到腾讯文档指定文件夹（同名覆盖/不同名新增）
python3 /Users/wujin/.workbuddy/skills/planned-schedule/scripts/proposed_schedule_confirm.py 20260821 --upload

# 6. 生成计划表 + 上传腾讯文档 + 起草邮件存草稿箱（一键combo）
python3 /Users/wujin/.workbuddy/skills/planned-schedule/scripts/proposed_schedule_confirm.py 20260821 --upload --send-mail

# 7. 仅查询腾讯文档同名情况（dry-run，不真正上传）
python3 /Users/wujin/.workbuddy/skills/planned-schedule/scripts/proposed_schedule_confirm.py 20260821 --upload --dry-run

# 8. 独立上传已有 HTML 到腾讯文档指定文件夹（可指定其它文件夹）
python3 /Users/wujin/.workbuddy/skills/planned-schedule/scripts/upload_to_tencent.py "拟排期需求计划表20260821-吴进.html" --folder "TNLKgDkNdIvP"
```

---

## ☁️ 腾讯文档自动上传（同名覆盖 / 不同名新增）

> [!IMPORTANT]
> 生成 HTML 后，可通过 `--upload` / `--tencent` / `--tdoc` 参数自动上传到腾讯文档指定文件夹。
> **默认目标文件夹：`版本计划排期`（ID `TNLKgDkNdIvP`，链接 `https://docs.qq.com/desktop/mydoc/folder/TNLKgDkNdIvP`），可用 `--tencent-folder` 覆盖为其他文件夹。**

**同名覆盖逻辑**：
- 上传前先查询目标文件夹内容（`manage.folder_list`）。
- 若已存在同名文档 → 先删除旧文档（`manage.delete_file`）再放入新文档，即**同名覆盖**（文件夹中始终只保留最新一份）。
- 若不存在同名 → 直接新增，即**不同名新增**。

**上传技术通路**（独立脚本 `upload_to_tencent.py`，纯 Python 自动完成）：
1. **净化 HTML**：上传前自动生成净化版，移除 `data-flat` 巨型属性（属性值内嵌完整 HTML、腾讯文档 aipage 解析不兼容，会造成表格上方 HTML 源码乱码泄漏）与内联 `<script>`（腾讯文档不执行 JS）；本地原文件不受影响。
1. `aipage_pack.js`（受管 Node）将净化版 HTML 打包为 `.aipage`；
2. `manage.pre_import` 获取 COS 上传链接 → curl PUT 上传；
3. `manage.async_import` + `manage.import_progress` 轮询导入完成，拿到在线 `file_url`；
4. 同名判定后 `manage.move_file` 放入目标文件夹（必要时先删除旧文档）。

**环境依赖**（脚本已内置处理，无需手动设置）：
- 必须使用**受管 Node** `/Users/wujin/.chat/runtimes/darwin-x64/node/versions/22.22.2/bin/node` 运行 mcporter 与 aipage_pack.js（系统 PATH 中的 connector-runtime node 会 V8 崩溃，脚本已显式指定受管路径规避）。
- 腾讯文档 MCP 需走代理 `http://172.16.0.11:3128`，脚本已自动注入完整的 `HTTPS_PROXY/https_proxy/HTTP_PROXY/http_proxy/ALL_PROXY/no_proxy` 环境变量。

**输出示例**：
```bash
[ProposedSchedule] ☁️ [腾讯文档] 已同名覆盖上传成功: https://docs.qq.com/page/DVGpZZVJHTUtEdWxi
[ProposedSchedule]   📂 文档ID: TjYeRGMKDulb
```

```bash
[ProposedSchedule] ☁️ [腾讯文档] 已新增上传成功: https://docs.qq.com/page/DVHNjZktCY1JjaU5v
```

---

## 📂 产物保存规范

> [!IMPORTANT]
> - 生成的 HTML 文件默认强保存在 `/Volumes/Macintosh HD_Data/obsidian/100_Projects/进度跟踪` 目录下（脚本自动创建该目录；可通过 `--output_html` 参数覆盖为其他路径）。
> - 默认文件命名：
>   - 普通计划表模式：`拟排期需求计划表<版本号>-<受理人>.html` (例: `拟排期需求计划表20260821-吴进.html`)
>   - 沟通后上线清单模式 (`-r`)：`拟排期需求明细清单<版本号>-<受理人>.html` (例: `拟排期需求明细清单20260821-吴进.html`)
> - 默认只生成 HTML 计划表（`.md` Markdown 文件无需默认生成，仅在显式指定 `--output_md` 或 `--table-only` 时生成）。
