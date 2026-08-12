---
name: securities-notice-poster
description: 证券/金融IT系统改造与新规通知宣介长图海报制作技能。根据用户输入的内容或文档，提取核心结构并渲染为符合国泰君安/国泰海通高端科技蓝风格的高保真HTML长图海报，并自动导出高分辨率PNG图片。触发词：宣介长图、新规长图、IT改造长图、证券长图、金融长图海报、制作长图、生成长图海报、securities-notice-poster、notice-poster。
---

# 证券/金融 IT 宣介长图海报制作技能 (Securities Notice Poster Skill)

本技能定义了证券金融行业（国泰君安/国泰海通风格）IT新规宣贯、系统改造通知、业务上线提醒等场景的高端科技蓝长图海报视觉规范、1:1 复刻级 Header 标头与 HTML/CSS 自动化渲染工作流。

---

## 一、 技能使用方法 (Usage Guide)

### 1. 触发方式与交互指令

当用户在对话框中提及以下触发词或提出长图制作需求时触发本技能：

- **触发词**：`宣介长图`、`新规长图`、`IT改造长图`、`证券长图`、`金融长图海报`、`制作长图`、`生成长图海报`、`securities-notice-poster`
- **典型指令示例**：
  - *“根据史诗编号 PG202204-0260 制作宣介长图”*
  - *“将以下新规总结生成金融 IT 宣介海报”*
  - *“使用 securities-notice-poster 技能制作长图”*

---

### 2. 标准工作流程 (Standard Workflow)

```
┌──────────────────────────────────────────────────────────┐
│ Step 1: 内容提取与解构 (自动归纳分类，隐藏 R26xx 需求单号) │
├──────────────────────────────────────────────────────────┤
│ Step 2: 填充 HTML 骨架 (运用 1:1 品牌Header与设计 Token)  │
├──────────────────────────────────────────────────────────┤
│ Step 3: 自动化 PNG 导出 (调用 Headless Chromium 截取长图) │
├──────────────────────────────────────────────────────────┤
│ Step 4: 结果呈现 (提供 Markdown 嵌入图片与 HTML 源码)     │
└──────────────────────────────────────────────────────────┘
```

1. **Step 1：内容提取与清洗**
   - 提取业务/工程主标题、重磅提醒落标日期（大红字）。
   - 梳理涉及的系统列表，采用自然段落描述呈现。
   - 归纳核心改造要点，**自动隐去内部 `R26xxxxxx` 需求单号**，保持简洁纯粹的业务描述。
2. **Step 2：生成 HTML 页面**
   - 按照下面的【三、标准 1:1 高保真 HTML/CSS 模板】拼装填充，保存为本地 `.html` 文件。
3. **Step 3：运行截图工具导出 PNG**
   - 调用 Python 渲染脚本生成 2x Retina 高清长图 PNG。
4. **Step 4：输出汇报**
   - 在对话框中提供生成的 PNG 图片嵌入展示与 HTML/PNG 文件超链接。

---

### 3. 命令行手动运行 (CLI Usage)

若需在终端中直接将已写好的 HTML 转换为 PNG 长图海报，可执行：

```bash
# 基本用法
python3 /Users/wujin/.workbuddy/skills/securities-notice-poster/scripts/render_poster.py <html文件路径> [输出png路径]

# 示例
python3 /Users/wujin/.workbuddy/skills/securities-notice-poster/scripts/render_poster.py notice_poster.html notice_poster.png
```

---

## 二、 视觉设计规范体系 (Design Tokens & Aesthetics)

### 1. 顶部 Header 品牌栏标准 (1:1 复刻规范)

| 元素组件 | 样式与 DOM 规范 | 效果描述 |
| :--- | :--- | :--- |
| **品牌 Icon 矢量** | `<svg>` 蓝色切面菱形矢量 (`#0052CC` / `#003399` / `#52B2FF`) | 国泰海通几何图形 Logo |
| **中文品牌名** | `font-size: 19px; font-weight: 900; color: #003399;` | **国泰海通证券** |
| **英文品牌名** | `font-size: 8px; font-weight: 700; color: #555555;` | `GUOTAI HAITONG SECURITIES` |
| **竖分割线** | `width: 1px; height: 24px; background: #B0C8E8;` | 细竖线分割 |
| **部门与小组落款** | `font-size: 15px; font-weight: 800; color: #0052CC;` | **技术研发部 · 交易结算业务创新组** |
| **顶栏容器底边** | `background: #FFFFFF; height: 64px; border-bottom: 2px solid #0052CC;` | 纯白顶栏+蓝底边线 |

### 2. 核心颜色与文案呈现规则

| 规则维度 | 规范描述 | 应用指导 |
| :--- | :--- | :--- |
| **需求编号展示规则** | **隐藏内部需求单号** (如隐藏 `R26xxxxxx`) | 海报正文与改造要点中**默认不显示具体需求单号**，直接呈现干净、地道的业务与技术描述，保持海报美观高端。 |
| **系统呈现规则** | 自然段落结构 (`.paragraph-text`) | 避免杂乱的气泡按钮，采用“*本次改造共涉及 N 个系统，主要包括：集中交易系统、低延时交易系统……*”，重点系统**加粗深蓝字** (`<strong>` `#0052CC`)。 |
| **画布背景渐变** | `linear-gradient(180deg, #09378C 0%, #1355CA 40%, #0A3993 100%)` | 全图背景底色，呈现高质感深邃海蓝 |
| **高光 Tag (Header)**| `#FFC000` | 顶部“高能要点”胶囊背景，**文字为纯黑加粗** (`#000000`) |
| **重磅提醒大红字** | `#E60012` | “8月17日 星期一 正式实施”等核心落标实施日期 |
| **主卡片背景色** | `#FFFFFF` | 一级与二级白底圆角卡片，阴影 `0 8px 20px rgba(0,20,60,0.18)` |
| **嵌套子卡片 (Nested)**| `#EEF4FD` | 用于“交易权限管理”等复杂模块内的子板块浅灰蓝底框 |
| **参数/代码框** | `#FFFFFF` (带边框 `#D3E2F8`) | 内部代码、字典明细、配置参数卡片 |

---

## 三、 标准 1:1 高保真 HTML/CSS 模板

制作长图海报时，使用以下完全对齐原图 Header 与文案规范的 HTML 骨架：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=800, initial-scale=1.0">
  <title>宣介长图海报</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      width: 800px;
      margin: 0 auto;
      font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", "Microsoft YaHei", sans-serif;
      background: linear-gradient(180deg, #09378C 0%, #1355CA 40%, #0A3993 100%);
      color: #333;
      -webkit-font-smoothing: antialiased;
    }
    .poster-container { width: 800px; padding-bottom: 40px; }

    /* 0. 顶部 Logo 栏 (1:1 原图Header) */
    .top-logo-bar {
      background: #FFFFFF;
      height: 64px;
      padding: 0 28px;
      display: flex;
      align-items: center;
      justify-content: flex-start;
      border-bottom: 2px solid #0052CC;
    }
    .logo-left { display: flex; align-items: center; gap: 10px; }
    .logo-text-group { display: flex; flex-direction: column; }
    .zh-title { font-size: 19px; font-weight: 900; color: #003399; letter-spacing: 0.5px; line-height: 1.1; }
    .en-title {
      font-size: 8px; font-weight: 700; color: #555555; letter-spacing: 0.6px;
      font-family: Arial, sans-serif; margin-top: 2px; transform: scale(0.95); transform-origin: left center;
    }
    .divider-line { width: 1px; height: 24px; background: #B0C8E8; margin: 0 6px; }
    .dept-title { font-size: 15px; font-weight: 800; color: #0052CC; letter-spacing: 0.5px; }

    /* 1. Header 头部区 */
    .header-section { text-align: center; padding: 32px 28px 20px 28px; }
    .tag-highlight {
      display: inline-block;
      background: #FFC000;
      color: #000000;
      font-weight: 800;
      font-size: 13px;
      padding: 4px 18px;
      border-radius: 20px;
      margin-bottom: 14px;
      letter-spacing: 1px;
    }
    .main-title { color: #FFFFFF; font-size: 34px; font-weight: 900; letter-spacing: 1px; margin-bottom: 10px; }
    .sub-title { color: rgba(255, 255, 255, 0.85); font-size: 15px; letter-spacing: 1px; }

    .content-padding { padding: 0 28px; }

    /* 通用白底卡片 */
    .card {
      background: #FFFFFF;
      border-radius: 14px;
      padding: 20px 24px;
      margin-bottom: 22px;
      box-shadow: 0 8px 20px rgba(0, 20, 60, 0.18);
    }

    /* 2. 重磅提醒卡片 */
    .alert-card { text-align: center; padding: 24px 20px; }
    .alert-card .alert-title { font-size: 26px; font-weight: 900; color: #0B378E; margin-bottom: 6px; }
    .alert-card .alert-sub { font-size: 22px; font-weight: 900; color: #0B378E; margin-bottom: 12px; }
    .alert-card .alert-date { color: #E60012; font-size: 24px; font-weight: 900; letter-spacing: 1px; }

    /* 3. 一级胶囊标题条 */
    .section-badge-title {
      background: linear-gradient(90deg, #186BD9 0%, #0C4CB5 100%);
      color: #FFFFFF;
      font-size: 18px;
      font-weight: 800;
      text-align: center;
      padding: 10px 20px;
      border-radius: 8px;
      margin-bottom: 16px;
      box-shadow: 0 4px 10px rgba(0,0,0,0.15);
      letter-spacing: 1px;
    }

    /* 列表与段落 */
    .paragraph-text { font-size: 14.5px; line-height: 1.8; color: #333333; }
    .paragraph-text strong { color: #0052CC; font-weight: 700; }
    .list-item { font-size: 14.5px; line-height: 1.8; color: #333333; margin-bottom: 10px; }
    .list-item:last-child { margin-bottom: 0; }
    .list-item strong { color: #0052CC; font-weight: 700; }

    /* 二级板块 */
    .subsection-card {
      background: #FFFFFF;
      border-radius: 14px;
      padding: 20px 22px;
      margin-bottom: 18px;
      box-shadow: 0 6px 18px rgba(0, 20, 60, 0.15);
    }
    .subsection-header {
      background: linear-gradient(90deg, #1A6DD9 0%, #0E4FB8 100%);
      color: #FFFFFF;
      padding: 9px 16px;
      border-radius: 8px;
      font-size: 16.5px;
      font-weight: 800;
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 16px;
    }

    /* 内部浅灰蓝嵌套卡片 */
    .nested-card { background: #EEF4FD; border-radius: 10px; padding: 16px; margin-bottom: 14px; }
    .nested-card:last-child { margin-bottom: 0; }
    .nested-title-badge { color: #0052CC; font-size: 14.5px; font-weight: 800; margin-bottom: 10px; display: block; }
    .code-box {
      background: #FFFFFF;
      border: 1px solid #D3E2F8;
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 10px;
      font-size: 13.5px;
      line-height: 1.7;
    }
    .code-box .label { color: #0052CC; font-weight: 700; }

    /* 6. Footer 底部 */
    .footer-section {
      text-align: center;
      padding: 20px 28px 0 28px;
      color: rgba(255, 255, 255, 0.75);
      font-size: 12.5px;
      line-height: 1.6;
    }
  </style>
</head>
<body>
  <div class="poster-container">
    <div class="top-logo-bar">
      <div class="logo-left">
        <svg width="34" height="24" viewBox="0 0 90 60" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M45 0L85 30L45 60L5 30L45 0Z" fill="#0052CC"/>
          <path d="M45 0L45 60L5 30L45 0Z" fill="#003399"/>
          <path d="M45 0L65 30L45 60L45 0Z" fill="#52B2FF"/>
        </svg>
        <div class="logo-text-group">
          <div class="zh-title">国泰海通证券</div>
          <div class="en-title">GUOTAI HAITONG SECURITIES</div>
        </div>
        <div class="divider-line"></div>
        <div class="dept-title">技术研发部 · 交易结算业务创新组</div>
      </div>
    </div>

    <div class="header-section">
      <div class="tag-highlight">高能要点</div>
      <h1 class="main-title">项目/新规主标题</h1>
      <p class="sub-title">拟定核心变化 · 涉及改造系统 · 核心改造要点</p>
    </div>

    <div class="content-padding">
      <div class="card alert-card">
        <div class="alert-title">重磅提醒</div>
        <div class="alert-sub">项目/新规名称</div>
        <div class="alert-date">YYYY年MM月DD日 星期X 正式实施</div>
      </div>

      <div class="section-badge-title">规则核心变化</div>
      <div class="card">
        <div class="list-item">1. 核心变化描述一<strong>加粗强调词</strong>。</div>
        <div class="list-item">2. 核心变化描述二<strong>加粗强调词</strong>。</div>
      </div>

      <div class="section-badge-title">涉及改造系统</div>
      <div class="card">
        <div class="paragraph-text">
          本次改造共涉及 <strong>N 个系统</strong>，主要包括：<strong>系统A</strong>、<strong>系统B</strong>……
        </div>
      </div>

      <div class="section-badge-title">核心改造要点</div>

      <div class="subsection-card">
        <div class="subsection-header"><span class="icon">📊</span> (一) 子模块一</div>
        <div class="list-item">1. 纯业务与技术说明（隐藏内部需求单号）……</div>
      </div>
    </div>

    <div class="footer-section">
      <p>以上内容仅供参考，具体以系统实际上线运行发布版本为准。</p>
      <p>技术研发部 · 交易结算业务创新组 出品</p>
    </div>
  </div>
</body>
</html>
```

