---
name: debrief-ppt-maker
description: 专业述职PPT制作技能。根据用户提供的工作大纲，基于默认模板自动生成完整HTML述职演示文稿。触发词：述职PPT、述职报告、工作汇报PPT、季度总结PPT、年度述职、阶段汇报、slide_edit、slide_present。
disable: false
---


# Debrief PPT Maker

本技能旨在帮助用户快速、高质量地将零散工作内容整理成结构清晰、视觉精美的述职报告PPT（HTML格式，浏览器预览）。

## 默认模板

**模板路径**：`/Volumes/Macintosh HD_Data/Gemini/PPT/模板：2026年XX季度工作述职（姓名）.pptx`

**模板规格**：
- 幻灯片尺寸：10" × 5.62"（1280×720px）
- 封面/结语 layout：slideLayout2，背景图 tpl_image4.png（国泰海通 Logo + 上海天际线深蓝底）
- 内页 layout：slideLayout3，白色背景 + 品牌页眉

## 模板配色体系（国泰海通品牌色）

| Token | 用途 | 色值 |
|-------|------|------|
| 主蓝深 | 页眉色块、深色英雄卡、标题 | `#1F497D` |
| 主蓝亮 | 按钮、卡片左边框、柱状图主色 | `#0C72BB` |
| 品牌蓝 | 分割线、图标、次级装饰 | `#4F81BD` |
| 深蓝2 | 标题文字、序号徽章 | `#004E97` |
| **战果红（新增）** | **浅底核心大数字、环比增长胶囊、正文关键成果词高亮** | **`#D9232E`（备选 `#E53935`）** |
| **五阶递进蓝（新增）** | **规划页左侧模块色块（由深至浅五阶明度递进）** | **`#133962` ➔ `#1E4E87` ➔ `#2E6BB0` ➔ `#8FA3C0` ➔ `#B8C5D6`** |
| 正文灰 | 副标题、PM元数据栏、页脚 | `#999999`（正文次级 `#666666`） |
| 背景色 | 内页底色 | `#FFFFFF` |
| 卡片底 | 内容卡片背景 | `#f5f8fc`（浅冰蓝渐变 `#eef5fc`） |

## 核心工作流

### Step 1：模板背景提取

使用 Python zipfile 从 PPTX 提取背景图到输出目录：

```python
import zipfile, os
pptx_path = '/Volumes/Macintosh HD_Data/Gemini/PPT/模板：2026年XX季度工作述职（姓名）.pptx'
out_dir   = '/Volumes/Macintosh HD_Data/Gemini/PPT/'
with zipfile.ZipFile(pptx_path, 'r') as z:
    media = [f for f in z.namelist() if f.startswith('ppt/media/') and not f.endswith('/')]
    for mf in media:
        data = z.read(mf)
        with open(out_dir + 'tpl_' + os.path.basename(mf), 'wb') as fp:
            fp.write(data)
```

关键文件：
- `tpl_image4.png` → **封面/结语背景**（国泰海通 Logo + 上海天际线）
- `tpl_image3.jpeg` → 备用建筑背景图

### Step 2：PPTX 坐标转 px

EMU 转换公式（9144000×5143500 EMU = 1280×720 px）：

```python
sw, sh = 9144000, 5143500
pw, ph = 1280, 720
def emu_to_px(x,y,cx,cy):
    return round(x*pw/sw,1),round(y*ph/sh,1),round(cx*pw/sw,1),round(cy*ph/sh,1)
```

**封面关键坐标（px）**：

| 元素 | left | top | width | height | 字号 |
|------|------|-----|-------|--------|------|
| 标题区（居中） | 55 | 158 | 1159 | 154 | 50px bold |
| 汇报人 | 519 | 366 | 243 | 56 | 26px |
| 中国·上海 | 388 | 632 | 174 | 48 | 21px |
| 年月 | 730 | 632 | 175 | 48 | 21px |

**结语关键坐标（px）**：

| 元素 | left | top | width | height | 字号 |
|------|------|-----|-------|--------|------|
| 感谢聆听（居中） | 53 | 278 | 1189 | 130 | 36px bold |

### Step 3：HTML 骨架规范

#### 封面/结语 —— 模板原版

以 tpl_image4.png 全覆盖为背景，仅修改汇报人姓名，其余文字保持模板原样。
文字全部用 position:absolute 精确叠放，字体：微软雅黑/Microsoft YaHei，颜色：#fff。

> ⚠️ 封面/结语：**只改汇报人姓名**，其他文字（标题/城市/年月/感谢语）保持模板原样。

#### 内页（S2~S8）—— 模板白底风格

**页眉 HTML**：

```html
<div class="hdr">
  <!-- 左侧品牌色块 113x68px -->
  <div style="width:113px;height:68px;background:linear-gradient(90deg,#1F497D,#0C72BB);flex-shrink:0;display:flex;align-items:center;justify-content:center;">
    <span style="color:#fff;font-size:11px;font-weight:700;letter-spacing:1px;">国泰海通</span>
  </div>
  <span class="ht">章节标题 | SECTION TITLE</span>
  <span class="hn">姓名 | 部门</span>
</div>
```

**内页 CSS**：

```css
.slide{width:1280px;min-height:720px;position:relative;overflow:hidden;background:#fff;}
.hdr{width:100%;height:68px;background:#fff;display:flex;align-items:center;border-bottom:2px solid #4F81BD;}
.hdr .ht{color:#004E97;font-size:13px;font-weight:600;letter-spacing:1px;padding-left:12px;}
.hdr .hn{color:#999;font-size:12px;margin-left:auto;padding-right:20px;}
.ftr{position:absolute;bottom:0;left:0;right:0;height:36px;background:#fff;border-top:1px solid #e0e8f0;display:flex;align-items:center;padding:0 20px;}
.ftr .fo{color:#999;font-size:11px;letter-spacing:1px;}
.ftr .fp{color:#999;font-size:11px;margin-left:auto;}
.bp{padding:22px 48px 24px 48px;height:calc(720px - 68px - 36px);display:flex;flex-direction:column;}
.stitle{display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-shrink:0;}
.stitle .bar{width:5px;height:28px;background:linear-gradient(180deg,#0C72BB,#1F497D);border-radius:3px;}
.stitle h2{font-size:21px;font-weight:700;color:#004E97;letter-spacing:0.5px;}
.stitle .tag{font-size:11px;background:rgba(12,114,187,0.1);color:#0C72BB;border:1px solid rgba(12,114,187,0.3);border-radius:3px;padding:2px 8px;margin-left:8px;font-weight:600;}
.stat-box{text-align:center;background:linear-gradient(135deg,#1F497D,#0C72BB);border-radius:8px;padding:13px 14px;color:#fff;box-shadow:0 4px 12px rgba(12,114,187,0.12);}
.card{background:#f5f8fc;border-radius:6px;border-left:4px solid #0C72BB;padding:15px 18px;display:flex;flex-direction:column;}
.badge{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;background:#0C72BB;color:#fff;border-radius:50%;font-size:11px;font-weight:700;flex-shrink:0;}
.pfill{height:8px;border-radius:4px;background:linear-gradient(90deg,#1F497D,#0C72BB);}
.flex-fill{flex:1;}

/* 新增：高管战果总览条 (Executive Summary Strip - 避免流水账首要利器) */
.exec-summary-bar{background:linear-gradient(90deg,#102a45,#1F497D,#0C72BB);border-radius:6px;padding:12px 20px;display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;color:#ffffff;box-shadow:0 3px 10px rgba(0,0,0,0.08);flex-shrink:0;}
.exec-item{display:flex;align-items:center;gap:12px;}
.exec-item .ei-val{font-size:24px;font-weight:800;color:#ffe082;font-family:Arial,sans-serif;line-height:1;}
.exec-item .ei-text{font-size:12px;color:#ffffff;line-height:1.35;}
.exec-divider{width:1px;height:26px;background:rgba(255,255,255,0.25);}

/* 新增：SCQA 战役解构标签 (用于核心专项，取代单纯清单罗列) */
.scqa-box{background:#ffffff;border:1px solid #dce8f5;border-radius:6px;padding:8px 12px;margin-bottom:8px;flex-shrink:0;}
.scqa-tag{font-size:10.5px;font-weight:700;padding:1px 6px;border-radius:3px;margin-right:6px;display:inline-block;}
.tag-s{background:#ffebee;color:#c62828;} /* 痛点卡点-红 */
.tag-a{background:#e3f2fd;color:#1565c0;} /* 战役破局-蓝 */
.tag-r{background:#e8f5e9;color:#2e7d32;} /* 终局价值-绿 */

/* 新增：板块条块规划组件 (layout_domain_planner - 垂直撑满无下部空洞 + 五阶同色系明度递进) */
.planner-list{flex:1;display:flex;flex-direction:column;justify-content:space-between;gap:12px;margin-bottom:4px;}
.planner-row{flex:1;display:flex;align-items:stretch;gap:16px;}
.planner-tag{width:210px;flex-shrink:0;border-radius:4px;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:10px 14px;text-align:center;color:#ffffff;box-shadow:0 2px 6px rgba(0,0,0,0.06);}
.planner-tag.tag-dark,.planner-tag.tag-step-1{background:#133962;}
.planner-tag.tag-navy,.planner-tag.tag-step-2{background:#1E4E87;}
.planner-tag.tag-blue,.planner-tag.tag-step-3{background:#2E6BB0;}
.planner-tag.tag-cyan,.planner-tag.tag-step-4{background:#8FA3C0;color:#ffffff;}
.planner-tag.tag-step-5{background:#B8C5D6;color:#133962;} /* 第5阶浅雾蓝配深藏青字，确保高对比度 */
.planner-tag .tag-badge{font-size:10px;background:rgba(255,255,255,0.2);padding:1px 6px;border-radius:2px;margin-bottom:4px;letter-spacing:0.5px;}
.planner-tag.tag-step-5 .tag-badge{background:rgba(19,57,98,0.12);color:#133962;}
.planner-tag .tag-title{font-size:13.5px;font-weight:700;letter-spacing:0.5px;line-height:1.35;}
.planner-content.dashed-box{flex:1;border:1.5px dashed #4F81BD;border-radius:4px;background:#fbfdff;padding:10px 18px;display:flex;flex-direction:column;justify-content:center;gap:5px;}
.p-item{font-size:12.2px;color:#333333;line-height:1.55;display:flex;align-items:flex-start;}
.p-num{font-weight:700;color:#004E97;margin-right:6px;flex-shrink:0;}

/* 新增：高管极简编号页眉 + 左下角加粗深蓝装饰锚点 (Executive Minimal Header) */
.hdr-exec{width:100%;height:64px;background:#fff;display:flex;align-items:center;justify-content:space-between;padding:0 48px;border-bottom:1.5px solid #4F81BD;position:relative;}
.hdr-exec::after{content:"";position:absolute;left:48px;bottom:-2.5px;width:72px;height:4px;background:#1F497D;}
.hdr-exec .he-title{font-size:24px;font-weight:700;color:#1F497D;letter-spacing:0.5px;display:flex;align-items:baseline;gap:14px;}
.hdr-exec .he-num{font-family:Arial,sans-serif;font-weight:800;color:#1F497D;}
.hdr-exec .he-brand{font-family:Arial,sans-serif;font-size:13px;font-weight:700;color:#7a8a9e;letter-spacing:1.5px;}

/* 新增：双层标题之「一句话战果副标题 + PM元数据栏」 (Sub-headline & Meta Strip) */
.sub-headline-wrap{margin-bottom:14px;flex-shrink:0;}
.sub-headline-title{font-size:19px;font-weight:700;color:#1a2533;letter-spacing:0.3px;line-height:1.35;}
.sub-headline-meta{font-size:11.5px;color:#666666;margin-top:4px;display:flex;align-items:center;gap:14px;}
.sub-headline-meta .meta-sep{color:#cccccc;}
.hl-red{color:#D9232E;font-weight:700;} /* 正文与指标战果红高亮 */

/* 新增：版式A - 常规工作/基本盘稳健运行页 (layout_steady_ops) */
.ops-top-strip{background:#f2f7fd;border:1px solid #d0e1f9;border-radius:8px;padding:10px 24px;display:grid;grid-template-columns:repeat(4,1fr);align-items:center;margin-bottom:14px;flex-shrink:0;}
.ops-kpi-item{display:flex;align-items:center;justify-content:center;gap:12px;border-right:1px solid #bfd4f2;}
.ops-kpi-item:last-child{border-right:none;}
.ops-pie-icon{width:34px;height:34px;border-radius:50%;background:conic-gradient(#1F497D 0% 72%, #8eb4e3 72% 100%);border:2px solid #fff;box-shadow:0 2px 5px rgba(31,73,125,0.15);flex-shrink:0;}
.ops-kpi-label{font-size:13px;font-weight:700;color:#333;margin-bottom:2px;}
.ops-kpi-val{font-size:22px;font-weight:800;color:#D9232E;font-family:Arial,sans-serif;line-height:1.1;}
.ops-kpi-unit{font-size:13px;font-weight:700;color:#333;margin-left:2px;}
.ops-3col-grid{flex:1;display:grid;grid-template-columns:repeat(3,1fr);gap:16px;align-items:stretch;margin-bottom:12px;}
.ops-col-card{background:#f4f8fd;border:1px solid #d6e4f5;border-radius:6px;display:flex;flex-direction:column;overflow:hidden;}
.ops-col-hdr{background:linear-gradient(90deg,#1F497D,#2E6BB0);color:#ffffff;font-size:14.5px;font-weight:700;text-align:center;padding:8px 12px;letter-spacing:1px;clip-path:polygon(8px 0,100% 0,calc(100% - 8px) 100%,0 100%);margin:6px 10px 4px 10px;border-radius:2px;}
.ops-col-body{padding:8px 14px 12px 14px;font-size:11.5px;color:#333;line-height:1.55;flex:1;display:flex;flex-direction:column;gap:6px;}
.ops-bottom-pills{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;flex-shrink:0;}
.ops-pill-card{background:#f8fbff;border:1px solid #dce8f5;border-radius:6px;padding:6px 14px;display:flex;align-items:center;justify-content:space-between;}
.ops-pill-tag{background:#1F497D;color:#fff;font-size:11.5px;font-weight:700;padding:3px 12px;border-radius:3px;}
.ops-pill-stat{font-size:12px;color:#333;font-weight:600;}

/* 新增：版式B - 3浅1深非对称KPI顶栏 + 2x2能力建设矩阵 (layout_3light_1dark_matrix) */
.kpi-3l1d-grid{display:grid;grid-template-columns:1fr 1fr 1fr 0.95fr;gap:14px;margin-bottom:16px;flex-shrink:0;}
.kpi-light-card{background:linear-gradient(135deg,#eef5fc,#f7fbff);border:1px solid #d5e4f5;border-left:4px solid #0C72BB;border-radius:6px;padding:10px 16px;display:flex;flex-direction:column;justify-content:space-between;}
.kpi-light-card .kl-title{font-size:13px;font-weight:700;color:#1a2533;}
.kpi-light-card .kl-num-row{display:flex;align-items:baseline;justify-content:space-between;margin:4px 0;}
.kpi-light-card .kl-val{font-size:30px;font-weight:800;color:#D9232E;font-family:Arial,sans-serif;line-height:1;}
.kpi-light-card .kl-unit{font-size:12.5px;font-weight:700;color:#333;}
.kpi-light-card .kl-sub{font-size:11px;color:#666666;}
.kpi-dark-card{background:linear-gradient(135deg,#133962,#1F497D);border-radius:6px;padding:10px 16px;color:#ffffff;display:flex;flex-direction:column;justify-content:space-between;box-shadow:0 4px 12px rgba(19,57,98,0.18);}
.kpi-dark-card .kd-title{font-size:13px;font-weight:700;color:#e0edff;}
.kpi-dark-card .kd-val{font-size:32px;font-weight:800;color:#ffffff;font-family:Arial,sans-serif;line-height:1.05;margin:4px 0;}
.kpi-dark-card .kd-sub{font-size:11px;color:rgba(255,255,255,0.75);}
.matrix-2x2-grid{flex:1;display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;gap:14px;align-items:stretch;}
.matrix-cap-card{border:1.5px dashed #7fa6d6;border-radius:6px;background:#fbfdff;display:flex;flex-direction:column;overflow:hidden;}
.matrix-cap-hdr{background:linear-gradient(90deg,#dceaf9 0%,#eef5fc 65%,#ffffff 100%);border-bottom:1px solid #d0e1f5;padding:7px 14px;display:flex;align-items:center;justify-content:space-between;border-left:4px solid #0C72BB;}
.matrix-cap-hdr .mc-title{font-size:14px;font-weight:700;color:#004E97;display:flex;align-items:center;gap:6px;}
.matrix-cap-hdr .mc-slogan{font-size:11.5px;font-style:italic;font-weight:600;color:#1F497D;}
.matrix-cap-body{padding:10px 14px;font-size:11.8px;color:#333;line-height:1.58;display:flex;flex-direction:column;gap:6px;flex:1;justify-content:center;}

/* 新增：版式C - 一深一浅双英雄数据卡 + 环比红胶囊 + 星标里程碑 (layout_dual_hero) */
.dual-hero-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:14px;flex-shrink:0;}
.hero-card-dark{background:linear-gradient(135deg,#133962,#1E4E87);border-radius:8px;padding:14px 20px;color:#ffffff;display:flex;flex-direction:column;justify-content:space-between;box-shadow:0 4px 14px rgba(19,57,98,0.16);}
.hero-card-dark .hd-top{display:flex;align-items:baseline; gap:12px;}
.hero-card-dark .hd-name{font-size:15px;font-weight:700;color:#ffffff;}
.hero-card-dark .hd-tag{font-size:11.5px;color:#cbe0ff;}
.hero-card-dark .hd-main-val{font-size:40px;font-weight:800;color:#ffffff;font-family:Arial,sans-serif;line-height:1.1;margin:6px 0;}
.hero-card-dark .hd-main-unit{font-size:15px;font-weight:700;margin-left:6px;}
.hero-card-dark .hd-footer{border-top:1px solid rgba(255,255,255,0.2);padding-top:8px;display:grid;grid-template-columns:1fr 1fr;font-size:12px;color:#e0edff;}
.hero-card-dark .hd-footer b{font-size:16px;color:#ffffff;margin-left:6px;}
.hero-card-light{background:#f3f7fc;border:1px solid #d0e1f5;border-radius:8px;padding:14px 20px;display:flex;flex-direction:column;justify-content:space-between;}
.hero-card-light .hl-main-row{display:flex;align-items:center;justify-content:space-between;margin:4px 0;}
.hero-card-light .hl-val{font-size:38px;font-weight:800;color:#D9232E;font-family:Arial,sans-serif;line-height:1;}
.hero-card-light .hl-unit{font-size:14px;font-weight:700;color:#D9232E;margin-left:4px;}
.growth-pill{background:#D9232E;color:#ffffff;font-size:11.5px;font-weight:700;padding:4px 12px;border-radius:16px;line-height:1.2;text-align:center;box-shadow:0 2px 6px rgba(217,35,46,0.25);}
.hero-card-light .hl-sub-list{border-top:1px solid #dce8f5;padding-top:6px;display:flex;flex-direction:column;gap:3px;font-size:11.5px;color:#444;}
.hero-card-light .hl-sub-row{display:flex;justify-content:space-between;}
.star-milestone-box{flex:1;border:1px dashed #8eb4e3;border-radius:6px;background:#fbfdff;padding:12px 16px;display:flex;flex-direction:column;justify-content:space-around;gap:8px;}
.star-sec-title{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:700;color:#004E97;margin-bottom:3px;}
.star-icon{width:18px;height:18px;border-radius:50%;background:#1F497D;color:#fff;font-size:10px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;}

/* 新增：版式D - AI智能体双栏卡 + 底部原生CSS柱状图看板 (layout_ai_bar_chart) */
.ai-top-2col{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:14px;flex-shrink:0;}
.ai-agent-card{border:1.5px dashed #7fa6d6;border-radius:6px;background:#fbfdff;overflow:hidden;display:flex;flex-direction:column;}
.ai-agent-hdr{background:linear-gradient(90deg,#0C72BB,#2E6BB0);color:#ffffff;font-size:14.5px;font-weight:700;padding:8px 16px;display:flex;align-items:center;gap:8px;}
.ai-agent-body{padding:10px 16px;font-size:11.8px;color:#333;line-height:1.55;display:flex;flex-direction:column;gap:6px;flex:1;}
.ai-sub-label{font-size:12.5px;font-weight:700;color:#1F497D;margin-top:2px;}
.ai-chart-panel{flex:1;background:#f5f9fe;border:1px solid #dce8f5;border-radius:6px;padding:10px 20px;display:flex;flex-direction:column;justify-content:space-between;}
.ai-chart-badge{background:#1F497D;color:#ffffff;font-size:12.5px;font-weight:700;padding:4px 14px;border-radius:3px;align-self:flex-start;clip-path:polygon(0 0,100% 0,calc(100% - 8px) 100%,0 100%);}
.ai-chart-groups{flex:1;display:grid;grid-template-columns:1.2fr 1fr;gap:32px;align-items:end;padding:8px 12px 4px 12px;}
.bar-group{display:flex;flex-direction:column;height:100%;justify-content:space-between;}
.bar-group-title{font-size:12px;font-weight:700;color:#1F497D;text-align:center;margin-bottom:6px;}
.bar-items-row{display:flex;align-items:flex-end;justify-content:space-around;height:110px;border-bottom:1.5px solid #8FA3C0;padding:0 10px;}
.bar-col{display:flex;flex-direction:column;align-items:center;gap:4px;}
.bar-val{font-size:12px;font-weight:800;color:#1a2533;font-family:Arial,sans-serif;}
.bar-pillar{width:38px;background:linear-gradient(180deg,#0C72BB,#1F497D);border-radius:3px 3px 0 0;}
.bar-lbl{font-size:11px;color:#555;margin-top:4px;text-align:center;}
.bar-group-foot{font-size:11px;color:#555;text-align:center;margin-top:6px;font-weight:600;}

/* 新增：难点与建议对照组件 (layout_challenge_solution - 垂直撑满居中) */
.stitle-banner{display:flex;align-items:center;gap:14px;margin-bottom:18px;flex-shrink:0;}
.stitle-banner .badge-num{width:42px;height:32px;background:#004E97;color:#ffffff;font-size:19px;font-weight:700;display:flex;align-items:center;justify-content:center;border-radius:4px;}
.stitle-banner h2{font-size:21px;font-weight:700;color:#004E97;letter-spacing:0.5px;}
.cs-container{flex:1;display:flex;flex-direction:column;justify-content:space-between;gap:18px;margin-bottom:6px;}
.cs-row{flex:1;display:grid;grid-template-columns:1fr 1.35fr;gap:18px;align-items:stretch;}
.cs-box{display:flex;align-items:stretch;background:#f7faff;border:1px solid #dce8f5;border-radius:4px;overflow:hidden;box-shadow:0 2px 6px rgba(12,114,187,0.03);}
.cs-pain{border-left:4px solid #1F497D;}
.cs-sol{border-left:4px solid #0C72BB;background:#fdfefe;}
.v-badge{width:38px;background:#004E97;color:#ffffff;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;line-height:1.35;letter-spacing:1px;flex-shrink:0;padding:6px 0;text-align:center;}
.v-badge-sol{background:#0C72BB;}
.cs-text{padding:14px 18px;flex:1;display:flex;flex-direction:column;justify-content:center;}
.cs-title{font-size:13.8px;font-weight:700;color:#004E97;margin-bottom:6px;line-height:1.4;}
.cs-desc{font-size:12px;color:#444444;line-height:1.6;}
.cs-bullet-list{margin:0;padding-left:16px;font-size:12px;color:#444444;line-height:1.6;}
.cs-bullet-list li{margin-bottom:4px;}
```

### Step 4：截图嵌入规范

用户提供系统截图时，先将图片 cp 到 HTML 同目录，再使用左指标/右截图双栏布局：
- 比例：`grid-template-columns: 1fr 1.6fr`
- 截图容器：`border-radius:10px; box-shadow:0 4px 20px rgba(0,60,120,0.15); border:1px solid rgba(12,114,187,0.15)`
- 来源标注：`数据来源：XXX平台 YYYY-MM ~ YYYY-MM`（10px #999）

> ⚠️ 截图与 HTML 文件须在**同一目录**，使用相对路径。

### Step 5：大文件写入（绕过工具长度限制）

HTML > 10KB 时，**必须用 run_command + Python** 写入，禁止直接用工具参数传递超长字符串：

```bash
python3 /tmp/write_ppt.py
# write_ppt.py 内容：
# html = """..."""
# with open('/path/to/output.html','w',encoding='utf-8') as f: f.write(html)
```

### Step 6：HTML 转 PDF 规范

本技能支持通过 Playwright 渲染引擎，将生成的 HTML 页面高保真地转换输出为 PDF 矢量文档。

#### 转换机制
1. **高保真矢量导出**：自动在页面注入 `@page { size: 1280px 720px; margin: 0; }` 并规范 html/body padding，严格执行 `1 slide = 1 page` 打印映射，**彻底消除首尾及中间空白溢出页**。
2. **运行命令**：
```bash
python3 /Users/wujin/.workbuddy/skills/debrief-ppt-maker/scripts/convert_html.py /path/to/slide.html
```

---

## 避开流水账：高手级战役叙事法则 (Anti-Ledger Protocol)

述职不是“工作日记罗列”，而是证明“业务价值沉淀与组织影响力”。必须严格遵循以下五大战役叙事法则：

### 法则一：结论先行与双模标题体系（Headline & Sub-headline Rule）
- ❌ **禁止使用空泛模块标题或冗长带冒号的单行标题**：如“核心业务专项一”、“系统优化”，或把长串副标题硬塞进同一个 `<h2>` 导致折行拥挤。
- ✅ **支持两种标准标题模式（按单页信息密度择一使用）**：
  1. **精简标题模式（2026Q3 个人述职定稿）**：`stitle h2` 与卡片标题保持极简短语（如 `集中交易去历史查询`、`产品经理个人驾驶舱`），不带冒号副标题，战果/判断句下沉到正文 `stat-box`、SCQA 卡片与 `list-item`。
  2. **高管双层标题模式（部门/专项述职推荐）**：
     - **一级页眉（`.hdr-exec`）**：左上角 `02  深图一体化投资管理平台`（序号 + 精简模块名），右上角 `GUOTAIHAITONG`，底部分割线左端带 72px 加粗深蓝装饰锚点；
     - **二级战果副标题（`.sub-headline-title`）**：页眉正下方首行用 19px 黑体直接抛出一句话核心战果（如 `项目三季度完成116项需求，同步推进四大能力建设` 或 `商品期货期权累计成交130亿元，债券做市日均5亿元、环比+100%`）；
     - **三级 PM 元数据栏（`.sub-headline-meta`）**：紧跟一行浅灰小字锚定统计边界与总目标（如 `截至时间：2026/9/30  |  年度目标实现：80%`）。

### 法则二：高管战果总览条（Executive Summary Strip）
- 在 S2 目录页顶部，必须设置一条深蓝渐变色高管战果横幅（`.exec-summary-bar`）。
- 提炼 4 个金黄大字核心指标锚点（如 `4大核心攻坚战役`、`75项需求平稳推进`、`近100%核心下游适配`、`约28倍 AI追溯提速`），在汇报第 2 页的前 15 秒内直接定调。**锚点数字必须可回溯到源文档，且“100%”仅当全集事实成立时可用（否则用“近100%”）；需求总量含在途时写“平稳推进/闭环管理”，禁止写“全流程上线”。**

### 法则三：SCQA 战役模型拆解（SCQA Battle Card）
- 专项严禁平铺需求清单，必须使用 SCQA 结构卡片（`.scqa-box`）：
  - **痛点卡点（红标 `.tag-s`）**：老系统负荷冗余、多系统耦合严重、信创受阻等关键阻碍；
  - **攻坚战法（蓝标 `.tag-a`）**：主刀解耦、统一收口清算侧、双链路拉齐、三方协同机制；
  - **终局价值（绿标 `.tag-r`）**：突出金融级免死金牌——**“业务 0 中断 · 客户 0 投诉 · 数据 0 误差”**。

### 法则四：管理与生产力范式跃迁（Paradigm Shift）
- **驾驶舱叙事**：突出认知对比——从“催人问进度的消防员”升级为“看板等风险的领航员”（提前 2~3 周暴露风险）。
- **AI 生产力叙事**：不谈个人小账，谈**“工程质量红线制度化”**（如链接门禁、双检护栏、状态感知幂等）与端到端自动化流水线，证明个人经验已沉淀为团队基础设施。

### 法则五：指标对比与归因（Attribution & Multiplier）
- 突出倍率反差（如：`85s ➔ 3s（提速约 28 倍）`、`冷加载 58s ➔ 22s（降幅约62%）`、`旧历史库 8.8T ➔ 1.8T（-79.5%）日均压降 70%+`、`手工轮次 -60%`）。**倍率必须验算：提速倍数 = 旧值 ÷ 新值（85÷3≈28），降幅 =（旧−新）÷旧（58→22 降幅 62.07%，写“约62%”而非63%），严禁凭直觉夸大（如把 85s→3s 写成“100 倍+”），否则评审一算即穿帮。**
- 效能度量指标必须给出根本归因（架构解耦减少返工 + 驾驶舱前置暴露 + AI流水线消除损耗）。

---

## 标准页面清单与精选版式库

述职演示文稿标准为 10~11 页高光体系，支持按内容灵活组合（2026Q3 实战版为 13 页，目录「02 模块」含需求指标 + 版本集成发布双页）：

| 页 | 类型 | 推荐版式 | 叙事重点 |
|----|------|---------|---------|
| S1 | 封面 | 原版封面 | `tpl_image4.png` + 极简大标题 + 汇报人/部门/日期（**不加定调副标题**） |
| S2 | 目录与战果 | **极简目录 + 战果总览条 (`agenda-clean-grid`)** | 顶部 4 大核心战果指标 + 中部四大模块极简章节导航（不提前剧透长段正文，避免二次阅读疲劳） |
| S3 | 核心专项①（全景交付） | **`layout_3light_1dark_matrix` / SCQA 卡** | **3浅1深非对称KPI顶栏（红字高亮+深蓝目标卡）+ 四大能力建设 2×2 虚线矩阵卡** |
| S4 | 核心专项②（业务战果） | **`layout_dual_hero` / 左右双专项卡** | **一深一浅双英雄数据卡 + 环比增长红胶囊 + 底部星标关键里程碑** |
| S5 | 数字化实践 | **管理范式跃迁三栏卡** | 冷加载 -62% + 过去vs现在对比 + 3 级穿透 |
| S6 | AI 生产力 | **`layout_ai_bar_chart` / 流水线双栏** | **上半部「技术架构+业务场景」双智能体卡 + 下半部原生CSS柱状图（规模+同比增幅）** |
| S7 | 本季度需求指标看板 | **数据看板与机制归因** | 75 项需求平稳流动 + 流动效率 + 根本归因（页面标题 2026-11-11 定稿）；**由 `build_quarter_pages.py --quarter` 按季度配置自动生成** |
| **S8 (新增)** | **版本集成发布情况** | **4 KPI + 月度双系列柱状图 + 系统分布 + 月度明细卡 + 口径脚注** | 与 S7 同属目录「02 模块」；数据取全连接文档中心《各系统发版汇总》在线文档，规则见下方专章（2026-11-11 新增）；**与 S7 同由一条命令生成** |
| **S9 (战略)** | **后续工作规划** | **`layout_domain_planner` (五阶递进蓝)** | **实战还原：五阶同色系渐变模块色卡 + 虚线编号战役路线图** |
| **S10 (压轴讨论)** | **难点创新点讨论** | **`layout_discuss_qa`（置于后续工作规划之后）** | **实战还原：左「难点1/2」（蓝字标题+1/2分点）+ 右「建议」（向团队/领导提建设性方案，自然衔接Q&A）** |
| S11 | 结语 | 原版结语 | `tpl_image4.png` + 感谢聆听居中 |

### 高级版式 HTML 骨架速查

#### 1. 高管战果总览条 (`exec-summary-bar`)
```html
<div class="exec-summary-bar">
  <div class="exec-item">
    <div class="ei-val">3 大</div>
    <div class="ei-text"><b>核心攻坚战役</b><br>去历史查询 / 两融流转 / Y内切</div>
  </div>
  <div class="exec-divider"></div>
  <div class="exec-item">
    <div class="ei-val">73 项</div>
    <div class="ei-text"><b>需求平稳推进</b><br>全流程闭环管理，业务 0 中断</div>
  </div>
  <div class="exec-divider"></div>
  <div class="exec-item">
    <div class="ei-val">近100%</div>
    <div class="ei-text"><b>核心下游适配率</b><br>300+ 表梳理，信创干净基线</div>
  </div>
  <div class="exec-divider"></div>
  <div class="exec-item">
    <div class="ei-val">约28倍</div>
    <div class="ei-text"><b>AI 源码追溯提速</b><br>85s ➔ 3s，全链路闭环</div>
  </div>
</div>
```

#### 2. SCQA 战役解构卡片 (`scqa-box`)
```html
<div class="scqa-box">
  <span class="scqa-tag tag-s">痛点卡点</span>
  <span style="font-size:11.5px; color:#c62828;">老系统日终负荷沉重，外围 16 系统耦合严重，信创改造动弹不得。</span>
</div>
<div class="scqa-box">
  <span class="scqa-tag tag-r">终局价值</span>
  <span style="font-size:11.5px; color:#2e7d32;"><b>业务 0 中断 · 客户 0 投诉 · 数据 0 误差</b>，扫清信创切换核心路障。</span>
</div>
```

#### 3. 板块条块规划矩阵 (`layout_domain_planner` —— 五阶递进蓝)
```html
<div class="planner-list">
  <!-- 从 tag-step-1 到 tag-step-5 实现同色系由深至浅五阶明度递进 -->
  <div class="planner-row">
    <div class="planner-tag tag-step-1">
      <span class="tag-badge">核心业务域</span>
      <span class="tag-title">深图<br>一体化投资管理平台</span>
    </div>
    <div class="planner-content dashed-box">
      <div class="p-item"><span class="p-num">1)</span> 推进商品期货期权全量业务迁移，年内实现商品业务估值单轨运行。</div>
      <div class="p-item"><span class="p-num">2)</span> 推进沪深北非竞价业务技术研发，达到O32替代上线标准。</div>
    </div>
  </div>
</div>
```

#### 4. 难点攻坚与对策对照 (`layout_challenge_solution`)
```html
<div class="stitle-banner">
  <div class="badge-num">08</div>
  <h2>重点难点攻坚与创新反思</h2>
</div>
<div class="cs-container">
  <div class="cs-row">
    <div class="cs-box cs-pain">
      <div class="v-badge">难<br>点<br>1</div>
      <div class="cs-text">
        <h4 class="cs-title">去历史查询下游系统庞大，跨部门协同壁垒高</h4>
        <p class="cs-desc">历史数据迁移涉及 16 个外围系统、300 余张数据表...</p>
      </div>
    </div>
    <div class="cs-box cs-sol">
      <div class="v-badge v-badge-sol">建<br>议</div>
      <div class="cs-text">
        <ul class="cs-bullet-list">
          <li><b>以机制打破部门壁垒：</b>建立“跟踪邮件 + 在线文档 + 逐系统提醒”机制...</li>
        </ul>
      </div>
    </div>
  </div>
</div>
```

#### 5. 3浅1深非对称KPI顶栏 + 2×2能力建设矩阵 (`layout_3light_1dark_matrix`)
```html
<div class="sub-headline-wrap">
  <div class="sub-headline-title">项目三季度完成116项需求，同步推进四大能力建设</div>
  <div class="sub-headline-meta">
    <span>截至时间：2026/9/30</span><span class="meta-sep">|</span><span>年度目标实现：80%</span>
  </div>
</div>
<div class="kpi-3l1d-grid">
  <div class="kpi-light-card">
    <div class="kl-title">业务需求</div>
    <div class="kl-num-row"><span class="kl-val">116</span><span class="kl-unit">项</span></div>
    <div class="kl-sub">覆盖交易、销售、运营、对客与协同项目</div>
  </div>
  <!-- 其余 2 个 kpi-light-card 略 -->
  <div class="kpi-dark-card">
    <div class="kd-title">年度目标实现</div>
    <div class="kd-val">80%</div>
    <div class="kd-sub">目标完成时间：2026/12</div>
  </div>
</div>
<div class="matrix-2x2-grid">
  <div class="matrix-cap-card">
    <div class="matrix-cap-hdr">
      <span class="mc-title"><span class="badge">01</span> 销售交易重塑</span>
      <span class="mc-slogan">全面提升跨部门协同效能与平台化服务能力</span>
    </div>
    <div class="matrix-cap-body">
      <div>▪ <b>投标分销自研信创二期上线：</b>8月6日，债券投标分销模块移动端功能上线，<span class="hl-red">启动灰度试运行</span>。</div>
    </div>
  </div>
</div>
```

#### 6. 一深一浅双英雄数据卡 + 环比红胶囊 (`layout_dual_hero`)
```html
<div class="dual-hero-grid">
  <!-- 左：深蓝实心英雄卡 -->
  <div class="hero-card-dark">
    <div class="hd-top"><span class="hd-name">商品期货期权</span><span class="hd-tag">完成2家期货公司业务迁移并展业</span></div>
    <div><span style="font-size:12px;color:#cbe0ff;">累计成交金额</span><div class="hd-main-val">130<span class="hd-main-unit">亿元</span></div></div>
    <div class="hd-footer">
      <span>累计委托笔数 <b>4.2 万笔</b></span>
      <span>累计成交笔数 <b>10 万笔</b></span>
    </div>
  </div>
  <!-- 右：浅底红字高增长英雄卡 -->
  <div class="hero-card-light">
    <div><b style="font-size:14px;color:#1F497D;">债券广义做市</b> <span style="font-size:11.5px;color:#666;margin-left:8px;">报价成交金额</span></div>
    <div class="hl-main-row">
      <div><span class="hl-val">5</span><span class="hl-unit">亿元/天</span></div>
      <div class="growth-pill">环比<br>+100%</div>
    </div>
    <div class="hl-sub-list">
      <div class="hl-sub-row"><span>广义做市日均活跃交易员</span><span class="hl-red">48人</span></div>
      <div class="hl-sub-row"><span>意向询价笔数</span><span class="hl-red">1434笔/天 环比+82%</span></div>
    </div>
  </div>
</div>
```

#### 7. AI 智能体「架构+场景」双栏 + 底部原生 CSS 柱状图看板 (`layout_ai_bar_chart`)
```html
<div class="ai-top-2col">
  <div class="ai-agent-card">
    <div class="ai-agent-hdr">01 &nbsp;询报价智能体</div>
    <div class="ai-agent-body">
      <div class="ai-sub-label">技术架构建设</div>
      <div>将传统微服务架构升级为 <b>Skill + 自主编排智能体新架构</b>：完成接入、编排、Skill能力、渠道适配、基础服务 <b>5 层架构搭建</b>。</div>
      <div class="ai-sub-label">业务场景落地</div>
      <div>新增询价、风控、撤单、交易确认 <b>4 项交易 Skill 能力</b>，贯通 <b>6 个核心环节</b>。</div>
    </div>
  </div>
  <!-- 02 智能体卡片略 -->
</div>
<div class="ai-chart-panel">
  <div class="ai-chart-badge">阶段性成果</div>
  <div class="ai-chart-groups">
    <div class="bar-group">
      <div class="bar-group-title">用户规模构成</div>
      <div class="bar-items-row">
        <div class="bar-col"><span class="bar-val">120</span><div class="bar-pillar" style="height:42px;"></div><span class="bar-lbl">内部用户</span></div>
        <div class="bar-col"><span class="bar-val">154</span><div class="bar-pillar" style="height:56px;"></div><span class="bar-lbl">机构客户</span></div>
        <div class="bar-col"><span class="bar-val">267</span><div class="bar-pillar" style="height:88px;"></div><span class="bar-lbl">客户侧交易员</span></div>
      </div>
      <div class="bar-group-foot">活跃客户 139 家 · 活跃交易员 214 人</div>
    </div>
    <div class="bar-group">
      <div class="bar-group-title">同比增长幅度 (%)</div>
      <div class="bar-items-row">
        <div class="bar-col"><span class="bar-val">1400%</span><div class="bar-pillar" style="height:85px;"></div><span class="bar-lbl">新增客户</span></div>
        <div class="bar-col"><span class="bar-val">900%</span><div class="bar-pillar" style="height:55px;"></div><span class="bar-lbl">新增交易员</span></div>
      </div>
      <div class="bar-group-foot">新增客户 +14 倍 · 新增交易员 +9 倍</div>
    </div>
  </div>
</div>
```

#### 8. 常规工作/基本盘稳健运行页 (`layout_steady_ops`)
```html
<div class="ops-top-strip">
  <div class="ops-kpi-item">
    <div class="ops-pie-icon"></div>
    <div><div class="ops-kpi-label">系统数量</div><div><span class="ops-kpi-val">28</span><span class="ops-kpi-unit">个</span></div></div>
  </div>
  <div class="ops-kpi-item">
    <div class="ops-pie-icon"></div>
    <div><div class="ops-kpi-label">需求上线</div><div><span class="ops-kpi-val">317</span><span class="ops-kpi-unit">个</span></div></div>
  </div>
  <div class="ops-kpi-item">
    <div class="ops-pie-icon"></div>
    <div><div class="ops-kpi-label">上线版本</div><div><span class="ops-kpi-val">89</span><span class="ops-kpi-unit">个</span></div></div>
  </div>
  <div class="ops-kpi-item">
    <div class="ops-pie-icon"></div>
    <div><div class="ops-kpi-label">周末测试</div><div><span class="ops-kpi-val">9</span><span class="ops-kpi-unit">次</span></div></div>
  </div>
</div>
<div class="ops-3col-grid">
  <div class="ops-col-card">
    <div class="ops-col-hdr">交 &nbsp; 易</div>
    <div class="ops-col-body">
      <div>▪ <b>境内：</b>完成沪深京交易规则调整与G4上线多轮测试...</div>
      <div>▪ <b>境外：</b>提升QFII产品覆盖，新增支持可转债交易与公司行为处理...</div>
    </div>
  </div>
  <!-- 风控与定价 / 资产管理两列略 -->
</div>
<div class="ops-bottom-pills">
  <div class="ops-pill-card"><span class="ops-pill-tag">权益类</span><span class="ops-pill-stat">日均委托量 <span class="hl-red">130万笔</span></span></div>
  <div class="ops-pill-card"><span class="ops-pill-tag">固收类</span><span class="ops-pill-stat">日均委托量 <span class="hl-red">60万笔</span></span></div>
  <div class="ops-pill-card"><span class="ops-pill-tag">商品类</span><span class="ops-pill-stat">日均委托量 <span class="hl-red">3.2万笔</span></span></div>
</div>
```

## 最佳实践

- **封面/结语**：直接用 `tpl_image4.png`，**只改汇报人姓名**，其余文字保持模板原样。
- **内页页眉**：必须有左侧 113×68px 渐变色块（#1F497D→#0C72BB），分割线 #4F81BD。
- **颜色一致性**：禁止使用 #0a2456/#00a8e8/#38d9f5/#0078be/#00a8c8/#0e7ec0 等旧色，统一用配色体系表中的色值。
- **截图引用**：图片先 cp 至 HTML 同目录，再相对路径引用。
- **字体**：微软雅黑/PingFang SC；正文 12-13px；标题 22px；大数字 36-50px。
- **禁止**：padding-bottom 撑高 | 超过 10KB 的工具参数字符串写入。

## 对比度规范（Color Contrast Rules）

生成时必须遵守的对比度铁律，避免"文字隐形"问题：

### 规则一：深色背景 → 只能用白/亮色文字

深蓝背景（`#1F497D`、`#0C72BB`、`#004E97` 及其渐变）上：

| 用途 | 正确色 | 禁止色 |
|------|--------|--------|
| 主要文字/数字 | `#ffffff` | ~~`#4F81BD`~~（太暗，不可见） |
| 次要文字 | `rgba(255,255,255,0.75)` | ~~`#0C72BB`~~（同色系，消失） |
| 图标 | `rgba(255,255,255,0.85)` | ~~`#4F81BD`~~（对比不足） |
| 小标签/子标题 | `#e0edff`（浅冰蓝） | ~~`#4F81BD`~~（深蓝上不清晰） |
| 强调色标签 | `#ffe0a0`（金色系） | ~~`#f5a623`~~（暖色在蓝底略暗） |
| 项目符号 · | `rgba(255,255,255,0.6)` | ~~`#4F81BD`~~（消失） |

### 规则二：浅色背景 → 只能用深色文字

浅色背景（`#EEF4FB`、`#D6E8F5`、`#f5f8fc`、`#fff`）上：

| 用途 | 正确色 | 禁止色 |
|------|--------|--------|
| 正文 | `#3a4a60` | ~~`rgba(255,255,255,0.8)`~~（白字在浅底完全隐形） |
| 次级文字 | `#6a7a90` | ~~`#fff`~~（不可见） |
| 图标 | `#0C72BB` 或 `#1F497D` | ~~`rgba(255,255,255,0.8)`~~（不可见） |
| 标签颜色 | `#f5a623`（金色，OK）/ `#27ae60`（绿，OK） | ~~白色系~~（不可见） |

### 规则三：卡片类型与背景色绑定

| 卡片类型 | 背景 | 文字规则 |
|---------|------|---------|
| 深蓝数据看板 | `linear-gradient(#1F497D,#0C72BB)` | 数字/标签全白 |
| 灰底内容卡 | `#f5f8fc` | 深色文字（`#3a4a60`/`#1F497D`） |
| 白底子卡 | `#ffffff` | 深色文字，border-left 用 `#0C72BB` |
| 高亮结论条 | `linear-gradient(#eaf2fb,#d6eaf8)` | 深色文字（`#1F497D`），**禁止白色** |
| 里程碑深蓝条 | `linear-gradient(#1F497D,#0C72BB)` | 全部用白/半透白，月份标签用 `rgba(255,255,255,0.75)` |

### 规则四：`#4F81BD` 与 `战果红 (#D9232E)` 的正确用法

1. **`#4F81BD`（品牌蓝）仅适合白/浅色背景**，禁止用在深蓝背景上：
   - ✅ 正确：页眉分割线（白底上）、进度条、小 tag 文字（浅底）
   - ❌ 禁止：深蓝背景上的数字、图标、标签（会隐形）
2. **`#D9232E`（战果红）仅用于浅色背景上的核心数字与高亮词，或作为实心胶囊背景配白字**：
   - ✅ 正确：浅蓝/白底卡片（`#f5f8fc` / `#eef5fc` / `#fff`）上的核心大数字、正文加粗红字（`.hl-red`）、红底白字的增长胶囊（`.growth-pill`）
   - ❌ 禁止：直接在深蓝背景（`#1F497D` / `#133962`）上写红字（红蓝撞色刺眼且对比度低；深蓝底上一律用纯白 `#fff` 或浅金 `#ffe082`）
3. **`五阶递进蓝` 第 5 阶浅雾蓝 (`#B8C5D6`) 必须配深藏青文字 (`#133962`)**：
   - 前 4 阶（`#133962`、`#1E4E87`、`#2E6BB0`、`#8FA3C0`）用白色文字 `#ffffff`；第 5 阶因明度高，必须切换为深色文字 `#133962`。

### 快速自查清单（生成后检查）

在完成 HTML 生成后，逐页确认：

- [ ] 深蓝背景上所有文字/数字是否为白色系？
- [ ] `#EEF4FB`/`#f5f8fc` 浅背景上无白色文字？
- [ ] 卡片 border-left 颜色是否使用 `#0C72BB` 而非旧色？
- [ ] 图标颜色与其所在背景是否形成足够对比？
- [ ] 旧色（#00a8e8/#38d9f5/#0078be/#00a8c8/#0e7ec0/#0a2456）是否已全部替换？

---

## 2026 Q3 实战优化要点（已验证，后续汇报直接沿用）

以下要点为 Q3 述职对照核查整改后沉淀，**每次生成时直接执行**：

1. **个人角色标签**：每页 `stitle .tag` 最前标注个人角色（`牵头统筹` / `主刀攻坚` / `牵头主责`），避免“全程叙述无主语”，让评审一眼看清个人贡献边界。
2. **封面年月**：写**述职汇报发生月**（Q3 于 10 月初汇报写 `2026年10月`，Q2 于 7 月汇报写 `2026年7月`），与季度末月份解耦，避免与汇报时间不符。
3. **净工入口径标注**：SIT/UAT 时长若为净工时，必须写“净工时”并指引含等待期口径所在页（如 S2 写“SIT 净工时 1.97 天（含等待期口径详见 P7）”）。
4. **容量/资源战果上版**：`8.8T→1.8T（-79.5%）`、`日均压降 70%+` 这类“卸包袱”指标放在对应专项 stat-box/list-item，比纯表数更有杠杆感。
5. **不可比基线不编数字**：上季若为定性汇报（无同口径效能数值），禁止编“较上季度提升 X%”；改用季内前后对比（如 Story 拆分 7 次→5 次 -29%、确认轮次 -60%+）。
6. **结束页与模板完全一致**：结语页复刻《2026年第三季度工作述职汇报_xxx.pptx》模板最后一页——封面背景图（`tpl_image4.png`，cover-bg）+ 居中两行 `感谢聆听！` / `Thanks for listening！`（微软雅黑/苹方 36px 加粗白色，letter-spacing 3px/2px，两行 margin-top 4px；27pt=36px 为绝对单位等价，无需按画布等比放大）；**不加落款（部门—姓名）与承诺行**。flex 容器用 `left:53px; top:278px; width:1189px; height:130px; flex-direction:column; align-items:center; justify-content:center;` 使两行组中心与模板一致（页面 47.8% 处）。
7. **需求总量口径**：总量含在途（如 75 = 15 提出 + 60 在途）时，exec-summary 写“平稳推进 · 全流程闭环管理”，**禁止“全流程上线”**。
8. **技术前置单列**：需求数含技术前置/专项工具时明示（如 `20 个核心需求 + 1 项技术前置（独立撤单工具）`），防评审“这 21 个怎么只数出 20 个”的质疑。
9. **不要陈列未实际使用的接口/数量指标**：“41 个 MCP 接口”这类数字听着大气但实际使用寥寥，评审追问即穿帮，**禁止上版**；改用真实消耗、有数据支撑的量（如 Story 拆分调用 7 次→5 次 -29%），保留能力命名（kjptai MCP 需求自动化）但不放虚高计数。
10. **标题一律精简模式（正文页同样适用）**：h2 页面标题与卡片标题都不加「：副标题」（如 `集中交易去历史查询` 而不是 `集中交易去历史查询：卸负荷·清依赖·扫除信创核心路障`），标题末尾不留悬空冒号；战果数据下沉正文 stat-box / SCQA / list-item（2026Q3 定稿）。

---

## 数据一致性核查规范（Data Consistency Audit）

> 本规范源自 2026 Q3 述职实战教训：MD 与 PPT 未做双向数字互查，导致"85s→3s 写成提速 100 倍+"、Story 状态细分与总数矛盾等硬伤险些带进评审。**HTML 定稿与交付前，必须逐条执行以下核查。**

### 核查一：倍率计算公式（Multiplier Formula）

- **提速倍数 = 旧耗时 ÷ 新耗时**。示例：`85s ➔ 3s` = 85÷3 ≈ **28 倍**，不是"100 倍+"。
- **降幅百分比 =（旧 − 新）÷ 旧 × 100%**。示例：58s→22s = 36÷58 ≈ 62.07%，写 "约62%"（不是63%）；四舍五入精度须全文统一。
- 禁止在未完成验算前写入任何"倍 / 跃升 / 数量级"等程度词；拿不准就只写原始值（`85s ➔ 3s`，不写倍数）。

### 核查二：MD ↔ PPT 双向数字互查（Cross-Source Traceability）

- 交付前把源 MD 中**全部数字**抽成清单，逐一核对 PPT 每页 stat-box / 执行摘要 / 正文 / 架构图标签。
- 同一指标在 MD 与 PPT 必须**同值同精度**。本模板的 Q3 基准清单（抽数后逐项打勾）：
```
75 需求 | 15 提出 | 60 进行中 | 26.95 天 | 19.55 天 | 4.55 天 | 1.97 天 | 1.07 天 |
35.04% | 13 需求 16 系统 300+ 表 | 6 大下游（5×100% + 大数据 94.1%）|
339 表 6.16 亿行 150G | 12 需求 16 Story | 23 Story | 20 需求 5 期史诗 12+ 系统 |
58s→22s（约−62%）| 85s→3s（约28倍）| 8.8T→1.8T（−79.5%）日均压降 70%+ | QFII 20编号+1技术前置 | 75项口径=15提出+60在途
```

### 核查三："100%"表述规则（Absolute Claim Guard）

- 仅当指标**全集**均为 100% 时，才允许写 `100%`；只要存在任一非 100% 子项（如"大数据 94.1%"），一律使用 **"近100%"**。
- 若必须保留 100% 大字锚点，须在其 label/注释中给出例外项（如 `核心下游适配率（大数据94.1%）`）。
- 执行摘要与专项页同时检查，防止 S2 写"100%"、S3 正文却出现 94.1% 的当面穿帮。

### 核查四：小数精度统一（Precision Lock）

- 同一指标在同一版本内使用**同一精度**：`1.97` 不能写 `1.9`，`1.07` 不能写 `1.0`。
- 摘要页确需简写时，必须加"约"字（如"SIT 约 2 天"），或直接引用精确值。

### 核查五：合计算术自检（Sum Consistency）

- **分类状态之和必须等于总数**。若状态枚举未覆盖全部，用"其余 X 条按排期开发推进中"兜底（正面案例：16 条 Story = 8 UAT + 3 已结束 + 5 推进中；23 条 Story = 5 UAT + 2 验收/走查 + 16 推进中），禁止硬凑分割数字（反面案例：8+3+3+1=15 却宣称总数 16）。
- **环节拆解与端到端总时长**：拆解之和若 ≠ 端到端口径（如 32.19 vs 26.95），必须在该模块内添加口径注释——"分环节独立统计（含等待期），与净交付端到端口径不同，不直接相加"。

### 核查六：同页与跨页自洽（Same & Cross-Slide Coherence）

- 同一指标在 S2 执行摘要与具体专项页必须同值（如"约28倍"在 S2 与 S6 前后一致）。
- 页面底部架构流转图涉及的子项数字，必须与顶部 stat-box 同源（6 大下游 = 5 个 100% + 1 个 94.1%，"近100%"对应的是总和口径）。

### 校验动作（定稿前执行）

1. `search_relative` 全文搜索 `100倍/倍+/近100%/100%` 等关键词，逐一人工复核是否满足核查三；
2. 将 MD 数字清单与 PPT 各页 stat-box 做一次映射核对（核查二）；
3. 对含加法的模块逐项算和（核查五：Story 状态之和 = 总数，缺口用“其余 X 条推进中”补齐）；
4. 确认修改后重新渲染 PDF 并比对预览图，防止文字溢出/换行破坏版式；
5. 逐页检查：stitle 是否带个人角色标签、封面日期是否为述职当月、结语页是否与模板一致（优化要点 1/2/6）、所有页面/卡片标题是否均为精简模式（无“：副标题”残留，优化要点 10）。

---

## 效能度量页（S7）取数字典 · kjptai MCP（2026-11-11 实测校准）

> **页面标题（2026-11-11 用户定稿）：`本季度需求指标看板`；禁用旧名「科技平台交付效能度量实证」。**
> **图表产物**：`docs/本季度需求指标看板.svg`（16:9 矢量，可直接插入 PPT）+ 同名 `.html`（浏览器预览/打印）；生成脚本 `~/.workbuddy/skills/debrief-ppt-maker/scripts/gen_kpi_dashboard.py`（数据为 2026Q4 快照，换季度需同步更新脚本内数字）。固定版式：4 张 KPI 卡 + 版本排期柱状图 + 受理月份柱状图 + 状态分布参考条（标注不参与计数）+ 口径脚注。

> **铁律：看板「我提出/受理的需求总数」以科技平台「效能度量」页为准，禁止直接用 MCP 的 `startTime/endTime` 结果当受理总数。**

| 来源 | 时间口径 | 角色口径 |
| --- | --- | --- |
| 效能度量看板 | **最后一次需求受理时间**（横轴标注「需求提交/最后一次受理时间(month)」） | 主受理 + 共同受理，进行中 |
| `query_requirement` | `startTime/endTime` = 需求创建/提交时间；**无受理时间过滤字段** | `mineScope=accepted` |

**实测差异（2026-10 ~ 2026-11，截至 2026-11-11）**

| 月份 | 看板（按最后受理） | MCP（按提交） |
| --- | --- | --- |
| 2026-10 | 11 | 10 |
| 2026-11 | 2 | 1 |
| **合计** | **13** | **11** |

差的 2 条 = 提交时间早于 10 月、但最后一次受理发生在 10/11 月并落到本人名下的需求（受理转派 / 重新受理 / 后加共同受理人）。`receiveTime` 字段确实存在（`query_requirement_flow` 需求对象，例 R2609230112 = `2026-09-24 08:37:12`），但列表接口不暴露该过滤条件。

### 取数规则

1. **受理总数**：以看板为准，MCP 仅交叉校验。`mineScope=accepted` = 主受理 OR 共同受理（一次查询即可）；`receiverNames`（主受理）与 `commonReceiverNames`（共同受理）互斥且并集相等，**同时传是 AND，禁止用于 OR 统计**；不用 mineScope 时须分两次查询按需求编号去重。
2. **上线数（2026-11-11 用户最终口径）**：**只看「版本排期」字段，不看需求状态**；范围限定「我受理或共同受理」。`demandStatus` 仅作分布参考，**不参与计数/过滤**。
   - 数据源：交易结算核心系统需求集合大宽表（API `getSheetContent` 实时全量行；宽表为 Story 粒度）。
   - 字段：`storyPlanLineName` / `storyPlanLineDate`（版本排期名称 / 日期）、`demandReceiver`（受理人，主受理 + 共同受理逗号拼接）、`demandId`（去重键）。
   - 过滤链：`demandReceiver` 含本人 → `storyPlanLineDate` 落在季度内 → **排除 `2099-12-31` 与年末 `12-31` 占位值**（对应 BDNEW_3.0 / ZCFC_2026 / DK_V1.6 / 迭代65.0 等长期或历史版本名，Q4 共 9 行 / 8 个需求）→ 按 `demandId` 去重 → **去重后数量即上线数**。
   - 若用户要求「字面只按字段、含占位」，则给出含占位数字（Q4 = 61），并在脚注说明含年末默认占位。默认主口径用排除占位的 54。
   - **禁用**：`demandStatus = 已上线`（用户明确不按状态筛）、`planProdLineDate`（计划生产排期，Q4 实测 99 条，口径不同）、`esDuedate*`（预计上线时间，虚高）、`actualDuedate*`（实际交付验收时间，字段覆盖率低，Q4 仅 16 条，严重低估）。
3. **纯 MCP 复现看板受理数**：用 `query_requirement_flow` 逐条取需求对象 `receiveTime`，按季度区间过滤后按需求编号去重计数。
4. **PPT 口径标注**：写明「数据来源：科技平台效能度量看板 / 需求集合大宽表；受理口径：最后一次需求受理时间，含主受理与共同受理；上线口径：版本排期日期落在本季度，按需求编号去重，不按需求状态筛选；截至 YYYY-MM-DD」。季度未完结时写「平稳推进」，禁止「全流程上线」。
5. 不要上版 MCP 接口数量等虚高计数（见 Q3 优化要点 9）。

**上线数实测（实时全量 13,072 行，截至 2026-11-11 09:20）**

| 季度 | **上线数（只看版本排期，不看状态）** | 含年末 12-31 占位 | 参考：按状态已上线 | 旧口径（实际交付验收） |
| --- | --- | --- | --- | --- |
| 2026Q4 10/1–12/31 | **54** | 61 | 41 | 16 |
| 2026Q3 7/1–9/30 | **85** | 85 | 81 | 96（不同口径，不可比） |
| 2026 10/1–11/30 | **54** | 54 | 41 | — |

Q4（排除占位）按版本排期分组（去重需求数）：`20261009` 16、`20261023` 15、`20261106` 12、`20261120` 10、其余 3 个小版本 3；分组求和 56，跨版本重复 2 个需求，去重后 **54**。含占位时另有 `BDNEW_3.0` 5、`ZCFC_2026` 2、`DK_V1.6` 1、`迭代65.0` 1，去重后 61。
状态分布（仅供参考，不计数）：Q4 87 行中已上线 63 行，其余为 SIT 测试待排期 12 / SIT 生产测试待排期 4 / 待 SIT 生产测试 4 / 待开发集成 2 / 待 OA 审核 1 / Story 待处理 1；`20261120` 版本 10 个需求均未上线（版本日未到，Q4 为进行时数字）。
**历史修正**：上一版误把「仅标准 8 位日期版本名」子集的 Q3 81/79 当成 Q3 全量；Q3 全量应为 **85**（不看状态）/ 81（已上线）。旧状态口径 41（Q4）与旧验收口径 16 交集 15。

---

## 2026 Q3 历史季度看板变体（2026-11-11 落地）

- **脚本**：`~/.workbuddy/skills/debrief-ppt-maker/scripts/gen_kpi_dashboard_q3.py`（与 Q4 脚本并列，不改动 Q4 定稿）；支持 `--out` 指定产物目录。
- **产物**：`{PPT工作区}/docs/本季度需求指标看板_Q3.svg`、同名 `.html`、`q3_slide7_inner.html`（述职内页片段，含内联 CSS，插入时需把 `<style>` 拆到主 HTML 的 `<head>`）。
- **落版方式**：替换 `2026年三季度个人工作总结_吴进.html` 的 P7 `.bp` 内容，页眉标题改 `本季度需求指标看板`，目录页 P07 标题 / pill / desc 同步；`convert_html.py` 重导 PDF（12 页）。原 HTML/PDF 备份为 `*_v1_before_kpi.*`。重建时**始终从备份原件读取**再替换，保证幂等、不重复注入 CSS。
- **Q3 版式差异**：历史季度已完结，且暂无与 85 基线自洽的版本排期分组明细，故双图改为「按最后受理时间分布（33/24/18）」+「需求状态构成（60/7/8）」，保留 4 KPI 卡 + 状态分布参考条 + 口径脚注的固定骨架。**禁止为凑「版本排期柱状图」编造分组数字**（违反数据一致性核查五）。
- **数据出处**：受理 75 / 26.95 天 / 19.55 天 / 35.04% / 60·7·8 / 33·24·18 均来自效能度量看板 2026-07~09 原生截图；版本排期交付 85 沿用本节校准基线。60+7+8=75、33+24+18=75，我提出 15 项为子集不重复计数。
- **⚠️ 口径复核待办**：2026-11-11 10:47 用实时宽表（13,073 行）按 `demandReceiver` 含吴进 + `storyPlanLineDate` 落季度 + 排除占位 + 按 `demandId` 去重复现，Q3 = **50**、Q4 = **25**，与本节基线 85 / 54 不一致；整行匹配、含占位、按版本名、按历史受理 ID 回查等变体均无法复现。本次交付沿用用户拍板的 SKILL 基线 85 上版，**后续重算前须先与用户确认上午取数脚本的字段 / 数据源，不要直接替换基线数字**。

---

## 版本集成发布情况（S8）· 与需求指标看板同属「02 模块」（2026-11-11 新增）

> **页面定位**：紧接 S7「本季度需求指标看板」之后，统计本季度版本集成发布情况，图表化呈现。**两页共同纳入目录第 02 模块**，形成「需求流动 → 集成发布」的交付闭环叙事。

### 一、目录与页码重组规则

| 项 | 规则 |
| --- | --- |
| 02 模块标题 | `需求指标与版本集成发布（P07 ~ P08）` |
| 02 模块导航 pill | `06 本季度需求指标看板`、`07 版本集成发布情况`，另加 1 条指标 pill（如 `受理 75 · 排期 85 · 发版 27 次`） |
| 02 模块 desc | 同时写明需求指标与版本发布两个维度（如 `受理 75 项、版本排期交付 85 项；Q3 负责 10 个版本、27 次发版，已登记 0 起发版问题`） |
| 03 / 04 模块 | 页码区间顺延：`P08~P09 → P09~P10`、`P10~P11 → P11~P12`，模块内 pill 章节号 07→08、08→09、09→10、10→11 |
| 全篇页码 | 页脚 `x / 12` 按文档顺序重排为 `x / 13`（封面/结语无页脚）；`ht-num` 顺延 01~10；**压轴讨论页序号在 `.logo-box` 内（非 `ht-num`），须单独 10→11** |
| 新页页眉 | `ht-num=07`、`ht=版本集成发布情况`、`ht-tag=02 模块 · 集成发布实证` |

### 二、数据源与下载方式

- **在线文档**：全连接文档中心《各系统发版汇总》 `https://www.gtht.com.cn/jswps/weboffice/l/spULaQnvVBFlD`
- **登录**：访问任意 `www.gtht.com.cn/jswps/...` 会跳 `login.html`。用 `~/.workbuddy/skills/meet-minutes/config.json` 中 `mail.password`（Fernet，密钥 `~/.workbuddy/.meeting_skill_key`）解密，用户名 `wujin`；选择器 `input[placeholder*='Employee ID']` / `input[placeholder='Password']` / `button:has-text('Login')`。
- **会话复用**：登录后用 `context.storage_state(path=...)` 保存到 `~/.workbuddy/skills/debrief-ppt-maker/scripts/.wps_release_state.json`。**该文件含内网凭据，禁止外传或提交仓库**；后续请求用 `storage_state=` 直接复用。
- **下载 Excel**：打开 `https://www.gtht.com.cn/jswps/kdrive/latest`，定位文本 `各系统发版汇总.xlsx` → 右键 → `Download`（英文界面）→ `expect_download` 保存为 `docs/各系统发版汇总.xlsx`。也可复用 `bcp-progress-tracker/scripts/download_workbook.py` 的同款逻辑。

### 三、取数口径（铁律）

| 维度 | 规则 |
| --- | --- |
| 工作表 | 按季度取 3 个 `各系统{M}月版本`：Q3 = 7/8/9 月；sheet 名可能带尾随空格，先 `strip()` 再匹配 |
| 筛选 | 「发版负责人」(D 列) 含指定人，默认 `吴进` |
| 系统名 | A 列因合并单元格留空时**向下继承**（ffill）；`参数后台` / `参数中心` 按原表保留，**不强行归并**（避免臆断） |
| 版本数 | 有效行（B 版本排期或 D 负责人非空）计数，**按行计** |
| 发版次数 | 「发版次数」(F 列) 求和；非数字按 0 处理 |
| 发版问题 | 「是否有发版问题」(G 列) **仅作参考、不参与版本数计数**；空值不等于「无问题」，只统计已登记 `否/有/是` 的行，并在脚注写明未登记数量 |
| 占比 | `本人版本数 ÷ 全表有效行`，分母与口径必须写进脚注 |
| 严谨性 | 遵循「数据一致性核查」：分组之和 = 总数、同值同精度、不写全集 100% 类绝对表述；**禁止为凑图表编造明细** |

### 四、版式（16:9 图表页）

4 张 KPI 卡（负责版本 / 累计发版次数 / 覆盖系统 / 已登记发版问题）+ 左「月度版本发布分布」双系列柱状图（版本数深蓝 + 发版次数浅蓝，共用刻度）+ 右「按系统分布」横条 + 月度明细三卡（版本数 / 次数 / 系统构成）+ 两行口径脚注（含数据源 URL、工作表、筛选条件、空值说明、下载日期）。配色沿用品牌 token（`#1F497D` / `#0C72BB` / `#D9232E` / `#E6F1FB` / `#85B7EB`）。

### 五、脚本与命令模板（2026-11-11 已升级为按季度一键生成）

> **优先使用统一入口**（详见文末「02 模块按季度自动生成」专章）：
> `python $S/build_quarter_pages.py --quarter 2026Q3 [--refresh] [--probe]`
> 一条命令完成：下载/读取在线表 → 生成两页 SVG/HTML/内页片段 → 幂等落入主 HTML（P7+P8+目录+页码）→ 重导 PDF。

```bash
PY=/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python
S=~/.workbuddy/skills/debrief-ppt-maker/scripts

# 标准用法：按季度重生成 02 模块双页
$PY $S/build_quarter_pages.py --quarter 2026Q3 --refresh --probe
# --refresh  重新登录全连接下载最新《各系统发版汇总》
# --probe    额外输出实时宽表口径探测 JSON（只复核，不覆盖基线）
# --no-insert 只出图不改主 HTML；--no-pdf 不重导 PDF
```

**分步命令（排障时用）**：`fetch_release_workbook.py` → `gen_kpi_dashboard_q.py --quarter` → `gen_release_dashboard.py --quarter --months --tag` → `insert_quarter_pages.py --quarter` → `convert_html.py`。旧脚本 `gen_kpi_dashboard.py`(Q4 快照) / `gen_kpi_dashboard_q3.py`(Q3 快照) / `insert_release_slide.py` 保留供历史回溯，**新任务不要再改它们的硬编码常量**。

**换季度 checklist（新链路）**：① 在 `quarter_config.json → quarters` 补该季度的 `kpi` 基线并置 `ready=true`；② 一条 `build_quarter_pages.py --quarter YYYYQn --refresh`；③ 核对命令输出的「在线数据源变化」提示与目录 02 模块文案；④ 逐页核对页数/页码/无溢出。月份、tag、统计区间、目录页码、章节号、下载日期**全部自动推导，无需手改**。

### 六、2026 Q3 实测基线（现版：下载于 2026-11-11 13:50，一键链路重算）

| 指标 | 值 |
| --- | --- |
| 吴进负责版本 | **10** 个（全表 22 个版本，占 45.5%） |
| 累计发版次数 | **27** 次 |
| 按月 | 7 月 6 版 / 17 次；8 月 1 版 / 1 次；9 月 3 版 / 9 次 |
| 按系统 | 集中交易 5、参数后台 5（合计 10，**2 类**） |
| 发版问题 | 已登记 7 版均「否」→ **0 起**；9 月 3 版该字段为空，未纳入 |

6+1+3=10、17+1+9=27、5+5=10，三组算术自洽。

**⚠️ 数据源变更记录**：13:20 首版中 9 月表 A 列两行写「参数中心」，当时按原表保留为 3 类（集中交易 5 / 参数后台 3 / 参数中心 2），并留了「两者是否同一系统」的待定问题。13:50 重新下载发现维护者已把这两行统一改为「参数后台」，系统数自动变为 2 类。**这实际回答了待定问题**：按最新在线表，不再区分「参数中心」。旧版产物仍保留在 `*_v3_before_quarter_auto.*` 与 `docs/各系统发版汇总_20261111_1320.xlsx`。脚注已改为动态生成系统名，不再硬编码「参数后台 / 参数中心」。

### 七、复盘与已固化优化点

1. **插页幂等**：`insert_release_slide.py` 从母版备份重建，重复执行不会重复插页 / 重复注入 CSS；页码与章节号按文档出现顺序统一重排，避免手工改漏。
2. **压轴页特殊结构**：讨论页序号藏在 `.logo-box` 而非 `.ht-num`，已单独处理，防止顺延时漏改。
3. **空值不美化**：9 月「是否有发版问题」为空，脚注明确「未登记 ≠ 无问题」，避免写出「全季 0 事故」这类被评审一问即穿帮的绝对表述。
4. **图表可读性**：内页柱状图高度按季度最大值放大（系数 205），独立 SVG 固定 0~20 刻度，两者数值一致、比例不同源但不冲突。

---

## 02 模块按季度自动生成（2026-11-11 二次固化）

> **目标**：换季度不改脚本、不手算页码。给定 `--quarter`，一条命令生成并落版「本季度需求指标看板（S7）+ 版本集成发布情况（S8）」双页，自动同步目录 02 模块、全篇页码与章节号。

### 一、一键命令

```bash
PY=/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python
S=~/.workbuddy/skills/debrief-ppt-maker/scripts

$PY $S/build_quarter_pages.py --quarter 2026Q3 --refresh --probe
$PY $S/build_quarter_pages.py --quarter 2026Q4 --refresh        # 换季度：仅此一处变化
```

| 开关 | 作用 |
| --- | --- |
| `--refresh` | 重新登录全连接文档中心下载最新《各系统发版汇总》（默认复用本地 xlsx） |
| `--probe` | 额外输出 `probe_<quarter>.json` 实时宽表口径对照，**只复核、不覆盖基线** |
| `--no-insert` | 只生成两页 SVG/HTML/内页片段，不改主 HTML |
| `--no-pdf` | 不重导 PDF |

缺省即完成：读表 → 两页图表 → 幂等落入主 HTML → 重导 PDF。季度、月份（Q3=7/8/9）、tag、统计区间、已完结/进行中态、下载日期、目录页码、章节号**全部自动推导**。

### 二、脚本清单（均在 `~/.workbuddy/skills/debrief-ppt-maker/scripts/`）

| 脚本 | 职责 |
| --- | --- |
| `build_quarter_pages.py` | **统一编排入口**：按季度串起下列全部步骤，含数据源变化比对 |
| `quarter_config.json` | **唯一配置源**：季度基线、路径、目录锚点与文案模板、页面布局常量 |
| `gen_kpi_dashboard_q.py` | 参数化 S7：季度基线 → SVG / 预览 HTML / `kpi_slide_inner_<tag>.html`；内置一致性校验 |
| `fetch_release_workbook.py` | 内网登录 + 文档中心下载 xlsx（复用 `.wps_release_state.json`，权限 600） |
| `gen_release_dashboard.py` | 参数化 S8：读 Excel → SVG / 预览 HTML / `release_slide_inner_<tag>.html` / `release_stats_<tag>.json` |
| `insert_quarter_pages.py` | 从母版一次性替换 P7 + 插入 P8 + 目录 02 模块改写 + 页码/章节号重排 |
| `probe_quarter_metrics.py` | 实时宽表口径探测，输出对照 JSON（不写配置） |
| `convert_html.py` | HTML → PDF |
| 旧脚本 | `gen_kpi_dashboard.py`(Q4 快照)、`gen_kpi_dashboard_q3.py`(Q3 快照)、`insert_release_slide.py` 保留回溯，**不再维护其硬编码常量** |

### 三、配置结构（quarter_config.json）

- `paths`：`out_dir` / `main_html` / **`base_html`（12 页原始母版 `*_v1_before_kpi.html`，插页永远从它重建）** / `xlsx` / `wps_state` / `mail_config` / `mail_key`。
- `release_doc`：在线文档 URL、文档中心 URL、文件名、默认 `owner=吴进`。
- `layout`：`total_pages=13` / `kpi_page=7` / `release_page=8` / `kpi_num=06` / `release_num=07` / `insert_before` 锚点。
- `base_agenda`：母版目录页原文锚点（02 标题/desc、03/04 页码区间与 pill 序号）。**换母版时改这里，不改脚本。**
- `agenda_tpl`：02 模块新标题与文案模板，支持 `{accept} {release} {tag} {versions} {times} {problems}` 占位符，数字由当季配置 + Excel 现场统计注入。
- `quarters.<YYYYQn>`：`ready`（是否可生成）+ `kpi` 基线：`accept_total`、`accept_months`、`release_total`、`e2e_days`、`it_days`、`flow_eff`、`status`、**`proposed`**、`month_note`、`foot1`、`foot2`。

**内置门禁**：`ready=false` 或缺任一必需字段 → 直接报错并列出缺失；`sum(accept_months)` 与 `sum(status)` 必须都等于 `accept_total`，否则拒绝生成。遵守「数据一致性核查」「禁止为凑图表编造明细」。

### 四、两条数据链路的边界（铁律）

| 页 | 数据来源 | 自动化程度 |
| --- | --- | --- |
| S7 需求指标看板 | 科技平台**效能度量看板季度截图**（受理数、时长、效率、月份/状态分布）+ 用户拍板的**版本排期基线** | **半自动**：数字写入 `quarter_config.json` 一次，之后按季度复用；脚本不抓取、不估算、不用 probe 值覆盖 |
| S8 版本集成发布 | 全连接文档中心《各系统发版汇总》在线表，按季度取 3 个工作表、筛 `发版负责人` | **全自动**：`--refresh` 登录后下载 xlsx → 解析 → 图表 → 目录文案 |

> 原因：效能度量看板无稳定取数接口，且实时宽表复算与拍板基线存在差异（见第八节）。**任何情况下不得把 probe 值静默写回配置，也不得为缺字段填估算值。**

### 五、新季度接入流程（ Checklist ）

1. 取该季度效能度量看板原生截图，记录受理数、月份分布、状态构成、端到端/IT 交付、流动效率、版本排期交付数。
2. 在 `quarter_config.json → quarters` 新增 `"YYYYQn"` 段，填 `kpi` 全部字段，`ready: true`；未知字段写 `null` 并保持 `ready: false`（脚本会拒绝生成）。
3. 若换了新的述职母版或目录文案，同步 `paths.main_html` / `paths.base_html` / `base_agenda` / `agenda_tpl` / `layout.total_pages`。
4. 跑 `$PY $S/build_quarter_pages.py --quarter YYYYQn --refresh --probe`。
5. 看输出的 **「在线数据源变化」** 提示与目录 02 模块 desc；逐页核对页数、页码、零溢出（第十节）。
6. 汇报时若系统名/分组被维护者改名，带一句说明，旧 xlsx 与旧 HTML/PDF 留备份。

### 六、幂等、目录与页码规则

`insert_quarter_pages.py` **永远从 `base_html`（12 页原始母版）读取**重建，因此重复执行不会重复插页或重复注入 CSS。一次完成：两段 CSS 注入 head → P7 标题/tag/`.bp` 替换 → SLIDE 8 前插 P8 → 02 模块改为「需求指标与版本集成发布（P07~P08）」双页导航、03/04 模块页码与 pill 序号 +1 → 页脚 `x/13`、`ht-num` 01~10、压轴讨论页 `.logo-box` 内序号 10→11、注释编号顺延。生成后校验 `slides == total_pages`，旧标题残留为 0。

### 七、数据源变化自动比对

`gen_release_dashboard.py` 每次输出 `release_stats_<tag>.json`（版本数/次数/系统分布/月度/问题/占比）；`build_quarter_pages.py` 运行前后读取快照，若 `total / times / systems / by_system / by_month / registered / problems / all_versions` 有变化，打印 `⚠ 在线数据源变化: 旧 → 新` 并要求在汇报中说明。**2026-11-11 实测生效**：9 月表「参数中心」被维护者统一改为「参数后台」，系统数 3→2，脚注同步改为动态系统名。

### 八、口径探测与已知差异

`$PY $S/probe_quarter_metrics.py --quarter 2026Q3`：拉实时宽表（本次 13,076 行），按 `demandReceiver` 含吴进 + `storyPlanLineDate` 落季度 + 排除占位 + `demandId` 去重，输出 `probe_<quarter>.json`。**Q3 复算 49 项，与基线 85 不一致，差异仍待与用户确认上午取数脚本字段/数据源后再处理。**

教训已固化：宽表里没有「受理时间」字段，时间类字段多为计划/完成日期，**只允许字段名含 `receiv`/`accept` 时输出受理月份**，否则明确标注「未输出」——绝不把 `demandEsDuedate` 之类误当受理月份（本次已修正）。

### 九、季度配置状态

| 季度 | ready | 说明 |
| --- | --- | --- |
| `2026Q3` | ✅ true | 受理 75 / 排期 85 / 26.95 天 / 19.55 天 / 35.04%；月份 33·24·18，状态 60·7·8，提出 15 项为子集 |
| `2026Q4` | ❌ false | 为进行时，已知受理 13 / 排期 54 / 覆盖版本 7 / 月份 10 月 11、11 月 2；**缺 `status`、`e2e_days`、`it_days`、`flow_eff`、`proposed`**，等效能看板季度数据齐备后补齐并置 true |

### 十、验证清单（每次生成后）

- 主 HTML `.slide` 数 = `total_pages`；P7 标题「本季度需求指标看板」、P8「版本集成发布情况」；旧标题零残留。
- 逐页 `scrollHeight <= clientHeight + 1`（含 `.q3kpi-wrap` / `.rel-wrap` 内层），页脚 `02/13 … 12/13` 连续，`ht-num` 01~10 连续。
- PDF 页数 = `total_pages`，每页均可抽取文本；目录 02 模块含两个页面导航 + 1 条指标 pill。
- 两页独立 SVG/HTML 与内页截图目视检查：数字、柱高、状态条、脚注无重叠截断。

### 十一、复盘与已固化优化点

1. **配置驱动取代硬编码**：Q3 快照脚本里 11 个模块常量、插页脚本里 11 条 `AGENDA_REPL` 全部抽出，换季度只改配置 + 一个参数；一键链路实跑后**除数据源变更影响的 P8 外，其余 12 页渲染文本与交付版逐字一致**。
2. **数据边界写进规范**：明确「发布页全自动 / 指标页半自动」，避免误以为可以全自动抓数而拿错口径上版。
3. **变化可观测**：统计快照比对让在线文档被维护者改名/补录时自动暴露，避免悄悄变数。
4. **口径不误标**：probe 只在字段名可信时输出受理月份，其余明确写「未输出」。
5. **质量门禁内建**：一致性校验（月份和、状态和 = 受理总数）与 `ready` 开关，杜绝为凑版式编数字。
