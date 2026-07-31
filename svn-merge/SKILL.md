---
name: svn-merge
description: >
  SVN Task编号粒度代码合并工具。从指定的源分支（UAT）搜索与给定Task编号（例如 JZJYPT-T202504823）
  相关的提交修订版本（Revision），并一次性合并到本地工作目录中。若合并无冲突，则自动提交并附加标准日志；
  若有冲突，则自动回滚（revert）并重新更新本地，确保工作副本干净。运行结束后会生成冲突报告与执行汇总。
  触发词：svn-merge、dyssvn-merge、svn代码合并、代码合并、svn merge、svn 合并、dyssvn_merge_V3.py。
agent_created: true
---

# svn-merge (SVN代码合并技能)

此技能能够自动化执行按Task编号维度的分支代码合并、冲突自动回撤、以及无冲突自动提交。本工具**不依赖特定操作系统，全面支持 Windows 与 macOS**，并且会自动根据当前操作系统适配其默认的本地工作目录和 SVN 可执行文件路径。

支持将 Excel 复制的多行“Task编号-任务”表格数据作为输入，按Task编号自动分组并行处理。

## 工作原理与流程

1. **工作副本更新**：对本地工作目录执行 `svn update --accept theirs-full`，以获取最新的代码基线。
2. **输入解析**：解析输入的表格内容，提取“Task编号、任务号、任务标题、经办人”等字段，并以“Task编号”为维度进行分组。
3. **日志检索**：对每个Task编号，在合并来源的分支（如 `MERGE_SOURCE`）上执行 `svn log --search <Task编号>`，找出所有相关的修订版本（Revisions）。
4. **批量合并**：一次性将某一Task编号的所有 Revision 合并 to 本地：`svn merge -c r1 -c r2 ... <MERGE_SOURCE> --accept postpone`。
5. **冲突处理**：
   * **有冲突**：若检测到冲突文件，执行 `svn revert -R .` 撤销本次合并，更新本地基线（`svn update --accept theirs-full`），并将该Task编号记录为“冲突”。
   * **无冲突**：
     * 若合并后本地工作副本没有实际代码变更，直接跳过提交。
     * 若有变更，自动生成多行 commit message 并提交：
       ```text
       【前缀】任务号  任务标题  经办人
       任务号  任务标题  经办人 （若一个需求关联多个任务）
       ```
 6. **报告汇总**：处理完所有任务后，在指定的输出目录下生成：
    * `summary_<时间戳>.txt`：整体执行的分类统计与明细。
    * `conflict_reqs_<时间戳>.txt`：发生冲突的Task编号、关联任务以及具体的冲突文件列表。
    * `conflict_diff_<冲突文件>.txt`：发生冲突的文件的详细差异文本（包含冲突标记）。
    * `conflict_diff_<冲突文件>.png`：专为冲突文件生成的语法高亮暗色模式**比对截图**（可直接用于邮件附件或展示）。

---

## 常用参数与配置

命令行调用支持以下参数：

| 参数 | 缩写 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `--data-text` | `-d` | *无* | 合并输入数据，可以是**行内Tab分隔文本**、**文本文件路径**，或通过标准输入 **stdin** 传入。 |
| `--commit-prefix` | `-p` | *自适应* | Commit 日志的分类前缀。默认从当前执行目录下的 `合并版本号.txt` 读取内容，若读取失败或文件不存在则默认为 `703`。 |
| `--local-dir` | `-l` | *OS自适应* | 本地 SVN 工作副本目录路径。在 Windows 上默认为 `F:\spb\spbsrc`，在 macOS 上默认为 `/Volumes/Macintosh HD_Data/Project/jzjy/spbsrc`。 |
| `--merge-source` | `-s` | `https://jyjs.svn.gtja.net/svn/jjywpt/Src/01Branches/spbsrc_uat_2024` | 来源分支的 SVN 仓库 URL（例如 UAT 分支）。 |
| `--svn-username` | `-u` | `wujin@gtht.com` | SVN 认证用户名。 |
| `--svn-password` | *无* | *加密存储* | SVN 认证密码（默认为加密后的密文）。 |
| `--log-limit` | *无* | `2000` | svn log 检索的最大行数。 |
| `--output-dir` | `-o` | `./<commit-prefix>` | 输出报告的路径，默认在当前工作目录的 commit-prefix 文件夹下。 |
| `--svn-executable` | *无* | *空* | 手动指定的 `svn.exe` 或 `svn` 命令行工具路径。 |

---

## 使用说明

### 代理调用指南

当用户要求您协助合并代码时，您需要：
1. **收集输入数据**：提示用户提供“Task编号-任务号-任务标题-经办人”列表（通常直接从 Excel 复制多行，默认用 Tab 分隔）。
2. **询问/推导配置**：
   * **合并前缀**（`-p`）：默认为今日的发布批次（如 `703`，可根据当前日期或批次提示用户）。
   * **工作副本目录**（`-l`）：若在特定项目下操作，可以确认是否为默认的 `/Volumes/Macintosh HD_Data/Project/jzjy/spbsrc`。
3. **构造并执行命令**：
   * 将输入数据写入临时文件，或通过 echo 传入 stdin。
   * 执行以下命令示例：

```bash
# 方式 1：通过参数直接传入数据文本
python3 /Users/wujin/.workbuddy/skills/svn-merge/scripts/svn_merge.py \
  -p "703" \
  -d "JZJYPT-T202504823	123456	债券质押式开发需求	蔡静雯-123576"

# 方式 2：使用 stdin 传入多行 Excel 复制的数据
cat << 'EOF' | python3 /Users/wujin/.workbuddy/skills/svn-merge/scripts/svn_merge.py -p "703"
JZJYPT-T202504823	123456	债券质押式开发需求	蔡静雯-123576
JZJYPT-T202504824	123457	另一个开发需求	李四-123456
EOF
```

4. **解析并展示结果**：
   * 读取终端输出或自动生成的 `summary_*.txt` 和 `conflict_reqs_*.txt` 文件，向用户汇报成功合入的Task编号、无 Revision 跳过的任务、以及有冲突并已安全 Revert 的任务，列出冲突文件供人工介入解决。

---

## macOS 环境必读（TLSv1.0 + 钥匙串认证）

在 macOS 上使用 Homebrew 安装的 SVN (1.14.x) + OpenSSL 3.x 环境下，会遇到两个关键问题：

### 问题 1：SSL 通信失败 (E120171)

SVN 服务器 `jyjs.svn.gtja.net` 仅支持 **TLSv1.0**，但 OpenSSL 3.x 默认禁用了 TLSv1.0（安全原因）。表现为：
```
svn: E170013: Unable to connect to a repository at URL '...'
svn: E120171: Error running context: An error occurred during SSL communication
```

**解决方案**：创建自定义 OpenSSL 配置文件，降低最小 TLS 版本：

```bash
# 创建 /tmp/svn-merge-fix/openssl.cnf，内容如下：
cat > /tmp/svn-merge-fix/openssl.cnf << 'EOF'
openssl_conf = openssl_init

[openssl_init]
providers = provider_sect
ssl_conf = ssl_sect

[provider_sect]
default = default_sect

[default_sect]
activate = 1

[ssl_sect]
system_default = system_default_sect

[system_default_sect]
MinProtocol = TLSv1
CipherString = DEFAULT:@SECLEVEL=0
EOF

# 执行合并时设置环境变量：
OPENSSL_CONF=/tmp/svn-merge-fix/openssl.cnf python3 ...
```

### 问题 2：密码认证失败 (E215004)

脚本中加密存储的 SVN 密码可能已过期。macOS 上 SVN 认证信息保存在 **钥匙串 (Keychain)** 中，用户名为工号（如 `125360`），而非 `wujin@gtht.com`。

**解决方案**：传入空用户名和空密码，让 SVN 自动使用钥匙串认证：

```bash
python3 svn_merge.py ... -u "" --svn-password ""
```

### 问题 3：cryptography 库未安装

脚本使用 `cryptography.Fernet` 解密密码。若使用裸 Python 环境而非 venv，会因缺少 `cryptography` 库导致解密静默失败（返回密文原文）。

**解决方案**：使用 venv Python 路径：
```bash
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python svn_merge.py ...
```
若 venv 中未安装 cryptography：
```bash
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/pip install cryptography
```

### macOS 完整执行命令模板

```bash
OPENSSL_CONF=/tmp/svn-merge-fix/openssl.cnf \
/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python \
  /Users/wujin/.workbuddy/skills/svn-merge/scripts/svn_merge.py \
  -d $'JZJYPT-T202606586\t任务标题\t经办人-工号' \
  -l "/Volumes/Macintosh HD_Data/Project/jzjy/spbsrc" \
  -o "/Users/wujin/WorkBuddy/<工作目录>/703" \
  -u "" \
  --svn-password ""
```

### SVN 工作副本锁修复

若遇到 `E155004: Failed to lock working copy` 或 `E200031: sqlite[S8]: attempt to write a readonly database`：

```bash
# 1. 删除残留的 journal 文件
rm -f "<local-dir>/.svn/wc.db-journal"
# 2. 移除 macOS 扩展属性
xattr -d com.apple.provenance "<local-dir>/.svn/wc.db" 2>/dev/null
# 3. 执行 svn cleanup
svn cleanup "<local-dir>" --non-interactive
```

---

## 冲突邮件发送指南

当代码合并过程中检测到冲突并自动回撤后，我们可以运行冲突邮件草稿生成脚本，将冲突的文件明细和代码比对详情直接发送（起草）给对应的开发人员。本技能**只发送冲突及比对明细，不发送版本邮件**（版本邮件由 `spb-mail` 负责）。

### 执行命令

```bash
# 自动读取当前目录的 '合并版本号.txt' 作为版本目录，在 Coremail 起草冲突提示邮件
python3 /Users/wujin/.workbuddy/skills/svn-merge/scripts/draft_conflict_emails.py

# 也可以手动指定版本目录和版本前缀：
python3 /Users/wujin/.workbuddy/skills/svn-merge/scripts/draft_conflict_emails.py \
  -d "/Volumes/Macintosh HD_Data/WorkBuddy/版本发布/20260710" \
  -p "SPB_V2.2.19"
```

该脚本将自动执行以下操作：
1. 解析指定目录下的 `conflict_reqs_*.txt` 冲突文件列表。
2. 依据冲突人员姓名（如 `蔡静雯`），利用 `pypinyin` 库将其转换为拼音邮箱（如 `caijingwen@gtht.com`）。
3. 读取该需求发生冲突文件的比对明细文本（最多 150 行），直接作为 Markdown 代码块内嵌在邮件正文中。
4. 调用 Playwright 自动登录 Coremail，并为每位有冲突的开发人员起草一份专属的冲突通知邮件草稿（包含收件人、抄送 `苏清玲;张康`、主题和邮件正文），默认保存于邮箱草稿箱中。

