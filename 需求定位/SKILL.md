---
name: 需求定位
description: >
  国泰海通 Fintech 平台「交易结算核心系统需求集合」大宽表定位工具。
  在大宽表搜索框输入需求编号，筛选结果，浏览器保持打开供人工查看。
  触发词：需求定位、定位需求、查找需求、R<编号>、PG<编号>。
---

# 需求定位

## 功能

打开交易结算核心系统需求集合大宽表，搜索指定需求编号，筛选结果，
浏览器保持打开，由用户手动查看。

## 用法

```
.venv/bin/python scripts/edit_schedule.py <需求编号>
```

参数：
- `需求编号`：支持 R+年月日+序号（R2604020071）、PG+年月+序号（PG202204-0155）等格式

示例：
```
cd /Volumes/Macintosh\ HD_Data/WorkBuddy/需求管理
.venv/bin/python ~/.workbuddy/skills/需求定位/scripts/edit_schedule.py PG202204-0155
```

## 执行流程

| 步骤 | 说明 | 耗时 |
|------|------|------|
| 登录检测 | commit 模式（~0.6s），Session 复用 | ~0.6s |
| 等数据就绪 | AG Grid 渲染 2 万+ 行数据（硬地板） | ~14-16s |
| 一键展开 | 展开所有分组行 | ~1s |
| 搜索过滤 | fill() 填入 → Quick Filter 过滤 | ~3-4s |
| 高亮定位 | 红色边框标注需求编号单元格 | <0.1s |
| 人工 | 浏览器保持打开，用户手动查看 | — |

**总耗时 ~20s**，其中 ~16s 为 AG Grid 服务端数据加载，脚本无法优化。

## 性能分析

| 方案 | 耗时 | 结论 |
|------|------|------|
| v1（原始） | 25.3s | `sleep(4.5s)` + `type(delay)` |
| v2（polling + fill） | 20.9s | 固定 sleep → 轮询；type → fill |
| v3（提前 fill） | 21.5s | ❌ 搜索框 DOM 早出现，但过滤引擎需数据模型就绪 |
| v4（URL 预过滤） | 16.1s | ❌ 平台不解析 `quickFilter` URL 参数 |
| v2 | **20.9s** | ✅ 最优方案，代码内已无冗余等待 |

## 关键选择器

- 搜索框：`#filter-text-box`
- 分组展开按钮：`button` 文本「一键展开」
- 数据行：`.ag-row.ag-row-level-2`
- 状态栏：`.ag-status-bar`

## 注意事项

- AG Grid Quick Filter 约 7 秒自动清空，搜索结果在此窗口内有效
- 浏览器始终以 headed 模式启动，查看完成后手动关闭
