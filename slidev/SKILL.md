---
name: slidev
description: 使用基于 Markdown、Vue 组件、代码高亮、动画与交互功能的 Slidev，为开发者创建和演示网页版幻灯片（Slidedecks）。在制作技术汇报、会议演讲、代码讲解、教学材料或开发者演示文稿时使用。
---

# Slidev - 开发者专属幻灯片系统

基于 Vite、Vue 和 Markdown 构建的现代网页版演示文稿制作工具。

## 1. 适用场景

- 包含实时/可执行代码示例的技术演示或幻灯片
- 带有动画控制的语法高亮代码片段
- 交互式 Demo 演示（Monaco 编辑器、可运行代码）
- 数学公式（LaTeX）或图表（Mermaid、PlantUML）
- 带有演讲者备注的演示录制
- 导出为 PDF、PPTX 或作为 SPA 网页进行部署托管
- 开发者演讲或 Workshop 研讨会中的代码演练讲解

## 2. 快速上手

```bash
pnpm create slidev    # 创建新项目
pnpm run dev          # 启动开发服务器 (自动打开 http://localhost:3030)
pnpm run build        # 构建静态 SPA 网页
pnpm run export       # 导出为 PDF (需要安装 playwright-chromium)
```

**验证方法**：运行 `pnpm run dev` 后，确认页面在 `http://localhost:3030` 正常加载；运行 `pnpm run export` 后，确认项目根目录下生成了导出的 PDF 文件。

## 3. 基本语法

```md
---
theme: default
title: 我的演示文稿
---

# 第一张幻灯片

这里是页面内容

---

# 第二张幻灯片

更多内容

<!--
这里是演讲者备注（Presenter Notes）
-->
```

- 使用 `---` 分隔不同的幻灯片
- 顶部的第一个 frontmatter 为全局配置（Headmatter）
- HTML 注释 `<!-- -->` 作为演讲者备注

## 4. 核心功能速查与参考

### 代码与编辑器

| 功能 | 用法 |
|---------|-------|
| 行高亮 | `` ```ts {2,3} `` |
| 点击逐步高亮 | `` ```ts {1\|2-3\|all} `` |
| 显示行号 | `lineNumbers: true` 或 `{lines:true}` |
| 可滚动代码块 | `{maxHeight:'100px'}` |
| 代码页签选项卡 | `::code-group` (需要开启 `comark: true`) |
| Monaco 编辑器 | `` ```ts {monaco} `` |
| 运行代码 | `` ```ts {monaco-run} `` |
| 引入并编辑文件 | `<<< ./file.ts {monaco-write}` |
| 代码平滑动画 | `` ````md magic-move `` |
| TypeScript 类型提示 | `` ```ts twoslash `` |
| 导入代码片段 | `<<< @/snippets/file.js` |

### 图表与数学公式

| 功能 | 用法 |
|---------|-------|
| Mermaid 图表 | `` ```mermaid `` |
| PlantUML 图表 | `` ```plantuml `` |
| LaTeX 数学公式 | `$行内公式$` 或 `$$块级公式$$` |

### 布局与样式

| 功能 | 用法 |
|---------|-------|
| 画布尺寸 | `canvasWidth`, `aspectRatio` |
| 幻灯片缩放 | `zoom: 0.8` |
| 元素缩放 | `<Transform :scale="0.5">` |
| 布局插槽 | `::right::`, `::default::` |
| Scoped 局部 CSS | 在幻灯片中使用 `<style>` |
| 全局图层 | `global-top.vue`, `global-bottom.vue` |
| 可拖拽元素 | `v-drag`, `<v-drag>` |
| 图标库 | `<mdi-icon-name />` |

### 动画与交互

| 功能 | 用法 |
|---------|-------|
| 点击逐步显现动画 | `v-click`, `<v-clicks>` |
| 手绘标注 (Rough) | `v-mark.underline`, `v-mark.circle` |
| 涂鸦/画笔模式 | 按 `C` 键或配置 `drawings:` |
| 动画方向样式 | `forward:delay-300` |
| 备注高亮联动 | 备注中使用 `[click]` |

### 导出与构建

- **导出导出命令**：`slidev export`（导出为 PDF/PPTX/PNG）
- **构建部署**：`slidev build`
- **导出前提依赖**：导出 PDF/PPTX/PNG 需要在项目中安装 `pnpm add -D playwright-chromium`。如果导出报错，请先安装该依赖。

## 5. 常用预置布局 (Layouts)

| 布局名称 | 适用用途 |
|--------|---------|
| `cover` | 标题/封面页 |
| `center` | 内容居中页 |
| `default` | 标准幻灯片页 |
| `two-cols` | 双栏左右分栏（配合 `::right::` 使用） |
| `two-cols-header` | 顶部标题 + 双栏分栏 |
| `image` / `image-left` / `image-right` | 单图/左图/右图布局 |
| `iframe` / `iframe-left` / `iframe-right` | 嵌入外链网页布局 |
| `quote` | 金句引用页 |
| `section` | 章节分隔页 |
| `fact` / `statement` | 数据/关键声明展示页 |
| `intro` / `end` | 开场介绍 / 结束尾页 |

## 6. 相关资源链接

- 官方文档: https://sli.dev
- 主题画廊 (Theme Gallery): https://sli.dev/resources/theme-gallery
- 案例展示 (Showcases): https://sli.dev/resources/showcases
