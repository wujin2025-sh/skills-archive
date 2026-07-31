---
name: req-schedule-edit
description: |
  国泰海通金融科技平台需求排期修改工具。根据需求编号与目标排期日期，自动打开需求详情页，点击右上角“修改排期”按钮，在“需求排期确认”弹窗中更新「需求预计交付验收时间」和「需求预计上线时间」并提交保存。支持 8 位纯数字日期 (20260821) 或标准日期格式 (2026-08-21)，自动支持 Session 复用与 Headless/Headed 双模式。
  触发词：修改排期、需求排期修改、修改需求排期、需求排期确认、排期修改、R2607150083 20260821。
agent_created: true
---

# 需求排期修改技能 (req-schedule-edit)

## 概述

访问国泰海通金融科技平台需求详情页 (`https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId={demand_id}&templateId=8888&flag=1`)，自动点击页面右上角的 **修改排期** 按钮，在弹出的 **需求排期确认** 对话框中，填入新的 **需求预计交付验收时间** 及 **需求预计上线时间**，完成排期确认并提交落库。

支持 Session 免登录态复用，且自动兼容 `20260821` (8位纯数字) 或 `2026-08-21` / `2026/08/21` 日期输入。

---

## 触发条件

当用户在对话或指令中涉及以下内容时触发本技能：

- **修改排期**、**需求排期修改**、**修改需求排期**
- **需求排期确认**、**排期修改**
- 需求编号 + 8位数字/标准日期格式，例如：
  - `R2607150083 20260821`
  - `修改排期 R2607150083 20260821`
  - `帮我把需求 R2606160105 的排期修改为 2026-08-21`

---

## 使用方法

脚本路径位于 `scripts/edit_req_schedule.py`，可以在虚拟环境中通过 CLI 直接调用：

```bash
# 1. 标准单笔修改模式 (自动转化 20260821 -> 2026-08-21)
.venv/bin/python /Users/wujin/.workbuddy/skills/req-schedule-edit/scripts/edit_req_schedule.py R2607150083 20260821

# 2. 分别指定交付验收时间与上线时间
.venv/bin/python /Users/wujin/.workbuddy/skills/req-schedule-edit/scripts/edit_req_schedule.py R2607150083 2026-08-21 2026-08-24

# 3. 可视化调试模式 (开启 Headed 浏览器观察 UI 操作)
.venv/bin/python /Users/wujin/.workbuddy/skills/req-schedule-edit/scripts/edit_req_schedule.py R2607150083 20260821 --headed
```

---

## 参数说明

| 参数名 | 必填 | 格式/示例 | 说明 |
| :--- | :---: | :--- | :--- |
| `demand_id` | **是** | `R2607150083` | 目标需求编号 |
| `target_date` | **是** | `20260821` 或 `2026-08-21` | 目标「需求预计交付验收时间」 |
| `online_date` | 否 | `2026-08-24` | 目标「需求预计上线时间」(未传时默认与交付验收时间一致) |
| `--headed` | 否 | N/A | 显示 Playwright 浏览器界面 |

---

## 核心技术与工作流

1. **Session 复用与免密认证**：自动加载 `.fintech_session.json`，在失效时自动补全登录流程 (`USERNAME: 125360`) 并持久化 StorageState。
2. **DOM 动态交互**：
   - 唤醒详情页 Top-Right 工具栏中的 `.ant-btn:has-text("修改排期")`。
   - 捕捉并定位渲染在顶层的 `.ant-modal-content` (`需求排期确认`)。
3. **Datepicker 属性解锁与键盘触发**：
   - 移去输入框的 `readonly` 约束属性。
   - **修改顺序控制**：必须**优先修改「需求预计上线时间」**，再修改**「需求预计交付验收时间」**（若先改验收时间，可能触发平台自动根据 +10 工作日重置上线时间或锁定可选区间）。
   - 模拟真实的全选 (`Meta+A` / `Ctrl+A`) 与字符流打字 (`type`)，选择并确认日历单元格，触发 React / Ant Design `onChange` 与状态绑定。
4. **接口交互与校验落库**：
   - 收起悬浮遮罩后触发提交按钮，推送后端更新接口 `/api/demand-service/demand/audit/updateLaunchTimeByDemandId`。
   - 自动刷新页面 (`page.reload()`) 进行数据库落库验证。
   - 自动截屏存盘为 `schedule_{demand_id}_{date}.png` 作为操作留痕凭证。
