---
name: meeting-invite
description: '线上会议邀请邮件一键自动保存到 Coremail 草稿箱技能。 该技能根据输入的会议要素（需求名称、详情链接、会议主题、时间、会议链接、ID、密码、收件人），生成并优化格式，确认后一键保存到草稿箱。
  支持整段腾讯会议文本自动解析，支持收件人本地白名单匹配校验。 触发词：需求会议邀请、需求沟通邮件、起草会议邮件、评审会议邀请、需求评审会议邀请、demand-meeting-invite、meeting-invite。

  '
disable: false
---


# 线上会议邀请技能 (Meeting Invite)

## 技能介绍
本技能用于快速起草和发送“需求沟通”或“需求评审”会议的线上邀请邮件。
在发送至 Coremail 之前，系统会根据用户输入的内容优化格式与措辞，展现给用户确认。在用户发出“发邮件”指令后，自动将邮件保存至 Coremail 草稿箱。

## 工作流与交互规则
1. **要素解析与润色**：
   当收到用户的输入时，支持以下智能操作：
   - **需求一键补全**：若输入中只提供需求编号（如 `R2604290048`），智能体联网使用 API 获取标题与 URL，免去您手动复制。
   - **原始文本解析**：可直接传入整段腾讯会议邀请文本，脚本将使用正则表达式自动提取会议主题、时间（智能补足北京时区后缀）、链接、ID、密码。
   - **收件人白名单匹配**：自动将收件人姓名与本地 `人员部门对应关系表.csv` 进行比对，若名字拼错（例如写成别字），提前在预览中高亮警告。
   - **发件/邀请人**：默认为“吴进”。

2. **用户二次确认**：
   整理并排版为以下标准格式，在聊天框中呈现给用户确认：
   ```text
   收件人：金渤文 徐旖旎 石雪军 张忍 连永进
   
   【个微两融柜台】支持授信额度实时调整
   https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId=R2607090120&templateId=8888&flag=1
   
   吴进 邀请您参加线上会议
   会议主题：个微柜台 支持授信额度实时调整-需求沟通
   会议时间：2026-07-20 09:00-10:00(GMT+08:00) 中国标准时间 - 北京
   
   点击链接入会，或添加至会议列表：
   http://www.gtht.com/=fruaJJ
   
   会议 ID：113124524
   会议密码：007007
   *参会人也可通过腾讯会议进入
   ```

3. **保存至草稿箱**：
   用户确认并输入“发邮件”或“确认保存”后，调用下方脚本进行 Playwright 自动化处理，将邮件存至 Coremail 草稿箱中。

## 执行指令 (Run Commands)

使用 `--raw-meeting` 自动解析模式（推荐）：
```bash
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python "/Users/wujin/.workbuddy/skills/meeting-invite/scripts/draft_demand_meeting.py" \
  --recipients "金渤文 徐旖旎 石雪军 张忍 连永进" \
  --demand-title "【个微两融柜台】支持授信额度实时调整" \
  --demand-url "https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId=R2607090120&templateId=8888&flag=1" \
  --raw-meeting "吴进 邀请您参加线上会议
会议主题：个微柜台 支持授信额度实时调整-需求沟通
会议时间：2026-07-20 09:00-10:00

点击链接入会，或添加至会议列表：
http://www.gtht.com/=fruaJJ

会议 ID：113124524
会议密码：007007
*参会人也可通过腾讯会议进入"
```

使用分项参数手动指定模式：
```bash
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python "/Users/wujin/.workbuddy/skills/meeting-invite/scripts/draft_demand_meeting.py" \
  --recipients "金渤文 徐旖旎 石雪军" \
  --demand-title "【个微两融柜台】支持授信额度实时调整" \
  --demand-url "https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId=R2607090120" \
  --meeting-theme "个微柜台 支持授信额度实时调整-需求沟通" \
  --meeting-time "2026-07-20 09:00-10:00(GMT+08:00) 中国标准时间 - 北京" \
  --meeting-link "http://www.gtht.com/=fruaJJ" \
  --meeting-id "113124524" \
  --meeting-password "007007"
```

### 参数说明
- `--recipients`：收件人姓名列表，由空格、分号或逗号分隔。
- `--demand-title`：需求标题。
- `--demand-url`：需求详情链接。
- `--raw-meeting`：整段腾讯会议客户端生成的邀请内容。
- `--meeting-theme`：（可选）会议主题，省略时由 raw-meeting 提取。
- `--meeting-time`：（可选）会议时间，省略时由 raw-meeting 提取。
- `--meeting-link`：（可选）入会链接，省略时由 raw-meeting 提取。
- `--meeting-id`：（可选）会议 ID，省略时由 raw-meeting 提取。
- `--meeting-password`：（可选）会议密码，省略时由 raw-meeting 提取。
- `--sender`：（可选）邀请人姓名，默认为 "吴进"。
- `--cc`：（可选）抄送人姓名列表。
- `--dry-run`：（可选）仅格式化并校验，不进行 Coremail 网页填报存盘。
