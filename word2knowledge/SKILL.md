---
name: word2knowledge
description: >-
  Convert Word (.docx) files into Obsidian-compatible Markdown (.md) files with embedded image links.
  Use when Codex needs to process .docx files for Obsidian knowledge management, including:
  (1) Converting Word documents to Markdown, (2) Extracting and migrating embedded images,
  (3) Rewriting image references to Obsidian double-bracket syntax,
  (4) Cleaning up converted text (line breaks, formatting noise),
  (5) Fixing table rendering for Obsidian (GFM → standard Markdown).
  Triggers on: docx to markdown, word to obsidian, .docx conversion,
  "doc转md", "word转笔记", "文档转Obsidian", "提取word图片", or any request to convert Word documents for Obsidian.
---

# Word2Knowledge: DOCX → Obsidian Markdown Converter

Convert Word (.docx) documents into clean, Obsidian-compatible Markdown with embedded image links.

## Prerequisites

1. **Pandoc 3.x** is installed: `pandoc --version`
2. **Python 3** is installed: `python3 --version`
3. **OBSIDIAN_INBOX** path is configured (default: `/Users/wujin/0000WorkFiles/myobsidian/Obsidian-Notes/000_Inbox`)

To update the Obsidian inbox path, either:
- Set the environment variable: `export OBSIDIAN_INBOX="你的路径"`
- Or edit `runner.sh` line 7

## Usage

```bash
bash scripts/runner.sh /path/to/document.docx
bash scripts/runner.sh file1.docx file2.docx file3.docx
```

## Pipeline (4 Steps)

| Step | Action | Output |
|------|--------|--------|
| 1/4 | Pandoc 解析 & 图片提取 | Raw markdown + 图片到 `.tmp/` |
| 2/4 | 图片迁移 & Obsidian 双链重构 | `![[assets/docname/BASENAME_image.png]]` 格式 |
| 3/4 | 文本清洗（换行/空行/排版降噪） | 修复折断段落，保护标题/列表/代码块 |
| 4/4 | 表格格式修复（GFM → 标准 Markdown） | Obsidian 可正确渲染的表格 |

临时文件（`.tmp/`）在处理完成后自动清理。

## Output

- **Markdown 文件**: `OBSIDIAN_INBOX/<basename>.md`
- **图片资产**: `OBSIDIAN_INBOX/assets/<basename>/<basename>_原始图片名`
- **图片链接格式**: `![[assets/docname/docname_image.png]]`

## File Structure

```
scripts/
├── runner.sh              # 主流水线（4步）
└── tools/
    ├── clean_text.py      # Step 3: 文本清洗
    └── fix_tables.py      # Step 4: 表格修复
```

## Cleaning Rules (Step 3)

`clean_text.py` 的清洗规则：

1. 去除 `![[...]]` 中多余的 Pandoc 属性（`{width=... height=...}`）
2. 合并被折断的段落行（依据上一行末尾是否有句末标点）
3. 保护以下行不参与合并：标题（`#`）、列表（`-` / `1.`）、引用（`>`）、代码围栏（` ``` `）、表格（`|` / `+`）、图片占位符（`![[`）
4. 代码块内容完整透传，不做任何处理
5. 去除多余空行，末尾换行保持干净

## Table Fixing Rules (Step 4)

`fix_tables.py` 的处理规则（已集成到主流程）：

1. GFM 表格（`+---+`） → 标准 Markdown（`|---|`）
2. Fixed-width 表格（`--- --- ---`） → 标准 Markdown
3. 修复 broken pipe headers（混合 dash 的表头）
4. 修复分隔行列数与表头不匹配
5. 删除 GFM 合并单元格边框行（`| +---+---+`）
6. 清理交叉引用链接（`[图 1](#_Ref...)`）
7. 合并表格中多行续行（`<br>` 连接）

## Troubleshooting

| 问题 | 解决方案 |
|------|----------|
| `pandoc: command not found` | `brew install pandoc` |
| 图片未被提取 | 检查 docx 中的图片是嵌入图（非链接图） |
| Obsidian 图片链接断裂 | 确认 `OBSIDIAN_INBOX` 路径正确 |
| 表格在 Obsidian 中渲染异常 | 手动运行 `python3 scripts/tools/fix_tables.py <file.md> <basename>` |
| 段落被错误合并 | 检查原文是否有非标准编码，提 issue |
