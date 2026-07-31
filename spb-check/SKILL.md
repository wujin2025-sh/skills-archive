---
name: spb-check
description: >
  主要比对解压后的版本包文件夹（SPB_V2.2.19_20260710 或 CSZX-20260710）与 excel_output.txt 之间声明的内容是否一致，进行双向文件与内容核对工作。
  触发词：spb-check、spb检查、版本包比对、spb比对、spbcheck。
agent_created: true
---

# spb-check (SPB 版本包与报告双向比对核对技能)

此技能能够自动化核对解压后的版本文件夹（如 `SPB_V2.2.19_20260710` 或 `CSZX-20260710`）与导出的 `excel_output.txt` 报表中的 DLL、Client CLI、SQL表、存储过程、以及 init 脚本等元素是否在版本包中一致。

支持 `jzjy` (集中交易) 与 `cszx` (参数中心) 两种不同系统的特定结构验证。

## 工作原理与校验规则

1. **输入解析 (Parsing `excel_output.txt`)**：
   * **`cli`**: 提取需要放置在 `client/` 的 dll 列表（例如 `CmCli_Of` -> `CmCli_Of.dll`）。
   * **`DLL`**: 提取需要放置在 `lbm/` 的 dll 列表（例如 `lbm_acct` -> `lbm_acct.dll`）。
   * **`Table`**: 
     * 若包含 `table_run_list.append`，提取需要出现在 `table/` 内容（`.sql` 文件）中的表名。
     * 若为直接列出的 SQL 文件名，检查该文件是否在 `table/`（及其子目录 `build_table` 等）中存在。
   * **`ProcUpd` / `ProcAdd`**:
     * 若包含 `proc_list.append`，提取需要出现在 `proc/` 内容（`.sql` 文件）中的存储过程名。
     * 若为直接列出的 SQL 文件名，检查该文件是否在 `proc/`（及其子目录）中存在。
   * **`init`**: 提取需要放置在 `init/` 中的脚本、zip或xml文件，核对它们在 `init/` 下是否存在。若不存在但在包内其他地方，标记为**警告**（位置错乱）。

2. **双向比对 (Bidirectional Audit)**：
   * **正向核对**：检查 `excel_output.txt` 声明的所有项是否在版本包中存在/被包含。
   * **反向核对**：检查版本包中各目录（`client`、`lbm` , `init`, `table`, `proc`）的多余文件，排查是否存在未在 `excel_output.txt` 中声明的“孤儿文件”。

3. **报告生成**：
   * 在控制台输出美化的终端比对表格。
   * 在比对文件夹下自动写入比对报告 `spb_check_report.md`，并在包同级目录下自动生成 HTML 格式的美化核对报告 `{包名}_check_report.html`。

4. **压缩包自动解压 (Auto-Unzip)**：
   * 若自动匹配到的最新版本包仅存在 `.zip` 压缩文件且未解压，工具将**自动在后台执行解压**（创建与 zip 文件名同名的已解压文件夹），并能自动处理并消除解压出的单层嵌套文件夹路径。

---

## 常用参数与配置

命令行调用支持以下参数：

| 参数 | 缩写 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `--dir` | `-d` | *自动搜索* | 要检查的版本包文件夹路径（例如 `SPB_V2.2.19_20260710`）。不传则自动在当前目录搜寻匹配的文件夹。 |
| `--file` | `-f` | `excel_output.txt` | 比对参考的 txt 报表路径（默认 `excel_output.txt`，也可以是 `upt_excel_output.txt`）。 |
| `--system` | `-s` | *自动识别* | 指定系统类型：`jzjy` 或 `cszx`。不传则根据当前目录名/路径或文件夹前缀自动识别。 |
| `--output` | `-o` | `./spb_check_report.md` | 输出比对报告的文件名。 |

---

## 使用说明

### 代理调用指南

当用户要求比对版本包内容或运行 `spb-check` 时：
1. 确定运行的系统目录（`jzjy` 目录或 `jygl` 目录）。
2. 在对应的目录下调用以下命令：

```bash
# 默认比对 excel_output.txt
python3 /Users/wujin/.workbuddy/skills/spb-check/scripts/spb_check.py

# 指定比对增量报告 upt_excel_output.txt
python3 /Users/wujin/.workbuddy/skills/spb-check/scripts/spb_check.py -f upt_excel_output.txt
```
3. 检查控制台输出，并将生成的 `spb_check_report.md` 报告内容以 Markdown 格式呈现给用户。同时，系统在核对完成后会在包目录下自动生成对应的 HTML 格式核对报告：如 `SPB_V2.2.19_20260710_check_report.html`。

---

## 发邮件指令

当用户在核对后指示对核对报告进行“发邮件”、“发送邮件”或“存草稿”时：

> [!IMPORTANT]
> **默认行为**：在此技能中，输入“发邮件”指令时**默认直接且只执行自动存入草稿箱**。命令行中**不得包含 `--send` 参数**，直接在后台创建草稿即可，不需要询问用户是否直接发送。

1. **确定当前核对系统与报告路径**：
   - **集中交易 JZJY**：核对报告 HTML 文件为 `jzjy/SPB_V2.2.19_{日期}_check_report.html`。
   - **参数中心 CSZX**：核对报告 HTML 文件为 `jygl/CSZX-{日期}_check_report.html`。
2. **邮件主题格式**：
   - 集中交易：`【版本核对报告】SPB_V2.2.19_{日期}`（例如：`【版本核对报告】SPB_V2.2.19_20260710`）
   - 参数中心：`【版本核对报告】CSZX-{日期}`（例如：`【版本核对报告】CSZX-20260710`）
3. **收件人与抄送人配置**：
   - **JZJY (集中交易)**：
     - 收件人：`lipingping@gtht.com; chenhaoyu@gtht.com; chenxi10@gtht.com; 1791894837@qq.com; gaojian2@gtht.com; shenss@guoliansh.com; heyuancheng@gtht.com; zhangzian@gtht.com; chenzihan@gtht.com; changli@gtht.com; zhangbowen@gtht.com`
     - 抄送：`suqingling@gtht.com; lihechen@gtht.com; 张康 <zhangkang2@gtht.com>`
   - **CSZX (参数中心)**：
     - 收件人：`wanxinming@gtht.com; bailin2@gtht.com; lilonglong@gtht.com; zhangying12@gtht.com; dingwei2@gtht.com; xiatian2@gtht.com; 15021289638@163.com; gaojian2@gtht.com; chenzihan@gtht.com`
     - 抄送：`ewenbo@gtht.com; chengfei@gtht.com; suqingling@gtht.com; zhangkang2@gtht.com`
4. **命令行保存到草稿箱**：
   在工作目录下运行（不加 `--send`）：
   ```bash
   python3 /Users/wujin/.workbuddy/skills/spb-mail/scripts/save_to_draft.py --subject "<上述邮件主题>" --body-file "<HTML报告路径>" --recipients "<收件人列表>" --cc "<抄送人列表>"
   ```

---

## 示例输出格式 (Example Output Format)

当核对失败（如 JZJY 存在文件缺失）时，标准输出格式如下：

```text
1. 客户端 CLI 核对 (共 2 项, 🟢 全部通过)
  • 🟢 CmCli_Of ➔ CmCli_Of.dll 已在 client/ 文件夹中存在。
  • 🟢 Cli_Of ➔ Cli_Of.dll 已在 client/ 文件夹中存在。

2. 核心 DLL 核对 (共 9 项, 🟢 全部通过)
以下 LBM 模块 of DLL 文件均已正确存放在 lbm/ 文件夹中：

  • 🟢 lbm_acct ➔ lbm_acct.dll 存在。
  ...

3. SQL 表结构核对 (共 4 项, 🔴 1 项缺失)
  • 🟢 表名 snonightorderid ➔ 成功在 build_table/build_table_shilibinJZJYPT-T202606586.sql 文件内容中找到。
  • 🔴 build_table_T202606586_slb.sql ➔ 文件缺失。
```

