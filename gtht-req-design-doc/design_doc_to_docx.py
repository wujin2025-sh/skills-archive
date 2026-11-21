#!/usr/bin/env python3
"""
设计文档 Markdown → 国泰海通标准格式 Word 文档转换器
基于参考文档（PG202204-0215 等）的格式规范，生成含封面页、自动编号标题、目录的标准 .docx

用法:
  python3 design_doc_to_docx.py <input.md> <output.docx> [--title "文档标题"] [--epic "史诗编号"] [--author "吴进"] [--dept "技术研发部"]

依赖: python-docx, pandoc (系统命令), mmdc (Mermaid CLI, 可选)
"""

import argparse
import os
import re
import sys
import subprocess
import tempfile
import shutil
import json
from pathlib import Path
from copy import deepcopy
from lxml import etree

# python-docx
from docx import Document
from docx.shared import Inches, Pt, Cm, Twips, RGBColor, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml

# ─── 常量 ───
W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
WP_NS = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
A_NS = 'http://schemas.openxmlformats.org/drawingml/2006/main'
PIC_NS = 'http://schemas.openxmlformats.org/drawingml/2006/picture'

# 国泰海通标准格式参数
FONT_BODY_CN = '宋体'        # 正文中文
FONT_BODY_EN = 'Times New Roman'  # 正文英文
FONT_HEADING_CN = '黑体'      # 标题中文
FONT_HEADING_EN = 'Arial'     # 标题英文
FONT_COVER_TITLE = '黑体'    # 封面标题
FONT_COVER_SUB = '楷体'      # 封面副标题
FONT_META = '宋体'           # 封面元信息

SZ_BODY = 24          # 12pt (half-points)
SZ_H1 = 32            # 16pt
SZ_H2 = 28            # 14pt
SZ_H3 = 28            # 14pt
SZ_H4 = 28            # 14pt
SZ_COVER_TITLE = 44   # 22pt
SZ_COVER_SUB = 44     # 22pt
SZ_COVER_META = 28    # 14pt
SZ_REV_TABLE = 21     # 10.5pt
SZ_TOC = 24           # 12pt

COLOR_GRAY_BG = 'D9D9D9'  # 封面标题背景灰 / 表头背景灰
COLOR_HEADING = '000000'  # 标题颜色（黑色）
COLOR_WHITE = 'FFFFFF'
COLOR_ZEBRA = 'E8E8E8'       # 斑马纹浅灰（加深以提升可见度）
COLOR_HEADER_TEXT = '1F4E79'  # 表头深蓝色
COLOR_HEADER_BORDER = 'BFBFBF'  # 表头分隔线灰
COLOR_IMG_BG = 'F8F9FA'     # 图片背景极浅灰
COLOR_IMG_BORDER = 'D0D0D0'  # 图片边框灰
COLOR_STATUS_GREEN = '2E7D32'  # 已上线绿色
COLOR_STATUS_ORANGE = 'E65100'  # 待上线橙色
COLOR_STATUS_GRAY = '757575'  # 无状态灰色


def run_pandoc(input_md, output_docx, ref_doc=None, resource_path='.'):
    """运行 pandoc 将 Markdown 转为 docx"""
    cmd = [
        'pandoc',
        '--from', 'markdown+pipe_tables+raw_html-implicit_figures-inline_notes',
        '--to', 'docx',
        '--resource-path', resource_path,
    ]
    if ref_doc and os.path.exists(ref_doc):
        cmd += ['--reference-doc', ref_doc]
    cmd += ['--output', output_docx, input_md]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"pandoc error: {result.stderr}", file=sys.stderr)
        raise RuntimeError(f"pandoc failed: {result.returncode}")
    return output_docx


def render_mermaid_diagrams(md_content, work_dir):
    """提取并渲染 Mermaid 图为 PNG，返回 (processed_md, image_paths)"""
    mermaid_pattern = re.compile(r'```mermaid\n(.*?)```', re.DOTALL)
    matches = list(mermaid_pattern.finditer(md_content))
    if not matches:
        return md_content, {}
    
    image_map = {}  # index -> path
    managed_node = '/Users/wujin/.chat/runtimes/darwin-x64/node/versions/22.22.2/bin/node'
    mmdc_src = '/usr/local/Cellar/mermaid-cli/11.15.0/libexec/lib/node_modules/@mermaid-js/mermaid-cli/src/cli.js'
    mmdc_dir = '/usr/local/Cellar/mermaid-cli/11.15.0/libexec/lib/node_modules/@mermaid-js/mermaid-cli'
    puppeteer_config = os.path.join(work_dir, 'puppeteer-config.json')
    
    # Write puppeteer config
    with open(puppeteer_config, 'w') as f:
        json.dump({
            "executablePath": "/Users/wujin/Library/Caches/ms-playwright/chromium_headless_shell-1223/chrome-headless-shell-mac-x64/chrome-headless-shell",
            "args": ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        }, f)

    # Write mermaid config (larger font for readability)
    mermaid_config = os.path.join(work_dir, 'mermaid-config.json')
    with open(mermaid_config, 'w') as f:
        json.dump({
            "theme": "base",
            "themeVariables": {
                "fontSize": "20px",
                "fontFamily": "'SimHei', 'Microsoft YaHei', 'PingFang SC', sans-serif"
            },
            "flowchart": {
                "nodeSpacing": 60,
                "rankSpacing": 80,
                "padding": 20
            }
        }, f)
    
    # Render each diagram
    for i in range(len(matches) - 1, -1, -1):
        match = matches[i]
        diagram_code = match.group(1)
        img_name = f'diagram{i+1}.png'
        img_path = os.path.join(work_dir, img_name)
        mmd_path = os.path.join(work_dir, f'diagram{i+1}.mmd')
        
        with open(mmd_path, 'w', encoding='utf-8') as f:
            f.write(diagram_code.strip())
        
        # Extract descriptive title from the heading before the mermaid block
        # Look backwards from match.start() for the nearest ### heading
        preceding_text = md_content[:match.start()]
        heading_lines = [l for l in preceding_text.split('\n') if l.strip().startswith('#')]
        diagram_title = f'图{i+1}'
        if heading_lines:
            last_heading = heading_lines[-1].strip()
            # Remove # markers and numbering
            clean_heading = re.sub(r'^#+\s*', '', last_heading)
            clean_heading = re.sub(r'^[\d.、]+\s*', '', clean_heading)
            diagram_title = f'图{i+1}  {clean_heading}'
        
        env = os.environ.copy()
        env['NODE_PATH'] = os.path.join(mmdc_dir, 'node_modules')
        env['TMPDIR'] = '/tmp'
        result = subprocess.run(
            [managed_node, mmdc_src, '-i', mmd_path, '-o', img_path,
             '-p', puppeteer_config, '-c', mermaid_config,
             '-b', 'white',
             '-w', '3200', '-H', '1800', '--scale', '3'],
            capture_output=True, text=True, env=env, timeout=60
        )
        
        if result.returncode == 0 and os.path.exists(img_path):
            image_map[i+1] = img_path
            # Replace mermaid block with image reference (descriptive alt text)
            md_content = md_content[:match.start()] + f'![]({img_name})' + md_content[match.end():]
        else:
            print(f"Warning: Failed to render Mermaid diagram {i+1}: {result.stderr}", file=sys.stderr)
            # Keep as code block
            md_content = md_content[:match.start()] + f'```\n{diagram_code}```' + md_content[match.end():]
    
    return md_content, image_map


def preprocess_markdown(md_content):
    """预处理 Markdown: 替换 wikilinks, 清理 Obsidian 语法"""
    # Replace [[wikilinks]] with plain text
    def replace_wikilink(m):
        inner = m.group(1)
        if '|' in inner:
            return inner.split('|', 1)[1]
        return inner
    md_content = re.sub(r'\[\[([^\]]+)\]\]', replace_wikilink, md_content)
    
    # Replace ![[embeds]] with reference text
    md_content = re.sub(r'!\[\[([^\]]+)\]\]', lambda m: f'（参考：{m.group(1)}）', md_content)
    
    # Convert Obsidian callouts to blockquotes
    md_content = re.sub(r'> \[!\w+\]', '>', md_content)
    
    return md_content


def add_cover_page(doc, title, subtitle, epic_no, author, dept, date_str):
    """在文档开头插入封面页"""
    body = doc.element.body
    
    # Create cover page as XML elements inserted before existing content
    # We'll build the cover as a table
    
    # ── 封面标题表格 ──
    cover_tbl = doc.add_table(rows=4, cols=1)
    cover_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    
    # Set table width and no borders
    tbl_pr = cover_tbl._element.find(qn('w:tblPr'))
    if tbl_pr is None:
        tbl_pr = parse_xml(f'<w:tblPr {nsdecls("w")}><w:tblW w:w="9072" w:type="dxa"/><w:jc w:val="center"/><w:tblLayout w:type="fixed"/></w:tblPr>')
        cover_tbl._element.insert(0, tbl_pr)
    
    # Remove borders
    borders_xml = f'''<w:tblBorders {nsdecls("w")}>
        <w:top w:val="none" w:sz="0" w:space="0" w:color="auto"/>
        <w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>
        <w:bottom w:val="none" w:sz="0" w:space="0" w:color="auto"/>
        <w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>
        <w:insideH w:val="none" w:sz="0" w:space="0" w:color="auto"/>
        <w:insideV w:val="none" w:sz="0" w:space="0" w:color="auto"/>
    </w:tblBorders>'''
    tbl_pr.append(parse_xml(borders_xml))
    
    # Row 0: Title (gray background, centered, bold, large)
    cell0 = cover_tbl.cell(0, 0)
    cell0.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    # Gray background
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{COLOR_GRAY_BG}"/>')
    cell0._element.find(qn('w:tcPr')).append(shd)
    # Add cell margins (top/bottom padding to prevent font clipping)
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="400" w:type="dxa"/><w:bottom w:w="400" w:type="dxa"/><w:left w:w="200" w:type="dxa"/><w:right w:w="200" w:type="dxa"/></w:tcMar>')
    cell0._element.find(qn('w:tcPr')).append(tcMar)
    # Set row height (generous to prevent font clipping; 4000 twips ≈ 7cm)
    tr0 = cover_tbl.rows[0]._element
    trpr0 = parse_xml(f'<w:trPr {nsdecls("w")}><w:trHeight w:val="4000" w:hRule="atLeast"/></w:trPr>')
    tr0.insert(0, trpr0)
    
    p0 = cell0.paragraphs[0]
    p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
    # Add paragraph spacing to prevent clipping
    p0.paragraph_format.space_before = Pt(12)
    p0.paragraph_format.space_after = Pt(12)
    run0 = p0.add_run(title)
    run0.font.name = FONT_COVER_TITLE
    run0.font.size = Pt(SZ_COVER_TITLE / 2)
    run0.bold = True
    run0._element.rPr.rFonts.set(qn('w:eastAsia'), FONT_COVER_TITLE)
    # Ensure line spacing is adequate
    p0_pf = p0.paragraph_format
    p0_pf.line_spacing = Pt(SZ_COVER_TITLE / 2 * 1.5)
    
    # Add subtitle if provided
    if subtitle:
        p0_sub = cell0.add_paragraph()
        p0_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p0_sub.paragraph_format.space_before = Pt(6)
        p0_sub.paragraph_format.space_after = Pt(12)
        run_sub = p0_sub.add_run(subtitle)
        run_sub.font.name = FONT_COVER_TITLE
        run_sub.font.size = Pt(SZ_COVER_TITLE / 2)
        run_sub.bold = True
        run_sub._element.rPr.rFonts.set(qn('w:eastAsia'), FONT_COVER_TITLE)
        p0_sub.paragraph_format.line_spacing = Pt(SZ_COVER_TITLE / 2 * 1.5)
    
    # Row 1: Logo placeholder (empty, tall)
    cell1 = cover_tbl.cell(1, 0)
    tr1 = cover_tbl.rows[1]._element
    trpr1 = parse_xml(f'<w:trPr {nsdecls("w")}><w:trHeight w:val="3985" w:hRule="atLeast"/></w:trPr>')
    tr1.insert(0, trpr1)
    p1 = cell1.paragraphs[0]
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run1 = p1.add_run('\n')
    
    # Row 2: Metadata (epic number, department, date)
    cell2 = cover_tbl.cell(2, 0)
    tr2 = cover_tbl.rows[2]._element
    trpr2 = parse_xml(f'<w:trPr {nsdecls("w")}><w:trHeight w:val="2000" w:hRule="atLeast"/></w:trPr>')
    tr2.insert(0, trpr2)
    
    meta_lines = []
    if epic_no:
        meta_lines.append(f'史诗编号：{epic_no}')
    meta_lines.append(f'{dept}')
    meta_lines.append(f'{date_str}')
    
    for line in meta_lines:
        p = cell2.add_paragraph() if cell2.paragraphs[0].text else cell2.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(line)
        run.font.name = FONT_META
        run.font.size = Pt(SZ_COVER_META / 2)
        run._element.rPr.rFonts.set(qn('w:eastAsia'), FONT_META)
        p.paragraph_format.space_after = Pt(6)
    
    # Row 3: Revision record table placeholder (will be separate table)
    # Actually, we'll add the revision table as a separate table below
    
    # Move cover table to the very beginning
    body.remove(cover_tbl._element)
    body.insert(0, cover_tbl._element)
    
    # Add a paragraph after cover table (spacer)
    spacer = doc.add_paragraph()
    body.remove(spacer._element)
    body.insert(1, spacer._element)


def add_revision_table(doc, rev_entries, after_element=None):
    """添加修订记录表"""
    body = doc.element.body
    
    rev_tbl = doc.add_table(rows=1 + len(rev_entries), cols=5)
    rev_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    
    # Set table style to grid
    rev_tbl.style = 'Table Grid'
    
    # Header row
    headers = ['日期', '版本', '修订人', '修订说明', '审核人']
    for i, header in enumerate(headers):
        cell = rev_tbl.cell(0, i)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = cell.paragraphs[0].add_run(header)
        run.bold = True
        run.font.size = Pt(SZ_REV_TABLE / 2)
        run.font.name = FONT_BODY_CN
        run._element.rPr.rFonts.set(qn('w:eastAsia'), FONT_BODY_CN)
        # Gray header background
        shd = parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{COLOR_GRAY_BG}"/>')
        cell._element.find(qn('w:tcPr')).append(shd)
    
    # Data rows
    for row_idx, entry in enumerate(rev_entries):
        for col_idx, val in enumerate(entry):
            cell = rev_tbl.cell(row_idx + 1, col_idx)
            run = cell.paragraphs[0].add_run(str(val))
            run.font.size = Pt(SZ_REV_TABLE / 2)
            run.font.name = FONT_BODY_CN
            run._element.rPr.rFonts.set(qn('w:eastAsia'), FONT_BODY_CN)
    
    # Move to after cover if specified
    if after_element is not None:
        body.remove(rev_tbl._element)
        after_element.addnext(rev_tbl._element)
    
    return rev_tbl._element


def add_page_break(doc):
    """添加分页符"""
    p = doc.add_paragraph()
    run = p.add_run()
    run.add_break(docx.enum.text.WD_BREAK.PAGE)
    return p._element


def add_toc_field(doc, after_element=None):
    """添加 Word 目录域（TOC field）
    
    Args:
        after_element: 如果提供，TOC 将插入到该元素之后；否则追加到 body 末尾。
    """
    body = doc.element.body
    
    # TOC title
    toc_title = doc.add_paragraph()
    toc_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = toc_title.add_run('目录')
    run.bold = True
    run.font.size = Pt(SZ_H1 / 2)
    run.font.name = FONT_HEADING_CN
    run._element.rPr.rFonts.set(qn('w:eastAsia'), FONT_HEADING_CN)
    
    # TOC field
    # The TOC field XML
    toc_xml = f'''<w:p {nsdecls("w")}>
        <w:r>
            <w:fldChar w:fldCharType="begin" w:dirty="true"/>
        </w:r>
        <w:r>
            <w:instrText xml:space="preserve"> TOC \\o "1-3" \\h \\z \\u </w:instrText>
        </w:r>
        <w:r>
            <w:fldChar w:fldCharType="separate"/>
        </w:r>
        <w:r>
            <w:t>右键点击此处选择"更新域"以生成目录</w:t>
        </w:r>
        <w:r>
            <w:fldChar w:fldCharType="end"/>
        </w:r>
    </w:p>'''
    
    toc_para = parse_xml(toc_xml)
    
    if after_element is not None:
        # Insert TOC title and field after the given element
        # Order: after_element → toc_title → toc_para
        after_element.addnext(toc_para)
        after_element.addnext(toc_title._element)
    else:
        body.append(toc_para)
    
    # Return the last inserted element (toc_para) for chaining
    return toc_para


def strip_heading_number(text):
    """去除标题文本中已有的编号前缀，以便使用 Word 自动编号
    
    例：
      '第 1 章 概述与背景' → '概述与背景'
      '1.1 业务背景' → '业务背景'
      '3.1.1 负债偿还规则跨系统对比' → '负债偿还规则跨系统对比'
      '第 3 章 功能模块设计' → '功能模块设计'
    """
    # 去除 "第 X 章 " 前缀
    text = re.sub(r'^第\s*\d+\s*章\s*', '', text)
    # 去除 "X.Y.Z " 或 "X.Y " 前缀（数字+点号+空格）
    text = re.sub(r'^\d+(\.\d+)*\s+', '', text)
    # 去除 "附录" 前缀保留
    return text.strip()


def apply_heading_numbering(doc):
    """为标题段落添加自动编号（1、 1.1 1.1.1 格式）"""
    # We need to add numbering definitions to the document
    # and reference them in heading paragraphs
    
    numbering_part = doc.part.numbering_part
    if numbering_part is None:
        from docx.oxml.numbering import CT_Numbering
        numbering_part = doc.part.numbering_part
    
    numbering_elem = numbering_part.element
    
    # Check if we already have a suitable abstractNum
    # Create abstract numbering for heading auto-numbering: 1、 1.1 1.1.1
    abstract_id = _get_next_abstract_num_id(numbering_elem)
    
    abstract_xml = f'''<w:abstractNum {nsdecls("w")} w:abstractNumId="{abstract_id}">
        <w:multiLevelType w:val="multilevel"/>
        <w:lvl w:ilvl="0">
            <w:start w:val="1"/>
            <w:numFmt w:val="decimal"/>
            <w:lvlText w:val="%1、"/>
            <w:lvlJc w:val="left"/>
            <w:pPr><w:ind w:left="0" w:firstLine="0" w:hanging="0"/></w:pPr>
        </w:lvl>
        <w:lvl w:ilvl="1">
            <w:start w:val="1"/>
            <w:numFmt w:val="decimal"/>
            <w:lvlText w:val="%1.%2"/>
            <w:lvlJc w:val="left"/>
            <w:pPr><w:ind w:left="420" w:hanging="420"/></w:pPr>
        </w:lvl>
        <w:lvl w:ilvl="2">
            <w:start w:val="1"/>
            <w:numFmt w:val="decimal"/>
            <w:lvlText w:val="%1.%2.%3"/>
            <w:lvlJc w:val="left"/>
            <w:pPr><w:ind w:left="840" w:hanging="840"/></w:pPr>
        </w:lvl>
        <w:lvl w:ilvl="3">
            <w:start w:val="1"/>
            <w:numFmt w:val="decimal"/>
            <w:lvlText w:val="%1.%2.%3.%4"/>
            <w:lvlJc w:val="left"/>
            <w:pPr><w:ind w:left="1260" w:hanging="1260"/></w:pPr>
        </w:lvl>
        <w:lvl w:ilvl="4">
            <w:start w:val="1"/>
            <w:numFmt w:val="decimal"/>
            <w:lvlText w:val="%1.%2.%3.%4.%5"/>
            <w:lvlJc w:val="left"/>
            <w:pPr><w:ind w:left="1680" w:hanging="1680"/></w:pPr>
        </w:lvl>
    </w:abstractNum>'''
    
    abstract_elem = parse_xml(abstract_xml)
    numbering_elem.insert(0, abstract_elem)
    
    # Create num element linking to abstractNum
    num_id = _get_next_num_id(numbering_elem)
    num_xml = f'<w:num {nsdecls("w")} w:numId="{num_id}"><w:abstractNumId w:val="{abstract_id}"/></w:num>'
    num_elem = parse_xml(num_xml)
    numbering_elem.append(num_elem)
    
    # Remove style-level numPr from all heading styles to prevent inherited numbering conflicts
    styles_elem = doc.styles.element
    for style in styles_elem.findall(qn('w:style')):
        name_elem = style.find(qn('w:name'))
        if name_elem is None:
            continue
        name_val = name_elem.get(qn('w:val'), '')
        if not re.match(r'heading\s+\d+', name_val, re.IGNORECASE):
            continue
        ppr_style = style.find(qn('w:pPr'))
        if ppr_style is not None:
            existing_style_numPr = ppr_style.find(qn('w:numPr'))
            if existing_style_numPr is not None:
                ppr_style.remove(existing_style_numPr)

    # Now apply numbering to each heading paragraph
    # Mapping: H1 = document title (skip), H2 = chapter (ilvl 0 → "1、"), H3 = section (ilvl 1 → "1.1"),
    #          H4 = subsection (ilvl 2 → "1.1.1"), H5 = sub-subsection (ilvl 3 → "1.1.1.1")
    # Headings to skip from numbering: H1 (document title), "文档修订记录"
    SKIP_HEADING_TEXTS = {'文档修订记录', '修订记录', '修订历史', '参考文献', '术语与缩略语'}

    heading_counter = [0, 0, 0, 0]  # ilvl 0-3 counters

    for para in doc.paragraphs:
        style_name = para.style.name if para.style else ''

        # Match both "Heading 1" and "heading 1" (case-insensitive)
        if not re.match(r'heading\s+\d+', style_name, re.IGNORECASE):
            continue

        # Determine heading level (1-based from style name)
        try:
            h_level = int(re.search(r'\d+', style_name).group())
        except (AttributeError, ValueError):
            continue

        # Get full heading text
        full_text = ''.join(run.text for run in para.runs)
        stripped_text = strip_heading_number(full_text).strip()

        # Clean "（初稿）" / "（定稿）" / version tags from all headings
        cleaned_text = re.sub(r'（初稿）|（定稿）|（V[\d.]+）', '', stripped_text).strip()
        if cleaned_text != full_text and para.runs:
            # Consolidate all text into first run
            para.runs[0].text = cleaned_text
            for run in para.runs[1:]:
                run.text = ''
        elif stripped_text != full_text and para.runs:
            # Strip existing numbering from heading text
            para.runs[0].text = stripped_text
            for run in para.runs[1:]:
                run.text = ''

        # H1 (document title) — no numbering, just override style numPr with numId=0
        if h_level == 1:
            _set_paragraph_numPr(para, ilvl=0, num_id=0)
            continue

        # Skip metadata headings (修订记录 etc.)
        if stripped_text in SKIP_HEADING_TEXTS:
            _set_paragraph_numPr(para, ilvl=0, num_id=0)
            continue

        # Map heading level to numbering ilvl: H2→0, H3→1, H4→2, H5→3
        ilvl = h_level - 2  # H2→0, H3→1, H4→2, H5→3
        if ilvl < 0 or ilvl > 3:
            _set_paragraph_numPr(para, ilvl=0, num_id=0)
            continue

        # Update counter
        heading_counter[ilvl] += 1
        # Reset deeper levels
        for i in range(ilvl + 1, 4):
            heading_counter[i] = 0

        # Apply paragraph-level numPr
        _set_paragraph_numPr(para, ilvl=ilvl, num_id=num_id)

    return num_id


def _set_paragraph_numPr(para, ilvl, num_id):
    """Set or override numPr on a paragraph. num_id=0 means no numbering."""
    pPr = para._element.find(qn('w:pPr'))
    if pPr is None:
        pPr = parse_xml(f'<w:pPr {nsdecls("w")}></w:pPr>')
        para._element.insert(0, pPr)

    # Remove existing numPr if any
    existing_numPr = pPr.find(qn('w:numPr'))
    if existing_numPr is not None:
        pPr.remove(existing_numPr)

    numPr = parse_xml(
        f'<w:numPr {nsdecls("w")}><w:ilvl w:val="{ilvl}"/><w:numId w:val="{num_id}"/></w:numPr>'
    )
    pPr.insert(0, numPr)


def _get_next_abstract_num_id(numbering_elem):
    """获取下一个可用的 abstractNumId"""
    max_id = -1
    for abstract in numbering_elem.findall(qn('w:abstractNum')):
        aid = int(abstract.get(qn('w:abstractNumId'), '0'))
        if aid > max_id:
            max_id = aid
    return max_id + 1


def _get_next_num_id(numbering_elem):
    """获取下一个可用的 numId"""
    max_id = 0
    for num in numbering_elem.findall(qn('w:num')):
        nid = int(num.get(qn('w:numId'), '0'))
        if nid > max_id:
            max_id = nid
    return max_id + 1


def fix_document_styles(doc):
    """修复文档样式：字体、字号、行距等，匹配国泰海通标准"""
    styles = doc.styles
    
    # Fix Normal style (body text)
    normal = styles['Normal']
    normal.font.name = FONT_BODY_EN
    normal.font.size = Pt(SZ_BODY / 2)
    normal._element.rPr.rFonts.set(qn('w:eastAsia'), FONT_BODY_CN)
    normal.paragraph_format.line_spacing = Pt(SZ_BODY / 2 * 1.3)  # ~1.3x line spacing
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    
    # Fix heading styles
    heading_configs = [
        ('Heading 1', SZ_H1, True, FONT_HEADING_CN, FONT_HEADING_EN, 18, 18),
        ('Heading 2', SZ_H2, True, FONT_HEADING_CN, FONT_HEADING_EN, 14, 14),
        ('Heading 3', SZ_H3, True, FONT_BODY_CN, FONT_BODY_EN, 12, 12),
        ('Heading 4', SZ_H4, True, FONT_HEADING_CN, FONT_HEADING_EN, 10, 10),
    ]
    
    for name, sz, bold, font_cn, font_en, space_before, space_after in heading_configs:
        try:
            style = styles[name]
            style.font.name = font_en
            style.font.size = Pt(sz / 2)
            style.font.bold = bold
            style._element.rPr.rFonts.set(qn('w:eastAsia'), font_cn)
            style.paragraph_format.space_before = Pt(space_before)
            style.paragraph_format.space_after = Pt(space_after)
            style.paragraph_format.keep_with_next = True
        except KeyError:
            pass
    
    # Fix table styles
    for style_name in ['Table Grid', 'Normal Table']:
        try:
            style = styles[style_name]
            style.font.name = FONT_BODY_EN
            style.font.size = Pt(SZ_BODY / 2)
            if hasattr(style, '_element') and style._element.rPr is not None:
                style._element.rPr.rFonts.set(qn('w:eastAsia'), FONT_BODY_CN)
        except KeyError:
            pass


def add_missing_pandoc_styles(doc):
    """添加 pandoc 引用但未定义的样式（CaptionedFigure, ImageCaption 等），
    否则 Word 无法正确渲染图片段落"""
    styles_elem = doc.styles.element

    # List of pandoc-generated styles that may be missing
    missing_styles = {
        'FirstParagraph': {
            'name': 'First Paragraph',
            'type': 'paragraph',
            'pPr': f'<w:spacing w:before="0" w:after="120" w:line="360" w:lineRule="auto"/><w:ind w:firstLineChars="200" w:firstLine="420"/>',
            'rPr': f'<w:rFonts w:ascii="{FONT_BODY_EN}" w:eastAsia="{FONT_BODY_CN}"/><w:sz w:val="{SZ_BODY}"/><w:szCs w:val="{SZ_BODY}"/>',
        },
        'BodyText': {
            'name': 'Body Text',
            'type': 'paragraph',
            'pPr': f'<w:spacing w:before="0" w:after="120" w:line="360" w:lineRule="auto"/><w:ind w:firstLineChars="200" w:firstLine="420"/>',
            'rPr': f'<w:rFonts w:ascii="{FONT_BODY_EN}" w:eastAsia="{FONT_BODY_CN}"/><w:sz w:val="{SZ_BODY}"/><w:szCs w:val="{SZ_BODY}"/>',
        },
        'Compact': {
            'name': 'Compact',
            'type': 'paragraph',
            'pPr': f'<w:spacing w:before="0" w:after="0" w:line="276" w:lineRule="auto"/>',
            'rPr': f'<w:rFonts w:ascii="{FONT_BODY_EN}" w:eastAsia="{FONT_BODY_CN}"/><w:sz w:val="{SZ_BODY}"/><w:szCs w:val="{SZ_BODY}"/>',
        },
        'BlockText': {
            'name': 'Block Text',
            'type': 'paragraph',
            'pPr': f'<w:spacing w:before="60" w:after="60" w:line="360" w:lineRule="auto"/><w:ind w:left="420" w:right="420"/>',
            'rPr': f'<w:rFonts w:ascii="{FONT_BODY_EN}" w:eastAsia="{FONT_BODY_CN}"/><w:sz w:val="{SZ_BODY}"/><w:szCs w:val="{SZ_BODY}"/>',
        },
        'CaptionedFigure': {
            'name': 'CaptionedFigure',
            'type': 'paragraph',
            'pPr': '<w:jc w:val="center"/><w:spacing w:before="180" w:after="60"/>',
            'rPr': '',
        },
        'ImageCaption': {
            'name': 'ImageCaption',
            'type': 'paragraph',
            'pPr': '<w:jc w:val="center"/><w:spacing w:before="60" w:after="240"/>',
            'rPr': f'<w:rFonts w:ascii="{FONT_BODY_EN}" w:eastAsia="{FONT_BODY_CN}"/><w:sz w:val="18"/><w:szCs w:val="18"/>',
        },
        'TableCaption': {
            'name': 'TableCaption',
            'type': 'paragraph',
            'pPr': '<w:jc w:val="center"/><w:spacing w:before="60" w:after="120"/>',
            'rPr': f'<w:rFonts w:ascii="{FONT_BODY_EN}" w:eastAsia="{FONT_BODY_CN}"/><w:sz w:val="{SZ_BODY}"/><w:szCs w:val="{SZ_BODY}"/>',
        },
    }

    # Get existing style IDs and names
    existing_ids = set()
    existing_names = set()
    for style in styles_elem.findall(qn('w:style')):
        sid = style.get(qn('w:styleId'), '')
        name_elem = style.find(qn('w:name'))
        name = name_elem.get(qn('w:val'), '') if name_elem is not None else ''
        existing_ids.add(sid)
        existing_names.add(name)

    # Add missing styles
    for style_id, config in missing_styles.items():
        if style_id in existing_ids or config['name'] in existing_names:
            continue

        style_xml = f'<w:style {nsdecls("w")} w:type="{config["type"]}" w:styleId="{style_id}">'
        style_xml += f'<w:name w:val="{config["name"]}"/>'
        if config['pPr']:
            style_xml += f'<w:pPr>{config["pPr"]}</w:pPr>'
        if config['rPr']:
            style_xml += f'<w:rPr>{config["rPr"]}</w:rPr>'
        style_xml += '</w:style>'

        styles_elem.append(parse_xml(style_xml))


def beautify_tables(doc):
    """表格全面美化：表头灰底居中、单元格内边距、斑马纹、列宽优化、字体统一、行高、垂直居中"""
    from docx.oxml.ns import qn as _qn
    
    for table in doc.tables:
        tbl = table._element
        tblPr = tbl.find(qn('w:tblPr'))
        if tblPr is None:
            tblPr = parse_xml(f'<w:tblPr {nsdecls("w")}></w:tblPr>')
            tbl.insert(0, tblPr)
        
        # ── 1. 边框：外框细线 + 内部更细线 ──
        existing_borders = tblPr.find(qn('w:tblBorders'))
        if existing_borders is not None:
            tblPr.remove(existing_borders)
        borders_xml = f'''<w:tblBorders {nsdecls("w")}>
            <w:top w:val="single" w:sz="4" w:space="0" w:color="auto"/>
            <w:left w:val="single" w:sz="4" w:space="0" w:color="auto"/>
            <w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/>
            <w:right w:val="single" w:sz="4" w:space="0" w:color="auto"/>
            <w:insideH w:val="single" w:sz="2" w:space="0" w:color="BFBFBF"/>
            <w:insideV w:val="single" w:sz="2" w:space="0" w:color="BFBFBF"/>
        </w:tblBorders>'''
        tblPr.append(parse_xml(borders_xml))
        
        # ── 2. 单元格内边距 ──
        existing_cellmar = tblPr.find(qn('w:tblCellMar'))
        if existing_cellmar is not None:
            tblPr.remove(existing_cellmar)
        cellmar_xml = f'''<w:tblCellMar {nsdecls("w")}>
            <w:top w:w="40" w:type="dxa"/>
            <w:left w:w="108" w:type="dxa"/>
            <w:bottom w:w="40" w:type="dxa"/>
            <w:right w:w="108" w:type="dxa"/>
        </w:tblCellMar>'''
        tblPr.append(parse_xml(cellmar_xml))
        
        # ── 3. 表格居中（窄表） ──
        num_cols = len(table.columns) if table.columns else 0
        existing_jc = tblPr.find(qn('w:jc'))
        if num_cols <= 4:
            if existing_jc is not None:
                tblPr.remove(existing_jc)
            tblPr.append(parse_xml(f'<w:jc {nsdecls("w")} w:val="center"/>'))
        
        rows = table.rows
        if len(rows) == 0:
            continue
        
        # ── 4. 表头行美化 ──
        header_row = rows[0]
        header_tr = header_row._element
        # 表头行加粗底部分隔线
        existing_trpr = header_tr.find(qn('w:trPr'))
        if existing_trpr is None:
            existing_trpr = parse_xml(f'<w:trPr {nsdecls("w")}></w:trPr>')
            header_tr.insert(0, existing_trpr)
        # 表头行高
        existing_trh = existing_trpr.find(qn('w:trHeight'))
        if existing_trh is not None:
            existing_trpr.remove(existing_trh)
        existing_trpr.append(parse_xml(f'<w:trHeight {nsdecls("w")} w:val="360" w:hRule="atLeast"/>'))
        
        for cell in header_row.cells:
            tcPr = cell._element.find(qn('w:tcPr'))
            if tcPr is None:
                tcPr = parse_xml(f'<w:tcPr {nsdecls("w")}></w:tcPr>')
                cell._element.insert(0, tcPr)
            
            # 灰底
            existing_shd = tcPr.find(qn('w:shd'))
            if existing_shd is not None:
                tcPr.remove(existing_shd)
            tcPr.append(parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{COLOR_GRAY_BG}"/>'))
            
            # 垂直居中
            existing_valign = tcPr.find(qn('w:vAlign'))
            if existing_valign is not None:
                tcPr.remove(existing_valign)
            tcPr.append(parse_xml(f'<w:vAlign {nsdecls("w")} w:val="center"/>'))
            
            # 段落格式：居中 + 加粗 + 深蓝色
            for para in cell.paragraphs:
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                para.paragraph_format.space_before = Pt(2)
                para.paragraph_format.space_after = Pt(2)
                for run in para.runs:
                    run.bold = True
                    run.font.size = Pt(10.5)
                    run.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
                    run.font.name = FONT_HEADING_EN
                    run._element.rPr.rFonts.set(qn('w:eastAsia'), FONT_HEADING_CN)
        
        # ── 5. 数据行美化 ──
        num_rows = len(rows)
        for ridx in range(1, num_rows):
            row = rows[ridx]
            row_tr = row._element
            
            # 最小行高
            trpr = row_tr.find(qn('w:trPr'))
            if trpr is None:
                trpr = parse_xml(f'<w:trPr {nsdecls("w")}></w:trPr>')
                row_tr.insert(0, trpr)
            existing_trh = trpr.find(qn('w:trHeight'))
            if existing_trh is not None:
                trpr.remove(existing_trh)
            trpr.append(parse_xml(f'<w:trHeight {nsdecls("w")} w:val="280" w:hRule="atLeast"/>'))
            
            # 斑马纹（行数 ≥ 8 时启用，偶数数据行加浅灰底）
            use_zebra = num_rows >= 8
            is_even_data_row = (ridx % 2 == 0)
            
            for cell in row.cells:
                tcPr = cell._element.find(qn('w:tcPr'))
                if tcPr is None:
                    tcPr = parse_xml(f'<w:tcPr {nsdecls("w")}></w:tcPr>')
                    cell._element.insert(0, tcPr)
                
                # 垂直居中
                existing_valign = tcPr.find(qn('w:vAlign'))
                if existing_valign is not None:
                    tcPr.remove(existing_valign)
                tcPr.append(parse_xml(f'<w:vAlign {nsdecls("w")} w:val="center"/>'))
                
                # 斑马纹底色
                if use_zebra and is_even_data_row:
                    existing_shd = tcPr.find(qn('w:shd'))
                    if existing_shd is not None:
                        tcPr.remove(existing_shd)
                    tcPr.append(parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{COLOR_ZEBRA}"/>'))
                
                # 正文单元格字体统一
                for para in cell.paragraphs:
                    para.paragraph_format.space_before = Pt(1)
                    para.paragraph_format.space_after = Pt(1)
                    for run in para.runs:
                        if not run.font.size:
                            run.font.size = Pt(10)
                        if not run.font.name:
                            run.font.name = FONT_BODY_EN
                            run._element.rPr.rFonts.set(qn('w:eastAsia'), FONT_BODY_CN)


def beautify_images(doc):
    """图片美化：图片段落添加上下间距、图注增强、满页宽显示、超高限制"""
    # A4 页面可用宽度 (21cm - 3.18cm*2 = 14.64cm)，单位 EMU (1cm = 360000 EMU)
    PAGE_USABLE_EMU = int(14.64 * 360000)  # 5270400
    # A4 页面可用高度 (29.7cm - 2.54cm*2 = 24.62cm)，安全最大高度 20cm
    MAX_HEIGHT_EMU = int(20 * 360000)  # 7,200,000

    for para in doc.paragraphs:
        # Check if paragraph contains a drawing/image
        drawings = para._element.findall('.//' + qn('w:drawing'))
        if not drawings:
            continue

        # ── Set image to fit within page width AND max height ──
        for drawing in drawings:
            # wp:extent (inline or anchor)
            for extent in drawing.findall('.//' + qn('wp:extent')):
                cx = int(extent.get('cx', '0'))
                cy = int(extent.get('cy', '0'))
                if cx <= 0:
                    continue
                # Step 1: Scale to page width
                if cx != PAGE_USABLE_EMU:
                    ratio = PAGE_USABLE_EMU / cx
                    cx = PAGE_USABLE_EMU
                    cy = int(cy * ratio)
                # Step 2: Cap height to max (prevents ultra-tall images from overflowing page)
                if cy > MAX_HEIGHT_EMU:
                    ratio = MAX_HEIGHT_EMU / cy
                    cx = int(cx * ratio)
                    cy = MAX_HEIGHT_EMU
                extent.set('cx', str(cx))
                extent.set('cy', str(cy))

            # a:ext inside a:xfrm (graphic frame) — must match wp:extent
            ns_a = 'http://schemas.openxmlformats.org/drawingml/2006/main'
            for ext in drawing.findall('.//{%s}ext' % ns_a):
                cx = int(ext.get('cx', '0'))
                cy = int(ext.get('cy', '0'))
                if cx <= 0:
                    continue
                # Step 1: Scale to page width
                if cx != PAGE_USABLE_EMU:
                    ratio = PAGE_USABLE_EMU / cx
                    cx = PAGE_USABLE_EMU
                    cy = int(cy * ratio)
                # Step 2: Cap height to max
                if cy > MAX_HEIGHT_EMU:
                    ratio = MAX_HEIGHT_EMU / cy
                    cx = int(cx * ratio)
                    cy = MAX_HEIGHT_EMU
                ext.set('cx', str(cx))
                ext.set('cy', str(cy))
        
        # Ensure paragraph has proper spacing (CaptionedFigure style should handle this)
        pPr = para._element.find(qn('w:pPr'))
        if pPr is None:
            pPr = parse_xml(f'<w:pPr {nsdecls("w")}></w:pPr>')
            para._element.insert(0, pPr)
        
        # ── Fix: Set paragraph style to CaptionedFigure (pandoc may assign FirstParagraph/BodyText
        #    which are undefined in the reference doc's styles.xml, causing images to not render) ──
        pStyle = pPr.find(qn('w:pStyle'))
        if pStyle is None:
            pPr.insert(0, parse_xml(f'<w:pStyle {nsdecls("w")} w:val="CaptionedFigure"/>'))
        else:
            current_style = pStyle.get(qn('w:val'), '')
            if current_style not in ('CaptionedFigure',):
                pStyle.set(qn('w:val'), 'CaptionedFigure')
        
        # Ensure center alignment
        jc = pPr.find(qn('w:jc'))
        if jc is None:
            pPr.append(parse_xml(f'<w:jc {nsdecls("w")} w:val="center"/>'))
        
        # Add spacing before/after for image paragraph
        spacing = pPr.find(qn('w:spacing'))
        if spacing is None:
            spacing = parse_xml(f'<w:spacing {nsdecls("w")} w:before="180" w:after="60"/>')
            pPr.append(spacing)
        else:
            spacing.set(qn('w:before'), '180')
            spacing.set(qn('w:after'), '60')
        
        # Enhance image caption (next paragraph with ImageCaption style)
        pStyle = pPr.find(qn('w:pStyle'))
        style_val = pStyle.get(qn('w:val'), '') if pStyle is not None else ''
        
        # Find next paragraph and check if it's an image caption
        parent = para._element.getparent()
        if parent is not None:
            idx = list(parent).index(para._element)
            if idx + 1 < len(parent):
                next_elem = parent[idx + 1]
                if next_elem.tag == qn('w:p'):
                    next_pPr = next_elem.find(qn('w:pPr'))
                    if next_pPr is not None:
                        next_pStyle = next_pPr.find(qn('w:pStyle'))
                        if next_pStyle is not None and next_pStyle.get(qn('w:val'), '') == 'ImageCaption':
                            # Caption text is already set from alt text; ensure font size
                            for run_elem in next_elem.findall('.//' + qn('w:r')):
                                rpr = run_elem.find(qn('w:rPr'))
                                if rpr is None:
                                    rpr = parse_xml(f'<w:rPr {nsdecls("w")}></w:rPr>')
                                    run_elem.insert(0, rpr)
                                # Set 9pt for caption
                                sz = rpr.find(qn('w:sz'))
                                if sz is None:
                                    rpr.append(parse_xml(f'<w:sz {nsdecls("w")} w:val="18"/>'))
                                    rpr.append(parse_xml(f'<w:szCs {nsdecls("w")} w:val="18"/>'))
                                else:
                                    sz.set(qn('w:val'), '18')


def colorize_status_cells(doc):
    """状态列条件着色：已上线→绿色、待上线→橙色、—→灰色"""
    STATUS_COLORS = {
        '已上线': COLOR_STATUS_GREEN,
        '待上线': COLOR_STATUS_ORANGE,
        'SIT': COLOR_STATUS_ORANGE,
        'UAT': COLOR_STATUS_ORANGE,
        '不需要': COLOR_STATUS_GRAY,
        '—': COLOR_STATUS_GRAY,
    }

    for table in doc.tables:
        if len(table.rows) < 2:
            continue
        # Find status columns by header text
        header_cells = table.rows[0].cells
        status_col_indices = []
        for cidx, cell in enumerate(header_cells):
            header_text = cell.text.strip()
            if '状态' in header_text or '上线' in header_text:
                status_col_indices.append(cidx)

        if not status_col_indices:
            continue

        # Colorize data rows
        for row in table.rows[1:]:
            for cidx in status_col_indices:
                if cidx >= len(row.cells):
                    continue
                cell = row.cells[cidx]
                cell_text = cell.text.strip()
                for keyword, color in STATUS_COLORS.items():
                    if keyword in cell_text:
                        for para in cell.paragraphs:
                            for run in para.runs:
                                rgb = RGBColor(int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16))
                                run.font.color.rgb = rgb
                        break


def optimize_column_widths(doc):
    """基于内容长度智能分配列宽，消除等分列宽导致的文本过度换行和空间浪费。

    算法：
      1. 遍历所有行，计算每列最大文本长度（含表头）
      2. 以 max_len 为权重，设下限 3 字符、上限 60 字符（防止单列垄断）
      3. 归一化为 dxa (twips) 宽度，更新 tblGrid/gridCol 和所有单元格 tcW
      4. 约束：最小列宽 5%、最大列宽 50%
    """
    # 页面可用宽度（A4 - 左右边距）
    PAGE_USABLE_TWIPS = 8301
    MIN_COL_PCT = 0.08   # 最小列宽 8%（确保最窄列 ≥1.1cm）
    MAX_COL_PCT = 0.45   # 最大列宽 45%（防止单列垄断过多空间）
    MIN_COL_TWIPS = 700  # 最小列宽绝对值 ≈ 1.23cm（与百分比取较大者）
    MIN_WEIGHT = 3       # 最小权重（字符数）
    MAX_WEIGHT = 60      # 最大权重（防止超长文本垄断列宽）

    for table in doc.tables:
        if len(table.rows) < 2:
            continue

        ncol = len(table.columns)
        if ncol <= 1:
            continue

        # ── 1. 计算每列最大文本长度 ──
        max_lengths = [0] * ncol
        for row in table.rows:
            for cidx, cell in enumerate(row.cells):
                if cidx >= ncol:
                    break
                text = cell.text.strip()
                # 取最长行的长度，而非整个单元格文本长度
                # （多段落单元格取最长段落）
                lines = text.split('\n')
                for line in lines:
                    # 中文字符按 2 宽度计算，英文/数字按 1
                    visual_len = sum(2 if ord(c) > 127 else 1 for c in line)
                    if visual_len > max_lengths[cidx]:
                        max_lengths[cidx] = visual_len

        # ── 2. 计算权重 ──
        weights = []
        for length in max_lengths:
            w = max(length, MIN_WEIGHT)
            w = min(w, MAX_WEIGHT)
            weights.append(w)

        # ── 3. 归一化为列宽（twips）──
        total_weight = sum(weights)
        col_widths = [w / total_weight for w in weights]

        # 应用最小/最大百分比约束（迭代 3 轮）
        for _ in range(3):
            for i in range(ncol):
                if col_widths[i] < MIN_COL_PCT:
                    col_widths[i] = MIN_COL_PCT
                elif col_widths[i] > MAX_COL_PCT:
                    col_widths[i] = MAX_COL_PCT
            # 重新归一化
            total = sum(col_widths)
            col_widths = [w / total for w in col_widths]

        # 转换为 twips
        col_widths_twips = [int(w * PAGE_USABLE_TWIPS) for w in col_widths]
        # 应用绝对最小列宽（与百分比取较大者）
        for i in range(ncol):
            if col_widths_twips[i] < MIN_COL_TWIPS:
                col_widths_twips[i] = MIN_COL_TWIPS
        # 修正舍入误差：差额加到最大列
        diff = PAGE_USABLE_TWIPS - sum(col_widths_twips)
        if diff != 0:
            max_idx = col_widths_twips.index(max(col_widths_twips))
            col_widths_twips[max_idx] += diff

        # ── 4. 更新 tblGrid ──
        tbl = table._element
        tblGrid = tbl.find(qn('w:tblGrid'))
        if tblGrid is not None:
            gridCols = tblGrid.findall(qn('w:gridCol'))
            for i, gc in enumerate(gridCols):
                if i < ncol:
                    gc.set(qn('w:w'), str(col_widths_twips[i]))

        # ── 5. 更新所有行的单元格宽度 ──
        for row in table.rows:
            for cidx, cell in enumerate(row.cells):
                if cidx >= ncol:
                    break
                tcPr = cell._element.find(qn('w:tcPr'))
                if tcPr is None:
                    tcPr = parse_xml(f'<w:tcPr {nsdecls("w")}></w:tcPr>')
                    cell._element.insert(0, tcPr)
                tcW = tcPr.find(qn('w:tcW'))
                if tcW is None:
                    tcW = parse_xml(f'<w:tcW {nsdecls("w")}></w:tcW>')
                    tcPr.append(tcW)
                tcW.set(qn('w:w'), str(col_widths_twips[cidx]))
                tcW.set(qn('w:type'), 'dxa')


def cleanup_empty_paragraphs(doc):
    """清理连续空段落：删除 3+ 连续空段落中多余的，保留最多 1 个作为间距。"""
    body = doc.element.body
    paragraphs = body.findall(qn('w:p'))
    to_remove = []
    empty_streak = 0

    for p in paragraphs:
        # Check if paragraph is empty (no text content)
        texts = p.findall('.//' + qn('w:t'))
        has_text = any((t.text or '').strip() for t in texts)
        # Also check for drawings, page breaks, etc.
        has_drawing = len(p.findall('.//' + qn('w:drawing'))) > 0
        has_break = len(p.findall('.//' + qn('w:br'))) > 0
        has_fld = len(p.findall('.//' + qn('w:fldChar'))) > 0 or len(p.findall('.//' + qn('w:instrText'))) > 0

        if not has_text and not has_drawing and not has_fld:
            if has_break:
                # Page break paragraph - reset streak, don't remove
                empty_streak = 0
                continue
            empty_streak += 1
            if empty_streak >= 2:
                to_remove.append(p)
        else:
            empty_streak = 0

    for p in to_remove:
        body.remove(p)

    if to_remove:
        print(f"    Removed {len(to_remove)} consecutive empty paragraph(s)")


def verify_docx_integrity(doc):
    """生成后完整性验证：检查样式定义完整性、图片尺寸与样式、关系完整性。
    返回 issues 列表（空列表=全部通过）。"""
    issues = []

    # ── 1. 检查所有段落引用的 pStyle 是否在 styles.xml 中有定义 ──
    styles_elem = doc.styles.element
    defined_style_ids = set()
    for style in styles_elem.findall(qn('w:style')):
        sid = style.get(qn('w:styleId'), '')
        if sid:
            defined_style_ids.add(sid)

    body = doc.element.body
    for p in body.findall(qn('w:p')):
        pPr = p.find(qn('w:pPr'))
        if pPr is None:
            continue
        pStyle = pPr.find(qn('w:pStyle'))
        if pStyle is None:
            continue
        style_val = pStyle.get(qn('w:val'), '')
        if style_val and style_val not in defined_style_ids:
            # 检查该段落是否含图片
            has_drawing = len(p.findall('.//' + qn('w:drawing'))) > 0
            ctx = ' [含图片]' if has_drawing else ''
            issues.append(f"未定义样式: pStyle='{style_val}'{ctx}")

    # ── 2. 检查图片段落样式与尺寸 ──
    PAGE_USABLE_EMU = int(14.64 * 360000)
    MAX_HEIGHT_EMU = int(20 * 360000)

    for p in body.findall(qn('w:p')):
        drawings = p.findall('.//' + qn('w:drawing'))
        if not drawings:
            continue

        # 检查图片段落样式
        pPr = p.find(qn('w:pPr'))
        if pPr is not None:
            pStyle = pPr.find(qn('w:pStyle'))
            if pStyle is not None:
                style_val = pStyle.get(qn('w:val'), '')
                if style_val != 'CaptionedFigure':
                    issues.append(f"图片段落样式非 CaptionedFigure: '{style_val}'")

        # 检查图片尺寸
        for d in drawings:
            ns_wp = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
            for ext in d.findall('.//{%s}extent' % ns_wp):
                cx = int(ext.get('cx', '0'))
                cy = int(ext.get('cy', '0'))
                if cx <= 0 or cy <= 0:
                    issues.append(f"图片尺寸异常: cx={cx}, cy={cy}")
                elif cx > PAGE_USABLE_EMU + 1:
                    issues.append(f"图片宽度超限: {cx/360000:.1f}cm > 14.64cm")
                elif cy > MAX_HEIGHT_EMU + 1:
                    issues.append(f"图片高度超限: {cy/360000:.1f}cm > 20.0cm")

    # ── 3. 检查图片关系完整性 ──
    rels = doc.part.rels
    for p in body.findall(qn('w:p')):
        drawings = p.findall('.//' + qn('w:drawing'))
        if not drawings:
            continue
        ns_a = 'http://schemas.openxmlformats.org/drawingml/2006/main'
        for d in drawings:
            for blip in d.findall('.//{%s}blip' % ns_a):
                embed = blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed', '')
                if embed and embed not in rels:
                    issues.append(f"图片关系缺失: r:embed='{embed}' 无对应 relationship")
                elif embed:
                    rel = rels[embed]
                    if rel.target_part is None:
                        issues.append(f"图片目标缺失: r:embed='{embed}' target_part is None")
                    elif not rel.target_part.blob:
                        issues.append(f"图片内容为空: r:embed='{embed}' blob is empty")

    return issues


def format_figure_table_captions(doc):
    """格式化图表编号标题段落（**图N　...** / **表N　...**）。

    pandoc 将 Markdown 中的 **图1　标题** 渲染为粗体段落。
    本函数将其格式化为居中、黑体、小五号的图表标题样式。
    """
    caption_pattern = re.compile(r'^(图|表)\s*\d+')

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        # Check if this paragraph is a figure/table caption
        if not caption_pattern.match(text):
            continue

        # Verify it's bold (all runs should be bold, or it's a single bold run)
        runs = para.runs
        if not runs:
            continue
        all_bold = all(run.bold for run in runs if run.text.strip())
        if not all_bold:
            continue

        # Apply caption formatting
        pf = para.paragraph_format
        pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf.space_before = Pt(6)
        pf.space_after = Pt(6)
        pf.first_line_indent = Cm(0)
        pf.left_indent = Cm(0)

        # Set font: 黑体 9pt for all runs
        for run in runs:
            run.font.size = Pt(9)
            run.font.bold = True
            rPr = run._element.find(qn('w:rPr'))
            if rPr is None:
                rPr = parse_xml(f'<w:rPr {nsdecls("w")}></w:rPr>')
                run._element.insert(0, rPr)
            rFonts = rPr.find(qn('w:rFonts'))
            if rFonts is None:
                rFonts = parse_xml(f'<w:rFonts {nsdecls("w")}></w:rFonts>')
                rPr.insert(0, rFonts)
            rFonts.set(qn('w:eastAsia'), '黑体')
            rFonts.set(qn('w:ascii'), 'Arial')
            rFonts.set(qn('w:hAnsi'), 'Arial')


def format_references(doc):
    """格式化参考文献章节：学术论文标准格式。

    - 字体：宋体（中文）/ Times New Roman（英文）
    - 字号：小五号（9pt）
    - 行距：1.5 倍
    - 悬挂缩进：首行顶格，后续行缩进 0.74cm（420 twips）
    - 段前段后间距：0
    """
    in_refs = False
    for para in doc.paragraphs:
        style_name = para.style.name if para.style else ''
        text = para.text.strip()

        # Detect "参考文献" heading (H2)
        if style_name.startswith('Heading') and text == '参考文献':
            in_refs = True
            continue

        if not in_refs:
            continue

        # Skip empty paragraphs
        if not text:
            continue

        # Apply academic reference formatting
        pf = para.paragraph_format
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
        pf.line_spacing = 1.5
        pf.first_line_indent = Cm(-0.74)
        pf.left_indent = Cm(0.74)

        # Set font for all runs: 宋体 9pt for Chinese, Times New Roman 9pt for English
        for run in para.runs:
            run.font.size = Pt(9)
            run.font.name = 'Times New Roman'
            # Set East Asian font (宋体) via XML
            rPr = run._element.find(qn('w:rPr'))
            if rPr is None:
                rPr = parse_xml(f'<w:rPr {nsdecls("w")}></w:rPr>')
                run._element.insert(0, rPr)
            rFonts = rPr.find(qn('w:rFonts'))
            if rFonts is None:
                rFonts = parse_xml(f'<w:rFonts {nsdecls("w")}></w:rFonts>')
                rPr.insert(0, rFonts)
            rFonts.set(qn('w:eastAsia'), '宋体')
            rFonts.set(qn('w:ascii'), 'Times New Roman')
            rFonts.set(qn('w:hAnsi'), 'Times New Roman')


def set_section_margins(doc):
    """设置页面边距（A4 标准）"""
    for section in doc.sections:
        section.page_width = Cm(21.0)   # A4 width
        section.page_height = Cm(29.7)  # A4 height
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(3.18)
        section.right_margin = Cm(3.18)


def parse_revision_entries(md_content):
    """从 Markdown 中解析修订记录表条目"""
    entries = []
    # Find revision record table (usually first table after "修订记录")
    lines = md_content.split('\n')
    in_rev_table = False
    rev_header_found = False
    
    for i, line in enumerate(lines):
        # Look for revision record header
        if '版本号' in line and '版本日期' in line or ('版本' in line and '修订' in line and '填写人' in line):
            rev_header_found = True
            continue
        
        if rev_header_found and line.strip().startswith('|'):
            # Parse table row
            cells = [c.strip() for c in line.split('|')[1:-1]]
            # Skip separator row (---)
            if all(re.match(r'^[-:]+$', c) for c in cells):
                continue
            # Skip header row
            if '版本' in cells[0] or '日期' in cells[0]:
                continue
            # Skip rows with empty version (placeholder for future)
            if len(cells) >= 5 and not cells[0].strip():
                continue
            # Skip rows where version is a placeholder like V2.0 with no other content
            if len(cells) >= 5 and cells[0].strip() and not any(c.strip() for c in cells[1:]):
                continue
            if len(cells) >= 5:
                entries.append(cells[:5])
        elif rev_header_found and not line.strip().startswith('|') and line.strip():
            # End of table
            if entries:
                break
    
    return entries


def extract_title_from_md(md_content):
    """从 Markdown 提取文档标题和副标题"""
    lines = md_content.split('\n')
    for line in lines:
        if line.startswith('# ') and not line.startswith('## '):
            title = line[2:].strip()
            # Remove common suffixes
            title = re.sub(r'（初稿）|（定稿）|（V[\d.]+）', '', title).strip()
            return title
    return '系统总体设计'


def main():
    parser = argparse.ArgumentParser(description='设计文档 Markdown → 国泰海通标准 Word 文档')
    parser.add_argument('input_md', help='输入 Markdown 文件路径')
    parser.add_argument('output_docx', help='输出 .docx 文件路径')
    parser.add_argument('--title', help='文档标题（封面用，默认从 MD 提取）')
    parser.add_argument('--subtitle', help='文档副标题')
    parser.add_argument('--epic', help='史诗编号')
    parser.add_argument('--author', default='吴进', help='编写人')
    parser.add_argument('--dept', default='技术研发部', help='部门')
    parser.add_argument('--date', help='日期 (YYYY-MM-DD)，默认今天')
    parser.add_argument('--ref-doc', help='pandoc 参考模板 .docx')
    parser.add_argument('--skip-mermaid', action='store_true', help='跳过 Mermaid 渲染')
    
    args = parser.parse_args()
    
    from datetime import date
    date_str = args.date or date.today().strftime('%Y-%m-%d')
    date_display = date_str.replace('-', '年').replace('-', '月') + '日' if '-' in date_str else date_str
    # Better format: 2026年11月
    parts = date_str.split('-')
    if len(parts) >= 2:
        date_display = f'{parts[0]}年{int(parts[1])}月'
    else:
        date_display = date_str
    
    # Read Markdown
    with open(args.input_md, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    # Extract title
    title = args.title or extract_title_from_md(md_content)
    subtitle = args.subtitle
    
    # Parse revision entries
    rev_entries = parse_revision_entries(md_content)
    if not rev_entries:
        rev_entries = [[date_str, 'V1.0', args.author, '定稿', '']]
    
    # Create work directory
    work_dir = tempfile.mkdtemp(prefix='design_doc_')
    input_dir = os.path.dirname(os.path.abspath(args.input_md))
    
    try:
        # Step 1: Preprocess Markdown
        print("Step 1: Preprocessing Markdown...")
        processed_md = preprocess_markdown(md_content)
        
        # Step 2: Render Mermaid diagrams
        if not args.skip_mermaid:
            print("Step 2: Rendering Mermaid diagrams...")
            processed_md, image_map = render_mermaid_diagrams(processed_md, work_dir)
            # Copy images to input directory for pandoc
            for idx, img_path in image_map.items():
                dst = os.path.join(input_dir, f'diagram{idx}.png')
                shutil.copy2(img_path, dst)
        else:
            print("Step 2: Skipping Mermaid rendering...")
            # Still replace mermaid blocks with placeholder
            processed_md = re.sub(r'```mermaid\n.*?```', '（Mermaid 图，请手动插入）', processed_md, flags=re.DOTALL)
        
        # Write processed Markdown
        processed_md_path = os.path.join(work_dir, 'processed.md')
        with open(processed_md_path, 'w', encoding='utf-8') as f:
            f.write(processed_md)
        
        # Step 3: Run pandoc to generate base docx
        print("Step 3: Running pandoc conversion...")
        base_docx = os.path.join(work_dir, 'base.docx')
        run_pandoc(processed_md_path, base_docx, 
                   ref_doc=args.ref_doc, 
                   resource_path=input_dir)
        
        # Step 4: Post-process with python-docx
        print("Step 4: Post-processing document...")
        doc = Document(base_docx)
        
        # Fix page setup
        set_section_margins(doc)
        
        # Fix styles
        fix_document_styles(doc)
        
        # Add missing pandoc styles (CaptionedFigure, ImageCaption, etc.)
        add_missing_pandoc_styles(doc)
        
        # Add cover page
        print("  - Adding cover page...")
        add_cover_page(doc, title, subtitle, args.epic, args.author, args.dept, date_display)
        
        # Add revision table after cover
        print("  - Adding revision record table...")
        # Find the cover table element to insert after
        body = doc.element.body
        cover_tbl_elem = body.find(qn('w:tbl'))
        # Add a spacer paragraph after cover
        spacer_after_cover = doc.add_paragraph()
        body.remove(spacer_after_cover._element)
        if cover_tbl_elem is not None:
            cover_tbl_elem.addnext(spacer_after_cover._element)
        add_revision_table(doc, rev_entries, after_element=spacer_after_cover._element)
        
        # Add page break before content
        print("  - Adding page break and TOC...")
        page_break_p = doc.add_paragraph()
        pb_run = page_break_p.add_run()
        from docx.enum.text import WD_BREAK
        pb_run.add_break(WD_BREAK.PAGE)
        body.remove(page_break_p._element)
        # Insert after revision table
        rev_tbl_elem = body.findall(qn('w:tbl'))[1] if len(body.findall(qn('w:tbl'))) > 1 else None
        if rev_tbl_elem is not None:
            rev_tbl_elem.addnext(page_break_p._element)
        
        # Add TOC — insert after the page break (which follows the revision table),
        # so TOC sits between cover+revision and the content body
        toc_last_elem = add_toc_field(doc, after_element=page_break_p._element)
        
        # Add another page break after TOC to separate it from content
        page_break_p2 = doc.add_paragraph()
        pb_run2 = page_break_p2.add_run()
        pb_run2.add_break(WD_BREAK.PAGE)
        body.remove(page_break_p2._element)
        toc_last_elem.addnext(page_break_p2._element)
        
        # Apply heading numbering
        print("  - Applying heading numbering...")
        try:
            apply_heading_numbering(doc)
        except Exception as e:
            print(f"  Warning: Could not apply heading numbering: {e}", file=sys.stderr)
        
        # Fix table formatting (comprehensive beautification)
        print("  - Beautifying tables...")
        beautify_tables(doc)
        
        # Beautify images (spacing, captions)
        print("  - Beautifying images...")
        beautify_images(doc)
        
        # Colorize status columns
        print("  - Colorizing status cells...")
        colorize_status_cells(doc)

        # Optimize column widths (content-aware distribution)
        print("  - Optimizing column widths...")
        optimize_column_widths(doc)

        # Format references section (academic style)
        print("  - Formatting references...")
        format_references(doc)

        # Format figure/table captions (centered, bold, 小五号)
        print("  - Formatting figure/table captions...")
        format_figure_table_captions(doc)

        # Cleanup consecutive empty paragraphs
        print("  - Cleaning up empty paragraphs...")
        cleanup_empty_paragraphs(doc)

        # Verify document integrity (styles, images, relationships)
        print("  - Verifying document integrity...")
        issues = verify_docx_integrity(doc)
        if issues:
            print(f"  ⚠️  Found {len(issues)} issue(s):")
            for iss in issues:
                print(f"      - {iss}")
        else:
            print(f"  ✅ All checks passed (styles, images, relationships)")

        # Step 5: Save
        print("Step 5: Saving document...")
        doc.save(args.output_docx)
        print(f"\n✅ Document saved: {args.output_docx}")
        print(f"   Size: {os.path.getsize(args.output_docx) / 1024:.1f} KB")
        
    finally:
        # Cleanup
        shutil.rmtree(work_dir, ignore_errors=True)
        # Clean up temporary diagram images from input dir
        for idx in range(1, 10):
            tmp_img = os.path.join(input_dir, f'diagram{idx}.png')
            if os.path.exists(tmp_img):
                os.remove(tmp_img)


if __name__ == '__main__':
    main()
