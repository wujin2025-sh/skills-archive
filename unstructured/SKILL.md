---
name: insight-prism
description: 当需要解析、切分、提取或清理原始文档（如 PDF、Word DOCX、PPTX、XLSX、HTML、XML、EML、Markdown、TXT 等）为结构化文本元素时使用。在从用户提供的文件中提取内容或为下游 ML/LLM 检索分析准备文档时可主动使用。
homepage: https://github.com/Unstructured-IO/unstructured
compatibility: 需要安装 python3.12 及 unstructured 包。
platforms: [macos, linux, windows]
metadata: {"openclaw":{"requires":{"bins":["python3.12"]},"emoji":"📄"}}
---

# 非结构化文档解析技能 (Unstructured Document Parsing)

将非结构化文档（PDF、HTML、DOCX、PPTX、XML 等）解析、切分、提取与清洗为结构化的文本或 JSON 元素。

## 1. 适用与不适用场景

**适用本技能的场景：**
- 从文档中提取原始文本、结构性元素（标题、正文叙述、表格、列表）及元数据。
- 为 RAG（检索增强生成）管道、LLM 微调或搜索索引预处理文档。
- 切分处理复杂格式文档，如 PDF、DOCX、PPTX、XLSX、EML、HTML 和 Markdown。

**不适合本技能的场景：**
- 对单张独立图片进行轻量级 OCR 文字识别（除非需要提取结构化的文档元素）。
- 生成新文件或格式化绘制图表/可视化表达（请改用 `drawio` 或 `mermaid`）。

## 2. 前置条件

- **Python 版本**：需要 Python 3.12（安装路径 `/usr/local/bin/python3.12`）。
- **依赖包**：核心包及标准文档扩展已安装在 Python 3.12 环境下。

测试安装状态：
```bash
python3.12 -c "import unstructured; print(unstructured.__version__)"
```

## 3. Python API 使用指南

以下是使用 `unstructured` 库的最常用模式：

### 1. 切分文档（自动类型检测）

`partition` 函数可以自动检测文件类型并将其分发至对应的解析器。

```python
from unstructured.partition.auto import partition

# 切分本地文档
elements = partition(filename="path/to/document.pdf")

# 检查解析结果
for element in elements:
    print(f"[{element.category}] {element.text}")
```

### 2. 针对特定格式提取

你也可以直接导入针对特定格式的切分器：

```python
from unstructured.partition.docx import partition_docx
from unstructured.partition.pdf import partition_pdf

# 解析 Word 文档 (.docx)
docx_elements = partition_docx(filename="document.docx")

# 解析 PDF（提取表格，必要时使用 OCR）
pdf_elements = partition_pdf(
    filename="document.pdf",
    strategy="hi_res",          # 使用版面模型提取表格/图像
    infer_table_structure=True  # 将表格转化为 html/text 结构
)
```

### 3. 将元素转换为字典 / JSON

```python
from unstructured.staging.base import convert_to_dict

# 将元素列表转化为字典列表
elements_dict = convert_to_dict(elements)

# 导出为 JSON 文件
import json
with open("output.json", "w") as f:
    json.dump(elements_dict, f, indent=2)
```

### 4. 文本清洗

Unstructured 提供了文本清洗函数，方便在发送给 LLM 之前清理文本：

```python
from unstructured.cleaners.core import clean, group_broken_paragraphs

raw_text = "This is a paragraph  with   extra spaces.\n\nAnd some new lines."
cleaned_text = clean(raw_text, extra_whitespace=True, dashes=True, bullets=True)
```

## 4. 支持的元素分类 (Element Categories)

- `Title`：标题、小节标题。
- `NarrativeText`：标准正文段落。
- `ListItem`：无序或有序列表项。
- `Table`：表格（元数据中可包含 HTML 表达方式）。
- `Header` / `Footer`：页眉 / 页脚文档标记。
- `UncategorizedText`：无法归类的未分类文本元素。
