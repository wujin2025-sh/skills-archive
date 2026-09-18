---
name: anydoc
description: 极速将 Word (.doc/.docx/.docm)、PowerPoint (.ppt/.pptx/.pps/.pot/.odp)、Excel
  (.xls/.xlsx/.xlsm/.xlsb/.ods)、PDF、RTF、EPUB、CSV 等 14 种复杂办公文档与电子书转换为干净纯粹的 GitHub 风格
  Markdown。由 Firecrawl 研发，Rust 内核单次解析中位数 <5ms，支持 CLI 命令与 Python/Node API 直接调用。
disable: false
---


# AnyDoc: 高性能多格式文档转 Markdown 引擎

AnyDoc 是由 Firecrawl 开源的高性能、轻量级文档解析引擎。基于纯 Rust 构建，单次解析中位数小于 5ms，可将 14 种常见办公文档、表格、幻灯片、电子书和 PDF 快速转换为整洁的 GitHub-Flavored Markdown (GFM)。

---

## 🎯 核心特性与支持格式

- **14 种文档格式全覆盖**：
  - **文档**：Word (`.doc`, `.docx`, `.docm`)、OpenDocument Text (`.odt`)、富文本 (`.rtf`)
  - **演示文稿**：PowerPoint (`.ppt`, `.pps`, `.pot`, `.pptx`, `.pptm`, `.ppsx`, `.ppsm`)、OpenDocument Presentation (`.odp`)
  - **表格**：Excel (`.xls`, `.xlsx`, `.xlsm`, `.xlsb`)、OpenDocument Spreadsheet (`.ods`)、逗号分隔值 (`.csv`)
  - **其他**：PDF (`.pdf`，文本型)、电子书 (`.epub`)
- **基于二进制内容自动识别**：根据文件 Magic Number / 二进制头部特征自动识别格式，即使文件无后缀或后缀错误也能准确解析。
- **极致速度**：Rust 本地编译，处理速度达毫秒级（通常 <5ms），大幅提升长文档阅读与提炼效率。

---

## 💻 使用方法

### 1. 终端命令行 (CLI)

本地已全局安装 `anydoc` CLI，直接运行即可：

```bash
# 1. 转换文档并直接输出 Markdown 到终端标准输出 (stdout)
anydoc report.docx

# 2. 转换并保存到指定 Markdown 文件 (-o / --output)
anydoc slides.pptx -o slides.md
anydoc table.xlsx -o table.md

# 3. 从标准输入读取 (stdin) 并指定格式
cat data.csv | anydoc - --format csv

# 4. 下载远程文档并即时流式转换
curl -sL "https://example.com/sample.pdf" | anydoc -
```

> **备用命令 (npx 零安装运行)**：
> ```bash
> npx -y @firecrawl/anydoc <file> [-o output.md]
> ```

---

### 2. Python API

已安装 `firecrawl-anydoc` 包，在 Python 脚本中可直接引用：

```python
import anydoc

# 从本地文件路径转换
markdown_text = anydoc.to_markdown("path/to/document.docx")
print(markdown_text)

# 从字节流 (bytes) 转换（可指定格式：'docx', 'xlsx', 'pptx', 'pdf', 'csv', 'epub' 等）
with open("data.xlsx", "rb") as f:
    content_bytes = f.read()
markdown_text = anydoc.to_markdown_bytes(content_bytes, format="xlsx")
```

---

### 3. Node.js API

```javascript
import { toMarkdown } from '@firecrawl/anydoc';
import { readFileSync } from 'fs';

// 从路径或 Buffer 转换
const buffer = readFileSync('report.docx');
const markdown = await toMarkdown(buffer, { format: 'docx' });
console.log(markdown);
```

---

### 4. 辅助脚本调用

技能内置了 Python 增强封装脚本，支持处理本地路径及网络 URL：

```bash
# 转换本地文件并打印
python3 ~/.workbuddy/skills/anydoc/scripts/anydoc_convert.py --input "/path/to/doc.docx"

# 转换本地文件并存盘
python3 ~/.workbuddy/skills/anydoc/scripts/anydoc_convert.py --input "/path/to/doc.pptx" --output "/path/to/out.md"

# 转换远程 URL 文档
python3 ~/.workbuddy/skills/anydoc/scripts/anydoc_convert.py --url "https://example.com/sample.docx" --output "sample.md"
```

---

## ⚠️ 注意事项与边界约束

1. **扫描版 / 纯图片 PDF**：AnyDoc 为纯文本解析引擎，不包含本地 OCR。如遇到扫描件或纯图片 PDF，解析将提示不支持，需结合 OCR 引擎处理。
2. **大文档处理规范**：对于大型文件或长表格，建议使用 `-o <path>` 保存为 `.md` 文件后再按需切片查看，避免过长输出淹没上下文。
3. **返回码说明**：
   - `0`：转换成功
   - `1`：文档无法读取或无法转换
   - `2`：命令行参数错误
