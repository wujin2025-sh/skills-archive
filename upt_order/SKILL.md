---
name: upt_order
description: '国泰海通全连接平台 EOA117 IT运维申请单通用自动填写工具。支持集中交易系统 (jzjy)、参数中心 (cszx)、95信创域 (95xinchuang)、98创新域
  (98chuangxin) 等系统的子版本上线发布表单填报。通过 Playwright 登录，自动填写表单各字段与弹窗，最终保存并截图确认。
  已融合 spb-extract（自动从版本文件夹提取变更内容生成 upt_content.txt，无需手动执行 spb-extract）。
  已融合 Artifactory：输入 `/upt_order jzjy 20261106`（关键词含 8 位日期）时，自动从 Artifactory 制品库
  (http://10.120.188.223:8082/artifactory/jyxt-JZJYPT-generic-prod-local/{日期}/) 下载**编号最大的压缩包**
  （如 SPB-V0.26.11.6-05.zip），解压到本地 jzjy/ 目录并提取变更内容，且「版本地址」字段直接填入该压缩包完整地址
  （不再读取云盘链接），后续升级单填写逻辑不变。

  触发词：升级单、EOA117、IT运维申请单、子版本上线、变更系统升级、提交升级单。

  '
disable: false
---


# 执行指令

当用户提及触发词时，**立即前台执行**脚本，无需后台运行：

## 1. 确定搜索关键词

按用户输入映射到脚本搜索关键词：

| 用户输入 | 脚本识别模式 | 实际搜索关键词 | 说明 |
|----------|-------------|---------------|------|
| 不输入（默认） | `jzjy` | `集中交易系统` | 默认执行集中交易系统升级 |
| `jzjy` / `集中交易` | `jzjy` | `集中交易系统` | 集中交易系统升级 |
| `cszx` / `参数` / `交易参数` | `cszx` | `交易参数管理后台` | 交易参数中心升级 |
| `95xinchuang` / `信创` / `95` | `95xinchuang` | `信创` | 信创域（95信创）升级 |
| `98chuangxin` / `创新` / `98` | `98chuangxin` | `创新` | 创新域（98创新）升级 |
| 其他文字 | `dynamic` | 原样传入脚本 | 进行动态模糊适配填报 |

## 2. 执行脚本（前台，非后台）

直接运行（替换 `{关键词}` 为实际值），**无需 `run_in_background`**，让用户实时看到输出：

```bash
cd ~/.workbuddy/skills/upt_order/scripts && (python3.14 eoa_subversion_release.py "{关键词}" 2>/dev/null || python3 eoa_subversion_release.py "{关键词}")
```

> 推荐使用 Python 3.14 运行；脚本会自动向下兼容适配环境。

## 3. 执行完毕后

- **成功** → 告知用户执行完毕，说明截图路径，读取 `scripts/eoa117_report.json` 展示结果，预览截图
- **失败** → 告知错误信息，建议用户手工介入完善

## 4. 用户手工介入 / 无头模式

- **有头模式**：脚本在 headed Chrome 模式下自动填写，浏览器窗口保持 60 秒供确认，用户可直接在浏览器中继续手工操作
- **无头模式**：在 `scripts/config.json` 中配置 `"headless": true` 和 `"slow_mo": 0`。脚本将以最快速度完成填写，并在执行完毕后立即退出，无需等待 60 秒

---

# 参考文档

## 表单填写字段一览

| 步骤 | 字段 | 默认值/匹配规则 | 方式 |
|------|------|----------------|------|
| 1 | 登录并打开申请单 | 工号 125360 / OA 平台登录与页面加载 | 自动检测/登录 |
| 2 | 保护变更分类不被修改 | 检查分类并保存初始值，并在保存前复查防止误改 | 只读检查 |
| 3 | 变更系统 | 根据参数级联定位至系统 | 级联选择 |
| 4 | 标题 | 按配置模板自动生成标题 | 自动生成 |
| 5 | 升级时间 | 当周五开始-结束时间窗（信创/创新：17:00~20:00；其它：17:30~23:30） | 键盘清空输入 |
| 6 | 紧急度 | 非紧急 | 下拉 |
| 7 | 是否补单 | 否 | Radio |
| 8 | 变更事由 | 常规版本升级 | 文本 |
| 9 | 实施负责人 | 98：张永军（108728）；jzjy：张博闻（111483）；cszx：张颖（116748） | 可搜索组织树勾选 |
| 10 | 工程号 | 弹窗搜索选择（jzjy→"集中交易"，cszx→"参数中心"，信创/创新→"NGTP持续建设"） | 弹窗 |
| 11 | 系统版本号 | 所有系统均采用 98 弹窗逻辑：点击"请选择系统版本号"进入弹出窗口，搜索并选择变更系统，再从下拉中选择版本 | 弹窗级联选择 |
| 12 | 预估变更操作耗时 | 10分钟至30分钟 | 下拉 |
| 13 | 回退用时 | 30分钟内 | 下拉 |
| 14 | 导致业务/系统中断时间 | 无中断 | 下拉 |
| 15 | 是否停机 | 是 | Radio/下拉 |
| 16 | 变更需求类型 | 普通业务功能 | 下拉 |
| 17 | 实施复杂度 | 跨系统（关联系统需要变更） | 下拉 |
| 18 | 变更组件 | 98/95：核心交易组件+BOS相关组件；其它：数据库+核心交易组件 | Checkbox/下拉 |
| 19 | 影响业务功能 | 交易系统实时交易 | Checkbox/下拉 |
| 20 | 影响用户范围 | 1万人以下投资者,多个部门 | Checkbox/下拉 |
| 21 | 变更系统信息 | **自动融合 spb-extract**：先自动定位版本文件夹提取变更内容生成 `upt_content.txt`；若提取成功则循环新增多条系统信息；否则回退到已有 `upt_content.txt` 或默认值兜底静态填写 | 弹窗 |
| 22 | 变更方案 | `jzjy` 循环填写 3 条，包含处理人张永军(108728)、张博闻(111483)、宋倩(114322)；`cszx` 填写 2 条；其它系统填写 1 条 | 弹窗 |
| 23 | 回退计划 | 策略=全部回退 / 条件=系统异常整体回退 / 步骤=回退至上一版本 | 弹窗 |
| 24 | 应急计划 | 异常场景=升级验证失败 | 弹窗 |
| 25 | 变更成功标准 | 升级验证成功 | 文本 |
| 26 | 版本地址 | **jzjy 模式优先使用 Artifactory 压缩包完整地址**（如 `http://10.120.188.223:8082/artifactory/jyxt-JZJYPT-generic-prod-local/20261106/SPB-V0.26.11.6-05.zip`，不使用云盘链接）；若未下载成功（无日期参数/下载失败），再回退 `版本地址.txt` 匹配或默认地址 | 文本 |
| 27 | 保存 | 底部保存按钮，并在保存前复查恢复可能被误改的变更分类 | 自动点击 |

## 🔐 密码加密配置

为保障账户安全，密码推荐以加密格式存储：
- 密码以 `ENC:<密文>` 格式存储在 `scripts/config.json` 中
- 解密密钥文件路径：`~/.workbuddy/.meeting_skill_key`（Fernet 对称加密，与"会议转纪要"技能共享）
- 脚本运行时自动检测解密；明文密码同样兼容支持

## 中间与输入文件（均在脚本或工作区目录下）

| 文件 | 说明 |
|------|------|
| `scripts/eoa_subversion_release.py` | 主脚本（通用版） |
| `scripts/config.json` | 平台登录配置（含加密密码） |
| `scripts/eoa117_verify.png` | 保存后验证截图 |
| `scripts/eoa117_report.json` | JSON 执行报告 |
| `scripts/eoa117_keyword_signal.json` | 交互信号文件（临时） |
| `upt_content.txt` | [输入文件] 升级包变更文件提取内容（用于循环填写变更系统信息）。**已融合 spb-extract：脚本会在 [18.55] 步骤自动从版本文件夹提取并覆盖生成，无需手动执行 spb-extract** |
| `版本地址.txt` | [输入文件] 各系统历史云盘链接信息（**仅作兜底**：jzjy 已用 Artifactory 地址、cszx 等仍按此匹配） |

## 🔄 spb-extract 融合（自动提取升级包变更内容）

脚本已集成 spb-extract 的变更内容提取能力，在填写「变更系统信息」前自动完成：

1. **定位版本项目根目录**：向上查找含 `jzjy/`、`jygl/` 子目录及 `版本地址.txt` 的目录；找不到时兜底使用 `/Volumes/Macintosh HD_Data/WorkBuddy/版本发布`。
2. **定位版本文件夹**（取最新匹配）：
   - `jzjy`：`jzjy/` 下 `SPB-V0.26.*` 或 `SPB_V2.2.19_*` 文件夹
   - `cszx`：`jygl/` 下 `CSZX-*` 文件夹
3. **调用 `upt_extract.generate()`** 提取并分类汇总，生成 `upt_content.txt` 到项目根目录。
4. **失败兜底**：若自动提取失败（未找到版本文件夹等），回退到已有 `upt_content.txt` 或静态默认配置。

> 实现：`eoa_subversion_release.py` 新增 `locate_project_root()` 与 `auto_extract_upt_content(mode, project_root)` 两个函数，在 `[18.55]` 变更系统信息步骤前调用。依赖 `~/.workbuddy/skills/spb-extract/scripts/upt_extract.py`。

## 🗜 Artifactory 融合（自动下载编号最大的 JZJY 版本压缩包）

当用户输入 `/upt_order jzjy <8位日期>`（如 `/upt_order jzjy 20261106`）时，脚本自动从 Artifactory 制品库下载版压缩包：

1. **触发条件**：`jzjy` 模式且搜索关键词含 8 位日期（正则 `20\d{6}`）。
2. **下载时机提前**：下载动作在 **[9.5] 版本地址填写之前**执行，使「版本地址」字段可复用压缩包地址（用户要求：版本地址 = 压缩包地址，不再从 `版本地址.txt` / 配置文件读取云盘链接）。
3. **远程列目录**：调用 storage API `GET {base_url}/api/storage/{repo}/{日期}/` 列出该日期目录下的压缩包。
4. **选包规则**：按文件名末尾 `-(\d+)\.zip` 的编号取**最大**（如 `SPB-V0.26.11.6-05.zip` > `-03.zip`）；无编号后缀的 zip 排最末。
5. **下载解压**：下载到 `jzjy/` 目录，解压为同名文件夹（如 `jzjy/SPB-V0.26.11.6-05/`）；若唯一顶层子目录包含 lbm/table/init/proc/dll 等关键目录则自动提升该子目录为版本目录。
6. **清理旧包**：下载成功后自动清理 `jzjy/` 下**同基础版本号但编号更小**的旧压缩包及解压目录，只保留本次（如删除 `SPB-V0.26.11.6-05.zip` 与 `SPB-V0.26.11.6-05/`，仅保留 `-06`）。通过去掉末尾 `-NN` 序号后缀匹配基础版本号，`.xlsx` 等非压缩包/目录文件不受影响。
7. **版本地址**：下载成功后，`版本地址` 字段直接填入压缩包完整 URL（`{base_url}/{repo}/{日期}/{zip名}`），跳过 `版本地址.txt` 匹配。
8. **提取内容**：解压目录显式传给 `auto_extract_upt_content(version_dir=...)`，生成 `upt_content.txt`，后续升级单填写逻辑不受影响。
9. **失败兜底**：认证失败/目录无 zip/网络不可达时打印警告并回退到本地已有版本文件夹，版本地址回退 `版本地址.txt` 匹配或默认地址。

**凭据配置**（config.json 的 `artifactory` 节点，环境变量优先）：

| 配置项 | 环境变量 | 说明 |
|--------|----------|------|
| `base_url` | - | 默认 `http://10.120.188.223:8082/artifactory` |
| `repo` | - | 默认 `jyxt-JZJYPT-generic-prod-local` |
| `username` / `password` | `ARTIFACTORY_USERNAME` / `ARTIFACTORY_PASSWORD` | Basic Auth |
| `api_token` | `ARTIFACTORY_API_TOKEN` | 优先于 Basic Auth（X-JFrog-Art-Api） |

> 实现：`eoa_subversion_release.py` 新增 `download_latest_jzjy_package(version_date, project_root)`（返回 `(success, version_dir_or_msg, dl_url)` 三元组）及辅助函数 `_load_artifactory_config()` / `_artifactory_list_dir()` / `_pick_latest_zip()`。下载逻辑在 [9.5] 前提前执行，`artifactory_zip_url` 直接作为「版本地址」字段值。Artifactory 为内网地址，**请求强制禁用系统代理**（`ProxyHandler({})`），否则会代理超时。示例：`http://10.120.188.223:8082/artifactory/jyxt-JZJYPT-generic-prod-local/20261106/SPB-V0.26.11.6-05.zip`。旧包清理由 `_jzjy_pkg_base()`（去掉末尾 `-NN` 序号得到基础版本号）与 `_cleanup_old_jzjy_packages(jzjy_dir, best)`（删除同基础版本号下编号更小的旧压缩包与解压目录）实现。

## 环境要求

- Python 3.14（系统 Python `/usr/local/bin/python3`）
- Playwright 已安装
- Chromium 已安装
- Chrome 浏览器（headed 模式）
- cryptography（密码解密库）
