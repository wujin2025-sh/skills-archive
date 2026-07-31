---
name: spb-mail
description: >
  国泰海通版本发布邮件内容生成工具。根据中心+日期，从 SVN 获取当日提交记录（分支级过滤）、
  从 Excel 读取 Task 信息、计算升级包 MD5，生成结构化 TXT + HTML 邮件内容，并支持一键自动保存草稿及发送邮件。
  支持多中心配置（JZJY集中交易、CSZX参数中心），区分 Task新增/更新 双模式。
  触发词：版本邮件、发布邮件、release mail、版本报告、release report、发版邮件、
  生成邮件、邮件内容、发邮件、发送版本邮件、spb-mail。
agent_created: true
---

# 版本邮件

生成版本发布邮件内容的自动化工具。从 SVN + Excel + ZIP 三个数据源提取信息，
输出可直接用于邮件正文的 TXT 和 HTML 文件，并支持自动同步到 Coremail 发送/存草稿。

## 工作流程

### Step 1: 确定参数

从用户输入中提取三个参数：

| 参数 | 说明 | 示例 |
|------|------|------|
| 中心 | 目标系统中心 | `JZJY`（集中交易）、`CSZX`（参数中心） |
| 日期 | 版本日期（8位） | `20260529` |
| 类型 | Task新增/更新（可选） | 省略=`add`（新增），`upt`=（更新） |

- 如用户只说了系统名（如 "jzjy的版本邮件"），则中心=`JZJY`，询问日期
- 如用户直接给了完整参数（如 "JZJY 20260529"），直接执行
- 类型默认为 `add`，如用户提及"更新"、"upt"则改为 `upt`

确定当前工作目录：
- `cd` 到项目根目录（包含 `jzjy/` 和 `jygl/` 子目录的项目），脚本从中心对应的 `data_subdir` 读取 Excel 和 ZIP

### Step 2: 运行脚本

```bash
cd <项目目录> && python3 <SKILL_DIR>/scripts/release_mail.py <中心> <日期> [类型]
```

- `<项目目录>`：包含 `jzjy/` 和 `jygl/` 子目录的项目根目录（Excel + ZIP 所在位置）
- `<SKILL_DIR>`：技能安装目录（即本 SKILL.md 所在目录）

示例：
```bash
# JZJY 新增模式
cd <项目目录> && python3 <SKILL_DIR>/scripts/release_mail.py JZJY 20260529

# CSZX 更新模式
cd <项目目录> && python3 <SKILL_DIR>/scripts/release_mail.py CSZX 20260529 upt
```

### Step 3: 呈现结果

脚本生成两个文件，且 **stdout 同时输出文本预览 + HTML 内容**：

- `release_report.txt` — 纯文本邮件内容
- `release_report.html` — 带样式的 HTML 版本

完成第一步后，简要汇报：
- 版本号 + 中心名称
- Task 数量（区分新增/更新）
- SVN 提交数（仅本分支）

### Step 4: 对话窗口同步 HTML

脚本 stdout 已包含 HTML 内容预览。代理在收到输出后，**必须将 HTML 内容清理后同步打印到对话窗口**，格式为：

```
以下是 release_report.html 的完整内容：

---
<HTML 内容原文，保留标题 + Task + MD5 + 变更等核心块>
---
```

如果 HTML 较长（SVN 变更路径超过 5 条），可对路径列表做折叠摘要。

### Step 5: 发送邮件 (发邮件)

当用户指示“发邮件”、“发送邮件”或“存入草稿箱”时：
1. 确定当前中心：根据前面生成的版本邮件所属中心（`JZJY` 或 `CSZX`）。
2. 根据目标中心确定收件人（To）和抄送人（Cc）：
   - **JZJY (集中交易)**：
     - 收件人：`"李萍萍" <lipingping@gtht.com> ; "陈浩宇" <chenhaoyu@gtht.com> ; "陈曦" <chenxi10@gtht.com> ; "1791894837" <1791894837@qq.com> ; "高健" <gaojian2@gtht.com> ; "shenss" <shenss@guoliansh.com> ; "贺元成" <heyuancheng@gtht.com> ; "张子安" <zhangzian@gtht.com> ; "陈紫菡" <chenzihan@gtht.com> ; "常丽" <changli@gtht.com> ; "张博闻" <zhangbowen@gtht.com> ;`
     - 抄送：`"苏清玲" <suqingling@gtht.com> ; "李鹤晨" <lihechen@gtht.com> ; "张康" <zhangkang2@gtht.com> ;`
   - **CSZX (参数中心)**：
     - 收件人：`"万鑫明" <wanxinming@gtht.com> ; "白淋" <bailin2@gtht.com> ; "李龙龙" <lilonglong@gtht.com> ; "张颖" <zhangying12@gtht.com> ; "丁伟" <dingwei2@gtht.com> ; "夏添" <xiatian2@gtht.com> ; "15021289638" <15021289638@163.com> ; "高健" <gaojian2@gtht.com> ; "陈紫菡" <chenzihan@gtht.com> ;`
     - 抄送：`"鄂文博" <ewenbo@gtht.com> ; "程菲" <chengfei@gtht.com> ; "苏清玲" <suqingling@gtht.com> ; "张康" <zhangkang2@gtht.com> ;`
3. 运行通用保存邮件草稿/发送脚本：
    - 邮件主题（Subject）构建规则（`release_mail.py` 已自动在 `release_report.txt` 首行生成 `主题：<主题内容>`，`save_to_draft.py` 会自动解析并剥离该行）：
      - **JZJY (集中交易)**：
        - `upt` (更新) 模式：`【版本更新】SPB_V2.2.19_{日期}` (如 `【版本更新】SPB_V2.2.19_20260703`)
        - `add` (新增) 模式：`【版本发布】SPB_V2.2.19_{日期}` (如 `【版本发布】SPB_V2.2.19_20260703`)
      - **CSZX (参数中心)**：
        - `upt` (更新) 模式：`【版本更新】CSZX-{日期}` (如 `【版本更新】CSZX-20260703`)
        - `add` (新增) 模式：`【版本发布】CSZX-{日期}` (如 `【版本发布】CSZX-20260703`)
    - 在工作目录下执行以下命令（添加 `--send` 参数可直接发送，不带 `--send` 则默认存为草稿）：
      ```bash
      python3 /Users/wujin/.workbuddy/skills/spb-mail/scripts/save_to_draft.py --subject "<上述邮件主题>" --body-file "release_report.txt" --recipients "<收件人列表>" --cc "<抄送人列表>" [--send]
      ```

## 中心配置

| 中心 | 系统 | 版本前缀 | 数据子目录 | SVN 仓库 |
|------|------|----------|------------|----------|
| JZJY | 集中交易 | SPB_V2.2.19_{版本号} | jzjy/ | Src/01Branches/Produce |
| CSZX | 参数中心 | CSZX-{版本号} | jygl/ | Src/01Branches/02Trunk_jygl_prod/jygl_prod_s |

脚本从 `当前目录/<数据子目录>/` 下读取 Excel 和 ZIP 文件。

## SVN 分支过滤

SVN REPORT 请求的是整个 `jjywpt` 仓库，但日志解析时按 `path_in_repo` 进行**分支级过滤**：
- 只保留 `changed_paths` 以当前中心 `svn_repo` 内部路径开头的提交
- 例如 CSZX 只保留 `/Src/01Branches/02Trunk_jygl_prod/jygl_prod_s/...` 下的变更
- JZJY 同理只保留 `/Src/01Branches/Produce/...` 下的变更

## Excel 读取说明

| 模式 | 读取文件 |
|------|----------|
| add (新增) | `{VERSION_NAME}.xlsx` |
| upt (更新) | `{VERSION_NAME}_upt.xlsx` |

Excel 必须包含列：`Task编号`、`Task标题`

## 输出格式

- TXT：spb 风格详细格式（含 SVN 变更文件列表），适合直接粘贴到邮件
- HTML：jygl 风格美化格式（Microsoft YaHei 字体、结构化排版），适合浏览器预览

## 依赖

脚本需 `pandas`、`openpyxl`、`xml.etree.ElementTree`（标准库）。Python 3.x 环境即可。
