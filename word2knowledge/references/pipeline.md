# Word2Knowledge Pipeline Architecture

## Overview

Word-to-Knowledge is a pipeline that converts Word `.docx` files into Obsidian-compatible Markdown files with embedded image links.

## Pipeline Steps

1. **Parse & Extract** — Use Pandoc 3.x to convert `.docx` → Markdown, extract embedded images to `tmp/media/`
2. **Asset Transfer & Link Rewriting** — Move images to Obsidian Inbox with `BASENAME_` prefix; rewrite Pandoc image syntax to Obsidian double-bracket `![[...]]` syntax (remove `{width=...}` attributes)
3. **Text Cleaning** — Use `tools/clean_text.py` (pure local regex, no API) to fix broken line breaks, remove extra blank lines, preserve `![[...]]` image placeholders
4. **Table Post-Processing** — Use `tools/fix_tables.py` to convert GFM/fixed-width tables to standard Markdown

## Pandoc 3.x Compatibility

Pandoc 3.x outputs images in Obsidian-compatible `![[...]]` format directly:

```
![[assets/文档名/imageN.png]]{width="..." height="..."}
```

The pipeline handles this by:
1. Using `perl` to add `BASENAME_` prefix: `image1.png` → `BASENAME_image1.png`
2. Stripping trailing attributes: `{width="..." height="..."} alt="..."}` → removed
3. Result: `![[assets/文档名/文档名_image1.png]]`

> **Note**: Old sed regex `s|!\[.*\](.*media/\(.*\))|...|` only works with Pandoc 2.x output `![alt](media/X.png)`. Pandoc 3.x requires the perl regex approach shown above.

## Table Rendering Issues

Pandoc 3.x outputs tables in two non-standard formats that render poorly in Obsidian:

### GFM Format
```
+---+---+---+
| Header | Header | Header |
+---+---+---+
| Data | Data | Data |
+---+---+---+
```

### Fixed-Width Format
```
--- ---------- -----
data1    data2    data3
--- ---------- -----
```

The `fix_tables.py` script converts both to standard Markdown:
```
| Header | Header | Header |
| --- | --- | --- |
| Data | Data | Data |
```

## Post-Processing

After the pipeline produces `tmp/<basename>_cleaned.md`, optional post-processing improves Obsidian rendering:

```bash
python3 scripts/tools/fix_tables.py <file.md> [basename]
```

Fixes include:
1. GFM tables (`+---+`) → standard Markdown (`|---|`)
2. Fixed-width tables (`--- --- ---`) → standard Markdown (`|---|---|---|`)
3. Broken pipe headers (`| ----...| **Header** |`) → clean headers
4. Separator column count alignment (match `---` count to header columns)
5. Merged-cell border removal (`| +---+---+`)
6. Cross-reference cleanup (`[图 1](#_Ref...)` → `图 1`)
7. Typo fix (`和所示` → `所示`)
8. Multi-line note merging (`<br>`)

## Prerequisites

- `pandoc` 3.x installed
- `perl` installed (for link rewriting)
- `OBSIDIAN_INBOX` path configured in `runner.sh`

## File Structure

```
scripts/
├── runner.sh              # Main pipeline orchestrator
├── tools/
│   ├── clean_text.py      # Local text cleaning (regex, no API)
│   └── fix_tables.py      # Table rendering fix (GFM/fixed-width → Markdown)
└── .tmp/                  # Temporary files (raw.md, cleaned.md)
```

## Usage

```bash
bash scripts/runner.sh /path/to/file.docx
```
