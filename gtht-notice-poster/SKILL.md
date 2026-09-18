---
name: gtht-notice-poster
description: 证券/金融IT系统改造与新规通知宣介长图海报制作技能。根据用户输入的内容或文档，提取核心结构并渲染为符合国泰君安/国泰海通高端科技蓝风格的高保真HTML长图海报，并自动导出高分辨率PNG图片。触发词：宣介长图、新规长图、IT改造长图、证券长图、金融长图海报、制作长图、生成长图海报、gtht-notice-poster、notice-poster。
disable: false
---


# 证券/金融 IT 宣介长图海报制作技能 (Securities Notice Poster Skill) V2

本技能定义了证券金融行业（国泰君安/国泰海通风格）IT新规宣贯、系统改造通知、业务上线提醒等场景的高端科技蓝长图海报视觉规范、1:1 复刻级 Header 标头与 HTML/CSS 自动化渲染工作流。

> **V2 版本对齐说明**：本版已按 2026-09 实拍样张（《上交所新竞价新综业技术调整要点》）完成全组件 1:1 对齐，新增：独立一级栏目条、带图标 Chip 的二级渐变头模块卡、悬挂缩进编号列表、黄色注意提示框、新旧系统对比表格、红色行内强调、灰色脚注、深蓝 Footer 通栏。

---

## 一、 技能使用方法 (Usage Guide)

### 1. 触发方式与交互指令

当用户在对话框中提及以下触发词或提出长图制作需求时触发本技能：

- **触发词**：`宣介长图`、`新规长图`、`IT改造长图`、`证券长图`、`金融长图海报`、`制作长图`、`生成长图海报`、`gtht-notice-poster`
- **典型指令示例**：
  - *"根据史诗编号 PG202204-0260 制作宣介长图"*
  - *"将以下新规总结生成金融 IT 宣介海报"*
  - *"使用 gtht-notice-poster 技能制作长图"*

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

1. **Step 1：内容提取与清洗（按"三级内容结构"解构）**
   - **一级栏目（深蓝独立栏目条）**：按语义归纳为 2~4 个大栏目，典型划分：`涉及改造系统` → `市场交互变动` → `技术实施建议`（或 `规则核心变化` / `核心改造要点` 等）。
   - **二级模块（渐变头+图标 Chip 模块卡）**：每个一级栏目下挂 1~N 个模块卡，标题编号 `（一）（二）（三）……`，配语义化图标（🛡 权限/网关、📄 文件/接口、➕ 字段/新增、📊 行情/数据、❕ 下线/风险、ℹ️ 建议、🏢 公司系统）。
   - **三级要点（悬挂缩进编号列表）**：`N. + 加粗要点短语： + 说明文字`，说明中可用蓝色/红色行内强调。
   - 提取业务/工程主标题与正式实施日期（大红字）。
   - 梳理涉及的系统列表，采用自然段落描述 + 灰色脚注补充。
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
python3 /Users/wujin/.workbuddy/skills/gtht-notice-poster/scripts/render_poster.py <html文件路径> [输出png路径]

# 示例
python3 /Users/wujin/.workbuddy/skills/gtht-notice-poster/scripts/render_poster.py notice_poster.html notice_poster.png
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
| **系统呈现规则** | 自然段落结构 (`.paragraph-text`) | 采用"*主要涉及后台系统：低延时交易系统、集中交易系统……*"，重点系统**加粗深蓝字** (`<strong>` `#1B5FC0`)；段末可追加灰色脚注 `* 以上为主要涉及改造系统，其余相关系统按分工推进实施。` |
| **画布背景渐变** | `linear-gradient(180deg, #09378C 0%, #1355CA 40%, #0A3993 100%)` | 全图背景底色，呈现高质感深邃海蓝 |
| **高光 Tag (Header，可选)**| `#FFC000` | 顶部"高能要点"胶囊背景，**文字为纯黑加粗** (`#000000`)；无强营销诉求时可省略 |
| **重磅提醒大红字** | `#E60012` | "新竞价 + 新综业 同步上线"、"（2026年9月21日正式实施）"等核心上线动作与落标日期 |
| **主卡片背景色** | `#FFFFFF` | 一级与二级白底圆角卡片，阴影 `0 8px 20px rgba(0,20,60,0.18)` |
| **嵌套子卡片 (Nested)**| `#EEF4FD` | 复杂模块内的子板块浅灰蓝底框 |
| **参数/代码框** | `#FFFFFF` (带边框 `#D3E2F8`) | 内部代码、字典明细、接口文件名等配置参数卡片 |

### 3. 内容组件规范 (V2 核心组件，1:1 对齐样张)

| 组件 | 类名 | 样式要点 | 使用场景 |
| :--- | :--- | :--- | :--- |
| **一级栏目条** | `.section-banner` | 独立通栏渐变条 `linear-gradient(135deg, #1B4C9B 0%, #2E6EC9 100%)`，圆角 12px，高约 56px，白字 20px/800 居中 | "市场交互变动"、"技术实施建议"等章节分隔 |
| **二级模块卡** | `.subsection-card` + `.subsection-header` | 白卡圆角 14px；头部为**与卡片同宽的渐变条** `linear-gradient(135deg, #3B84DE 0%, #1E56B8 100%)`（仅上圆角 14px），内含 **40×40 图标 Chip**（`rgba(255,255,255,0.22)` 圆角 10px 白色图标）+ 白色标题 19px/800 左对齐 | "（一）网关与权限管理"、"（三）交易网关接口字段重要变化" |
| **悬挂缩进编号列表** | `.list-item` (flex) | 序号 `.num` 蓝色 `#1B5FC0` 加粗固定宽；`<b>` 要点短语纯黑加粗 + "："；`<strong>` 行内强调深蓝 `#1450A0`；`.red` 红色 `#E60012` 加粗（日期/已上线标记）；正文 15px/1.85 `#333`，换行自动对齐序号 | 模块卡内要点罗列 |
| **子项列表** | `.sub-item` | `(1)` 蓝色加粗前缀 + 内容；接口文件名等参数可用加粗或白底参数框 | 过户接口文件、枚举明细 |
| **注意提示框** | `.notice-box` | 米黄底 `#FFF7E0`，**左侧 5px 橙色竖线** `#F5A623`，圆角 8px；"注意："橙红 `#D35400` 加粗，正文暗红 `#B03A2E` | 生效时间、风险提示、例外说明 |
| **新旧对比表** | `.vs-table` | 两列等宽；表头左格浅橙底 `#FBE9DC` + 橙字 `#C05621` 加粗，右格浅蓝底 `#D6E4F7` + 深蓝字 `#1F4E9C` 加粗；左列表体白底，右列表体浅蓝 `#EFF5FC`；边框 `#E3E9F2`，单元格 padding 12px 14px | "原竞价系统 vs 新竞价系统"类迁移/差异说明 |
| **深蓝 Footer 通栏** | `.footer-bar` | 深海军蓝 `#0A2F66` 通栏（无圆角、无外边距），白字 13px 居中 1 行，padding 18px | 页尾免责/口径声明，如"以上内容供内部参考，具体业务规则以上交所及公司正式制度文件为准。" |

---

## 三、 标准 1:1 高保真 HTML/CSS 模板

制作长图海报时，使用以下完全对齐样张 Header 与全部内容组件规范的 HTML 骨架：

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
    .poster-container { width: 800px; display: flex; flex-direction: column; min-height: 100vh; }

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
    .header-section { text-align: center; padding: 34px 28px 24px 28px; }
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
    .main-title { color: #FFFFFF; font-size: 36px; font-weight: 900; letter-spacing: 1px; line-height: 1.35; margin-bottom: 12px; }
    .sub-title { color: rgba(255, 255, 255, 0.88); font-size: 15px; letter-spacing: 1px; }

    .content-padding { padding: 0 40px; }

    /* 通用白底卡片 */
    .card {
      background: #FFFFFF;
      border-radius: 14px;
      padding: 22px 26px;
      margin-bottom: 24px;
      box-shadow: 0 8px 20px rgba(0, 20, 60, 0.18);
    }

    /* 2. 重磅发布卡片 (四行结构，居中) */
    .alert-card { text-align: center; padding: 30px 20px 28px 20px; }
    .alert-card .alert-title { font-size: 32px; font-weight: 900; color: #0B378E; letter-spacing: 2px; margin-bottom: 12px; }
    .alert-card .alert-sub { font-size: 23px; font-weight: 800; color: #0B378E; margin-bottom: 12px; }
    .alert-card .alert-action { font-size: 24px; font-weight: 900; color: #E60012; letter-spacing: 1px; margin-bottom: 8px; }
    .alert-card .alert-date { color: #E60012; font-size: 17px; font-weight: 800; letter-spacing: 1px; }

    /* 3. 一级栏目条 (独立通栏深蓝渐变) */
    .section-banner {
      background: linear-gradient(135deg, #1B4C9B 0%, #2E6EC9 100%);
      color: #FFFFFF;
      font-size: 20px;
      font-weight: 800;
      text-align: center;
      padding: 15px 20px;
      border-radius: 12px;
      margin-bottom: 24px;
      box-shadow: 0 5px 12px rgba(0,10,40,0.25);
      letter-spacing: 2px;
    }

    /* 段落与脚注 */
    .paragraph-text { font-size: 15px; line-height: 1.85; color: #333333; }
    .paragraph-text strong { color: #1B5FC0; font-weight: 800; }
    .footnote { font-size: 12.5px; color: #8A8A8A; margin-top: 12px; line-height: 1.6; }

    /* 4. 二级模块卡 (渐变头 + 图标 Chip，头部与卡片一体) */
    .subsection-card {
      background: #FFFFFF;
      border-radius: 14px;
      margin-bottom: 24px;
      overflow: hidden;
      box-shadow: 0 6px 18px rgba(0, 20, 60, 0.18);
    }
    .subsection-header {
      background: linear-gradient(135deg, #3B84DE 0%, #1E56B8 100%);
      color: #FFFFFF;
      padding: 12px 20px;
      font-size: 19px;
      font-weight: 800;
      display: flex;
      align-items: center;
      gap: 14px;
      letter-spacing: 1px;
    }
    .icon-chip {
      width: 40px; height: 40px; flex-shrink: 0;
      background: rgba(255, 255, 255, 0.22);
      border-radius: 10px;
      display: flex; align-items: center; justify-content: center;
      font-size: 20px;
    }
    .subsection-body { padding: 22px 26px; }

    /* 5. 悬挂缩进编号列表 (序号蓝粗 / 要点黑粗 / 强调蓝 / 红色高亮) */
    .list-item { display: flex; gap: 6px; font-size: 15px; line-height: 1.85; margin-bottom: 12px; }
    .list-item:last-child { margin-bottom: 0; }
    .list-item .num { color: #1B5FC0; font-weight: 800; flex-shrink: 0; }
    .list-item .body { flex: 1; color: #333333; }
    .list-item .body b { color: #1A1A1A; font-weight: 800; }        /* 要点短语 */
    .list-item .body strong { color: #1450A0; font-weight: 800; }   /* 行内深蓝强调 */
    .list-item .body .red { color: #E60012; font-weight: 800; }     /* 红色高亮: 日期/已上线 */

    /* 子项列表 (1)(2)(3) */
    .sub-item { display: flex; gap: 6px; font-size: 14.5px; line-height: 1.8; margin: 8px 0 8px 26px; }
    .sub-item .num { color: #1B5FC0; font-weight: 800; flex-shrink: 0; }
    .sub-item .body { flex: 1; color: #333333; }
    .sub-item .body b { color: #1B5FC0; font-weight: 800; }

    /* 6. 注意提示框 (米黄底 + 橙色左竖线) */
    .notice-box {
      background: #FFF7E0;
      border-left: 5px solid #F5A623;
      border-radius: 8px;
      padding: 13px 16px;
      margin-top: 14px;
      font-size: 14px;
      line-height: 1.75;
      color: #B03A2E;
    }
    .notice-box .notice-label { color: #D35400; font-weight: 800; }

    /* 7. 新旧对比表格 (左橙右蓝) */
    .vs-table { width: 100%; border-collapse: collapse; margin: 6px 0; }
    .vs-table th, .vs-table td {
      border: 1px solid #E3E9F2;
      padding: 12px 14px;
      font-size: 14px;
      line-height: 1.7;
      text-align: left;
      vertical-align: top;
      width: 50%;
    }
    .vs-table th { font-weight: 800; text-align: center; font-size: 15px; }
    .vs-table th.col-old { background: #FBE9DC; color: #C05621; }
    .vs-table th.col-new { background: #D6E4F7; color: #1F4E9C; }
    .vs-table td.col-old { background: #FFFFFF; color: #333333; }
    .vs-table td.col-new { background: #EFF5FC; color: #333333; }

    /* 8. 深蓝 Footer 通栏 (贴底) */
    .footer-bar {
      margin-top: auto;
      background: #0A2F66;
      color: rgba(255, 255, 255, 0.88);
      text-align: center;
      font-size: 13px;
      letter-spacing: 0.5px;
      padding: 18px 28px;
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
      <h1 class="main-title">上交所新竞价新综业<br>技术调整要点</h1>
      <p class="sub-title">市场交互变动 · 市场重点关注 · 技术实施建议</p>
    </div>

    <div class="content-padding">
      <!-- 重磅发布卡片：四行结构 -->
      <div class="card alert-card">
        <div class="alert-title">重磅发布</div>
        <div class="alert-sub">新一代交易系统技术调整</div>
        <div class="alert-action">新竞价 + 新综业 同步上线</div>
        <div class="alert-date">（2026年9月21日正式实施）</div>
      </div>

      <!-- 一级栏目一：涉及改造系统 -->
      <div class="section-banner">涉及改造系统</div>
      <div class="card">
        <div class="paragraph-text">
          主要涉及后台系统：<strong>低延时交易系统</strong>、<strong>集中交易系统</strong>、<strong>自营系统</strong>、<strong>生态柜台</strong>、<strong>QFII 系统</strong>。
        </div>
        <div class="footnote">* 以上为主要涉及改造系统，其余相关系统按分工推进实施。</div>
      </div>

      <!-- 一级栏目二：市场交互变动 -->
      <div class="section-banner">市场交互变动</div>

      <div class="subsection-card">
        <div class="subsection-header"><span class="icon-chip">🛡</span>（一）网关与权限管理</div>
        <div class="subsection-body">
          <div class="list-item"><span class="num">1.</span><span class="body"><b>停用/注销 PBU 不再支持登录交易网关</b>，不支持新订单申报、撤单申报及订阅/被订阅</span></div>
          <div class="list-item"><span class="num">2.</span><span class="body"><b>PBU 口令更新时效性调整：</b>通过交易网关实时更新 PBU 口令后，竞价平台订阅该 PBU 时的口令<strong>实时同步生效</strong>（原次日生效）</span></div>
          <div class="list-item"><span class="num">3.</span><span class="body"><b>新过户接口：</b>新竞价取消老过户接口 ghXXXXXX.dbf，新增三个新过户接口 <span class="red">（9.7 已上线）</span></span></div>
          <div class="sub-item"><span class="num">(1)</span><span class="body"><b>新竞价过户数据文件</b> — gh00PXXXXXX_YYYMMDD.txt</span></div>
          <div class="sub-item"><span class="num">(2)</span><span class="body"><b>新竞价发行过户数据文件</b> — ipogh00PXXXXXX_YYYMMDD.txt</span></div>
          <div class="notice-box"><span class="notice-label">注意：</span>CPXX 文件相关变动于上线后 T+1 日起正式生效，其他变动于 T 日起生效。</div>
        </div>
      </div>

      <div class="subsection-card">
        <div class="subsection-header"><span class="icon-chip">➕</span>（二）交易网关接口字段重要变化</div>
        <div class="subsection-body">
          <table class="vs-table">
            <tr><th class="col-old">原竞价系统</th><th class="col-new">新竞价系统</th></tr>
            <tr><td class="col-old">业务类型与执行报告分区有固定对应关系</td><td class="col-new">执行报告分区取消固定取值，通过 TDGW 的 ExecRptInfo 每日获取</td></tr>
            <tr><td class="col-old">申报数量 OrderQty 取值小于 10 亿</td><td class="col-new">取消 10 亿取值限制，满足接口协议长度和业务规则即可</td></tr>
          </table>
        </div>
      </div>

      <!-- 一级栏目三：技术实施建议 -->
      <div class="section-banner">技术实施建议</div>

      <div class="subsection-card">
        <div class="subsection-header"><span class="icon-chip">ℹ️</span>（三）关键实施建议</div>
        <div class="subsection-body">
          <div class="list-item"><span class="num">1.</span><span class="body"><b>带宽扩容：</b>新竞价相比现有生产竞价系统的系统性能有显著提升，建议结合自身实际使用的流速权数按需扩容</span></div>
          <div class="list-item"><span class="num">2.</span><span class="body"><b>字符串规范：</b>申报接口字符串字段仅允许数字、大小写字母、空格，严禁特殊字符</span></div>
        </div>
      </div>
    </div>

    <!-- 深蓝 Footer 通栏 -->
    <div class="footer-bar">以上内容供内部参考，具体业务规则以上交所及公司正式制度文件为准。</div>
  </div>
</body>
</html>
```

### 填充要点提醒 (V2)

- **图标 Chip 图标语义表**：🛡 网关/权限 ｜ 📄 文件/接口调整 ｜ ➕ 字段新增/变化 ｜ 📊 行情/数据 ｜ ❕ 系统下线/风险 ｜ ℹ️ 实施建议 ｜ 🏢 公司相关系统。
- **列表写作范式**：`N. <b>要点短语：</b>说明文字`，说明中的关键结论用 `<strong>`（深蓝）、日期/上线标记用 `<span class="red">`；每条要点独立成段，禁止整段流水账。
- **新旧对比场景**（老系统→新系统、原规则→新规则、存量→增量）**必须使用 `.vs-table`**，左列"原"、右列"新"。
- **生效时间/例外/风险** 必须用 `.notice-box` 单独框出，不混入正文列表。
- `.poster-container` 使用 `min-height: 100vh + margin-top: auto` 保证深蓝 Footer 永远贴底通栏。
