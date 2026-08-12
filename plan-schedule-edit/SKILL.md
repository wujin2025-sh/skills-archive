---
name: plan-schedule-edit
description: "修改或只读查询大宽表 Story 的「计划生产排期」字段。支持单笔更新、只读查询与 Excel 批量更新模式。批量模式下可动态配置受让人过滤（默认配置或环境变量），采用分片并发模式修改并可选并发校验持久化。"
allowed-tools:
  - Bash
  - Read
  - Write
---

# 计划生产排期修改与查询技能 (plan-schedule-edit)

> [!NOTE]
> **技能定位**：本 Skill 用于根据用户指定的需求编号/史诗编号以及新的排期日期，或者解析 Excel 批量排期调整表，自动登录金融科技平台大宽表，支持**极速 API 只读查询**、**单笔排期修改**以及**多并发 Excel 批量更新**。

---

## 🎯 触发词与 3 大核心工作模式

当用户提到 “修改排期”、“查询排期”、“R2603310051 计划生产排期”、“批量更新排期”、“修改史诗排期 E2603040001” 时自动触发：

| 模式 | 触发场景/命令行参数示例 | 运行原理与性能特征 | 浏览器模式 | 耗时/性能 |
| :---: | :--- | :--- | :---: | :---: |
| **极速模式 (推荐)** | `python scripts/schedule_fast.py R2603310051 20260724 --verify` | **热缓存+WebSocket双态极速写回**：TTL 2h内热缓存匹配数据，React组件直连WebSocket写回落库 | 无头极速模式 (`Headless`) | **~ 5.2 秒** *(含写入+数据库校验)* |
| **模式 1** | `python scripts/edit_schedule.py R2603310051` | **只读查询模式**：仅传需求编号，省略日期。自动调用后端极速 API 查询排期 | 免启动浏览器 | **< 300 ms** |
| **模式 2** | `python scripts/edit_schedule.py R2603310051 20260724` | **单笔修改模式**：指定需求编号与目标日期。自动修改并更新 React 状态 drop 落库 | 无头模式 (`Headless`) | **~ 12 秒** |
| **模式 3** | `python scripts/edit_schedule.py --excel 20260710预排期.xlsx` | **Excel 批量修改模式**：自动读取 C 列 (需求号)、L 列 (拟调整排期)、Q 列 (受理人)。根据配置只更新目标受理人 (`--assignee`) 的需求 | 3 并发无头协程 (`-c 3`) | **极速分片并行** |

---

## 🔑 账号凭证配置 (`config.json` 与环境变量)

> [!IMPORTANT]
> **安全凭证配置规范**：
> - **方式一：环境变量注入 (推荐最安全)**
>   在终端中设置敏感凭据：
>   ```bash
>   export PLATFORM_USERNAME="125360"
>   export PLATFORM_PASSWORD="您的真实登录密码"
>   ```
> - **方式二：配置文件 `config.json`**
>   在技能目录或工作目录下的 `config.json` 中配置非敏感字段：
>   ```json
>   {
>     "username": "125360",
>     "password": "您的真实登录密码",
>     "platform_url": "https://fintech.gtht.com.cn",
>     "target_assignee": "吴进"
>   }
>   ```
>   *(注：`config.json` 严禁存储明文密码。若未检测到环境变量密码，系统将提示用户进行注入)*

---

## ⚙️ 核心技术亮点与安全审计保障

1. **热缓存路径 (TTL 2h 内)**：
   - 维持 `.table_cache.json` 2小时热缓存，无需全量拉取 14,000+ 条 ag-Grid 数据，直接在内存中匹配 `rowId` 与 `storyCode`。
2. **WebSocket 极速出库写回 (`schedule_fast.py`)**：
   - 跳过 ag-Grid 视图过滤与 DOM 搜索耗时，页面载入后直接通过 React Fiber 的 `sendRowData` 出库写回。
3. **HTTPS 安全加密传输**：
   - 平台接口与页面通信全量强制采用 `HTTPS` (`https://fintech.gtht.com.cn`) 加密协议传输。
4. **Playwright 自动化特征防护说明**：
   > [!NOTE]
   > 本技能使用 Playwright 模拟用户真实浏览器交互（包含注入 JS 防机制掩码以消除 `navigator.webdriver` 特征），请确保目标平台与环境符合您所在团队的自动化运维规范。
5. **Ag-Grid 列虚拟化与 DOM 节点精准唤醒**：
   - 自动利用 React Fiber 树注入 ag-Grid API (`ensureColumnVisible` + `ensureNodeVisible` + `startEditingCell`)，精准唤醒隐藏在视口外的【计划生产排期】列单元格。
6. **Ant Design DatePicker 下拉框防丢帧触发**：
   - 单元格开启编辑后自动触发 `.ant-picker` 下拉菜单，并自动点击对应日期单元格 (`select_date_in_picker`)，100% 确保 React `onChange` 状态更新并触发后端 API `POST updateRowContent` 真实落库。
7. **动态受让人过滤规则 (`--assignee`)**：
   - 支持通过 CLI 参数 `--assignee`、环境变量 `TARGET_ASSIGNEE` 或 `config.json` 中的 `target_assignee` 灵活调整授权受让人姓名（设为 `"ALL"` 时跳过姓名过滤）。
8. **macOS / Windows 全平台跨平台原生支持**：
   - **硬件设备解密**：原生兼容 macOS (`ioreg`) 与 Windows (`wmic`/`powershell` Win32_ComputerSystemProduct) 硬件 Key 解密。
   - **路径与浏览器解耦**：采用 Python `os.path` 跨平台路径拼接，Playwright 自动适配 Windows/macOS/Linux 的 Chrome/Chromium 执行句柄。
9. **标准进程退出与状态卡片清理 (`sys.exit(0)`)**：
   - 在 Playwright `await browser.close()` 关闭浏览器句柄并调用 `sys.stdout.flush()` 后，通过 `sys.exit(0)` 进行标准资源清理，确保进程干净退出。

---

## 💻 智能体命令行调用说明 (CLI Guide)

智能体在执行终端命令时，可直接通过 `python` 调用内部脚本：

```bash
# 0. 极速更新模式 (5.2s 包含 2 行写入 + 持久化校验，走 2h 内热缓存路径) [推荐]
python scripts/schedule_fast.py R2603310051 20260724 --verify

# 1. 极速只读查询模式（免启动浏览器，<300ms 返回）
python scripts/edit_schedule.py R2603310051

# 2. 单笔修改排期（默认无头模式 Headless，12s 内完成）
python scripts/edit_schedule.py R2603310051 20260724

# 3. 批量更新 Excel 排期（3 并发协程无头分片处理，指定受让人）
python scripts/edit_schedule.py --excel /path/to/20260710预排期.xlsx -c 3 --assignee 吴进

# 4. 可视化调试模式（若需人工观察页面渲染，可带 --headed）
python scripts/edit_schedule.py R2603310051 20260724 --headed
```

---

## 📂 产物与状态控制承诺

> [!CAUTION]
> **工作目录强制写回与输出**：
> - 当指定 Excel 导出或日志生成时，文件均会自动强保存在**该智能体调用的当前工作目录 (`os.getcwd()`)** 下。
> - 动态 Session 文件与缓存路径采用 `os.getcwd()` 相对解析，杜绝硬编码绝对路径。
