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
| 主蓝深 | 页眉色块、标题 | `#1F497D` |
| 主蓝亮 | 按钮、卡片边框 | `#0C72BB` |
| 品牌蓝 | 分割线、图标 | `#4F81BD` |
| 深蓝2 | 标题文字 | `#004E97` |
| 正文灰 | 副标题、页脚 | `#999999` |
| 背景色 | 内页底色 | `#FFFFFF` |
| 卡片底 | 内容卡片背景 | `#f5f8fc` |

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

/* 新增：板块条块规划组件 (layout_domain_planner - 垂直撑满无下部空洞) */
.planner-list{flex:1;display:flex;flex-direction:column;justify-content:space-between;gap:12px;margin-bottom:4px;}
.planner-row{flex:1;display:flex;align-items:stretch;gap:16px;}
.planner-tag{width:210px;flex-shrink:0;border-radius:4px;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:10px 14px;text-align:center;color:#ffffff;box-shadow:0 2px 6px rgba(0,0,0,0.06);}
.planner-tag.tag-dark{background:#232a36;}
.planner-tag.tag-navy{background:#1F497D;}
.planner-tag.tag-blue{background:#0C72BB;}
.planner-tag.tag-cyan{background:#4F81BD;}
.planner-tag .tag-badge{font-size:10px;background:rgba(255,255,255,0.2);padding:1px 6px;border-radius:2px;margin-bottom:4px;letter-spacing:0.5px;}
.planner-tag .tag-title{font-size:13.5px;font-weight:700;letter-spacing:0.5px;line-height:1.35;}
.planner-content.dashed-box{flex:1;border:1.5px dashed #4F81BD;border-radius:4px;background:#fbfdff;padding:10px 18px;display:flex;flex-direction:column;justify-content:center;gap:5px;}
.p-item{font-size:12.2px;color:#333333;line-height:1.55;display:flex;align-items:flex-start;}
.p-num{font-weight:700;color:#004E97;margin-right:6px;flex-shrink:0;}

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

### 法则一：结论先行与动词定调（Headline Rule）
- ❌ **禁止使用空泛模块标题**：如“核心业务专项一”、“系统优化”、“效能度量”。
- ✅ **所有页面与卡片标题统一精简模式**（不带冒号副标题）：`集中交易去历史查询`、`产品经理个人驾驶舱`、`需求分析 SKILL 自动化流水线`、S2 卡片 `01 核心业务专项攻坚`；战果/判断句（卸负荷、一屏控风险等）下沉到正文 stat-box、SCQA 卡片与 list-item 呈现（2026Q3 定稿）。

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

述职演示文稿标准为 10 页高光体系，支持按内容灵活组合：

| 页 | 类型 | 推荐版式 | 叙事重点 |
|----|------|---------|---------|
| S1 | 封面 | 原版封面 | `tpl_image4.png` + 极简大标题 + 汇报人/部门/日期（**不加定调副标题**） |
| S2 | 目录与战果 | **目录 + 战果总览条** | 顶部 Executive Summary 4大金黄核心锚点 + 四大模块索引 |
| S3 | 核心专项① | **SCQA 战役解构卡** | 顶部 4 大看板 + 红绿痛点价值对比 + 底部架构流转图 |
| S4 | 核心专项②&③ | **左右双专项协同卡** | 两融流转优化（压降资金占用偏差）+ Y核心内切（平稳并轨底座） |
| S5 | 数字化实践 | **管理范式跃迁三栏卡** | 冷加载 -63% + 过去vs现在对比 + 3 级穿透 |
| S6 | AI 生产力 | **流水线与质量红线双栏** | AI 自动化流水线 + 源码提速约 28 倍 + 制度化红线 |
| S7 | 效能度量 | **数据看板与机制归因** | 73 项需求平稳流动 + 34.02% 流动效率 + 根本归因 |
| **S8 (高光)** | **难点与对策** | **`layout_challenge_solution`** | **实战还原：左难点(竖标+问题)+右建议(竖标+机制解法)** |
| **S9 (战略)** | **战略路线图** | **`layout_domain_planner`** | **实战还原：四大业务板块色卡 + 虚线编号战役路线图** |
| S10 | 结语 | 原版结语 | `tpl_image4.png` + 感谢聆听居中 |

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

#### 3. 板块条块规划矩阵 (`layout_domain_planner`)
```html
<div class="planner-list">
  <div class="planner-row">
    <div class="planner-tag tag-dark">
      <span class="tag-badge">核心业务域</span>
      <span class="tag-title">集中交易系统<br>持续演进</span>
    </div>
    <div class="planner-content dashed-box">
      <div class="p-item"><span class="p-num">1)</span> 推进商品期货期权全量业务迁移，年内实现商品业务估值单轨运行。</div>
      <div class="p-item"><span class="p-num">2)</span> 推进ETF做市业务UAT用户验收，达到业务上线标准。</div>
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

### 规则四：`#4F81BD` 的正确用法

`#4F81BD`（品牌蓝）**仅适合白/浅色背景**，禁止用在深蓝背景上：

- ✅ 正确：页眉分割线（白底上）、进度条、小 tag 文字（浅底）
- ❌ 禁止：深蓝背景上的数字、图标、标签（会隐形）

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
