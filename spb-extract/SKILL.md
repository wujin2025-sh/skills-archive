---
name: spb-extract
description: >
  SPB版本升级包内容提取工具。根据输入系统（jzjy集中交易、cszx参数中心）及版本号，
  提取对应升级包内的变更文件（dll, sql, xml等）并分类汇总。
  针对 cszx 自动生成包含 CMDB 字段与主备库配置的输出结构。
  输出文件 upt_content.txt 将保存在版本目录下及当前工作目录下。
  触发词：spb-extract、版本内容、提取版本内容、upt_extract、提取变更文件、生成变更内容。
agent_created: true
---

# spb-extract (版本内容)

自动提取并格式化版本发布中的升级包文件内容，生成标准化部署升级段落的工具。支持 JZJY（集中交易）和 CSZX（参数中心）两套不同的部署架构及 CMDB 部位格式。

## 工作流程

### Step 1: 确定参数

从用户输入中提取以下两个参数：

| 参数 | 说明 | 示例 |
|------|------|------|
| 系统名称 | 目标系统（快捷名称） | `jzjy`（集中交易）、`cszx`（参数中心） |
| 版本号 | 可选，对应文件夹的版本号/标识 | `20260529_hoth`（对于cszx）、`20260529`（对于jzjy） |

* 如果没有指定版本号，脚本会自动寻找唯一匹配的文件夹。
* 如果匹配到多个符合条件的版本文件夹，脚本会列出并提示用户指定版本号。

确定当前工作目录：
* 执行命令时需要在版本发布项目根目录下，该目录下应包含 `jzjy/` 和 `jygl/` 子目录。

### Step 2: 运行脚本

在终端中执行以下命令（以技能安装路径为准）：

```bash
cd <项目目录> && python3 <SKILL_DIR>/scripts/upt_extract.py <系统名称> [版本号]
```

* `<项目目录>`：包含版本数据文件夹的目录。
* `<SKILL_DIR>`：技能的安装目录（即本 `SKILL.md` 所在目录，通常为 `/Users/wujin/.workbuddy/skills/spb-extract`）。

示例：
```bash
# 提取参数中心 cszx 版本的变更内容
python3 /Users/wujin/.workbuddy/skills/spb-extract/scripts/upt_extract.py cszx 20260529_hoth

# 提取集中交易 jzjy 版本的变更内容（自动寻找唯一版本）
python3 /Users/wujin/.workbuddy/skills/spb-extract/scripts/upt_extract.py jzjy
```

### Step 3: 输出结果

脚本运行成功后，会在以下两个位置同时生成 `upt_content.txt` 文件：

1. **版本所在的目录下**（例如 `jygl/CSZX-20260529_hoth/upt_content.txt`）
2. **当前工作目录下**（即 `./upt_content.txt`）

> [!NOTE]
> 针对无变更文件的类别（如空目录或没有匹配的文件后缀），脚本会自动过滤，不会将其写入最终的 txt 中。

同时，终端 stdout 会打印出生成的完整内容。代理可以直接读取并展示给用户。

---

## 规则配置

### 1. 集中交易 (jzjy) 格式规则
* **主部位映射**：各类别保持原样：
  * `lbm` / `init2` -> `所有kcbp（包含公募基金）`
  * `init1` -> `所有核心、两个总控、VIP极速与融资融券1/2/3的run(包括公募`
  * `table` -> `table 目录内脚本`

### 2. 参数中心 (cszx) 格式规则
* **CMDB 注入**：每个小节自动包含主系统、CMDB 维护组等信息。
* **部署部位映射**：
  * 数据库及 SQL 脚本（`init1`, `table`, `proc`, `proc1`, `proc2`） -> `参数中心主库，参数中心备库`
  * 节点模块及 XML 配置（`lbm`, `init2`, `init3`, `memlbm`, `client`, `adaptor`） -> `ZJJ1,ZJJ2`
* **特别调整**：
  * `table` 变更文件修改为列出目录下的具体 SQL 脚本文件名
  * `table` 备注内容重写为 `按目录下脚本序号执行`
  * `proc` 文件夹下的 SQL 脚本，在 `cszx` 模式下直接汇总输出为单个 `proc` 节（不再细分为 `proc1` 与 `proc2`）。
