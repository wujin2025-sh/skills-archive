---
name: debrief-ppt-maker
description: 专业述职PPT制作技能。根据用户提供的工作大纲，基于默认模板自动生成完整HTML述职演示文稿。触发词：述职PPT、述职报告、工作汇报PPT、季度总结PPT、年度述职、阶段汇报、slide_edit、slide_present。
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
.bp{padding:20px 48px 48px 48px;min-height:616px;}
.stitle{display:flex;align-items:center;gap:12px;margin-bottom:24px;}
.stitle .bar{width:5px;height:32px;background:linear-gradient(180deg,#0C72BB,#1F497D);border-radius:3px;}
.stitle h2{font-size:22px;font-weight:700;color:#004E97;letter-spacing:1px;}
.stitle .tag{font-size:11px;background:rgba(12,114,187,0.1);color:#0C72BB;border:1px solid rgba(12,114,187,0.3);border-radius:3px;padding:2px 8px;margin-left:8px;}
.stat-box{text-align:center;background:linear-gradient(135deg,#1F497D,#0C72BB);border-radius:10px;padding:20px 16px;color:#fff;}
.card{background:#f5f8fc;border-radius:8px;border-left:4px solid #0C72BB;padding:18px 22px;}
.badge{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;background:#0C72BB;color:#fff;border-radius:50%;font-size:11px;font-weight:700;}
.pfill{height:8px;border-radius:4px;background:linear-gradient(90deg,#1F497D,#0C72BB);}
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
1. **高保真 PDF 导出**：自动在页面注入 `@media print` 样式，隐藏导航栏并规范分页，调用 Playwright 原生 PDF 打印引擎，输出文字可选择的、完美高保真的 PDF 矢量文档。

#### 运行命令
```bash
python3 /Users/wujin/.gemini/config/skills/debrief-ppt-maker/scripts/convert_html.py /path/to/slide.html
```
*(或者使用 `workbuddy` 技能目录下的脚本：`python3 /Users/wujin/.workbuddy/skills/debrief-ppt-maker/scripts/convert_html.py /path/to/slide.html`)*

## 常用指令

| 指令 | 说明 |
|------|------|
| `slide_initialize` | 提取模板背景图，初始化 CSS 设计体系 |
| `slide_edit` | 编辑指定页：询问哪张页 + 改什么。禁止 padding-bottom，使用 min-height |
| `slide_present` | 生成/更新完整 HTML，确认文件大小 |
| `slide_export_pdf` | 调用 `convert_html.py` 脚本，将生成的 HTML 转换为同名 PDF 矢量文档 |

## 标准页面清单（9页）

| 页 | 类型 | 布局 |
|----|------|------|
| S1 | 封面 | tpl_image4.png + 精确坐标文字叠加 |
| S2 | 目录 | 2×2 卡片索引，左侧编号渐变色块 |
| S3 | 核心专项① | 左右双栏 + 底部数据流示意 |
| S4 | 核心专项② | 双栏卡片 + 逻辑对比示意图 |
| S5 | 系统优化 | 三栏卡片 |
| S6 | 效能度量 | 4大数据看板 + 左指标/右系统截图 |
| S7 | AI实践 | 左图标矩阵 + 右人机分工对比 |
| S8 | 下阶段规划 | 双栏规划卡 + 里程碑路线图 |
| S9 | 结语 | tpl_image4.png + 感谢聆听居中 |

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
