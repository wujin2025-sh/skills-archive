---
name: version-schedule-mail
description: >
  版本排期邮件一键自动保存到 Coremail 草稿箱技能。
  已配置指定的收件人（79位）和抄送人（7位），支持通过命令行指定主题和内容，一键在草稿箱中起草，自动存盘且不发送。
  触发词：版本排期邮件、起草版本排期、排期邮件草稿、存入版本排期草稿、version-schedule-mail。
agent_created: true
---

# 版本排期邮件自动起草技能 (Version Schedule Mail)

## 技能介绍
本技能用于快速将特定的“版本排期邮件”保存至 Coremail 草稿箱中。
已自动为您配置好了固定的收发件人和抄送人列表：
- **收件人**（79人）：周倩、刘勇明、胡玲杰、乔露露、聂章艳等。
- **抄送人**（7人）：王姝暘、赵永杰、周哲博、姜婷婷、纪飞、周尤珠、陈文培。

## 执行指令 (Run Commands)

在工作目录下执行以下命令起草版本排期邮件（请指定 `--subject` 及 `--body`，或者通过 `--body-file` 指定内容文件）：

```bash
python3 "/Users/wujin/.workbuddy/skills/version-schedule-mail/scripts/draft_schedule_email.py" --subject "<邮件主题>" --body "<邮件正文>"
```

### 参数说明
- `--subject`：指定邮件主题。如果省略且 `--body-file` 中第一行包含 `主题：`，会自动提取。
- `--body`：直接在终端中输入的邮件正文。
- `--body-file`：包含邮件正文的文件路径（可指定 HTML 或纯文本文件）。

## 结果确认
脚本执行完毕后，将在 `/Volumes/Macintosh HD_Data/WorkBuddy/邮件发送/` 下生成 `coremail_draft_saved.png` 存盘截图，并在控制台输出执行结果。
