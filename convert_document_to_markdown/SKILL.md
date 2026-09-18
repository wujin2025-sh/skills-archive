---
name: convert_document_to_markdown
description: '当用户要求你阅读、解析、总结、翻译或提取某份文件（或链接）的内容时，必须调用此工具。此工具将复杂的文件格式转换为你易于理解的纯 Markdown
  文本。 支持的文件类型包括：PDF、Word (.docx)、PowerPoint (.pptx)、Excel (.xlsx)、图像、音频、HTML 网页、CSV、JSON、XML、ZIP
  等。 调用注意事项： 1. 如果用户提供的是本地路径，请原样传入。 2. 如果用户提供的是网页链接或下载 URL，请传入 URL。 3. 获取到 Markdown
  文本后，请根据用户的具体指令（如总结摘要、提取表格、翻译等）对文本进行二次处理并回复用户。

  '
disable: false
---


# Convert Document to Markdown (智能文档解析/转换)

本技能利用 `markitdown` 库将各类复杂格式的本地文件或网页链接转换为纯净、结构化的 Markdown 文本，并支持开启多模态大模型的视觉解析（如识别图片或复杂 PPT 图表）。

## 工作流程

### Step 1: 确定参数
从用户输入或上下文中提取以下两个参数：

| 参数 | 类型 | 是否必填 | 描述 |
|------|------|----------|------|
| `file_source` | String | **是** | 本地文件的绝对路径或网络/下载 URL。 |
| `enable_vision` | Boolean | 否 | 是否启用视觉解析（常用于图片内容或复杂的 PPT 图表）。默认 `false`。 |

### Step 2: 运行转换脚本
在终端中执行以下命令进行转换：

- **.workbuddy 路径**：
```bash
python3 /Users/wujin/.workbuddy/skills/convert_document_to_markdown/scripts/convert_document_to_markdown.py --file_source "<file_source>"
```
- **.gemini/config 全局路径**：
```bash
python3 /Users/wujin/.gemini/config/skills/convert_document_to_markdown/scripts/convert_document_to_markdown.py --file_source "<file_source>"
```

如果需要启用视觉解析：
- **.workbuddy 路径**：
```bash
python3 /Users/wujin/.workbuddy/skills/convert_document_to_markdown/scripts/convert_document_to_markdown.py --file_source "<file_source>" --enable_vision
```
- **.gemini/config 全局路径**：
```bash
python3 /Users/wujin/.gemini/config/skills/convert_document_to_markdown/scripts/convert_document_to_markdown.py --file_source "<file_source>" --enable_vision
```


### Step 3: 读取转换后的文本并向用户回复
1. 执行脚本后，它会直接在标准输出 (stdout) 中输出转换后的 Markdown 文本。
2. 切勿直接将转换后的 Markdown 源码全文倾倒给用户。你需要仔细阅读和思考，提取与用户问题相关的核心数据。
3. 如果文档包含表格数据（在 Markdown 中以 `|` 分隔），请在分析时保持数据的逻辑对应关系，确保你的计算或摘要准确无误。
4. 如果读取失败，请如实告知用户并提供排查建议（如检查文件是否存在或损坏）。

---

## Tool Definition (适用于 OpenAI/LangChain 等平台)

```json
{
  "name": "convert_document_to_markdown",
  "description": "当用户要求你阅读、解析、总结或提取某份文件（或链接）的内容时，必须调用此工具。支持格式：PDF, Word, PPT, Excel, 图像, HTML等。该工具将返回便于你分析的纯净 Markdown 文本。",
  "parameters": {
    "type": "object",
    "properties": {
      "file_source": {
        "type": "string",
        "description": "文件的本地绝对路径或有效的网络 URL。"
      },
      "enable_vision": {
        "type": "boolean",
        "description": "是否启用多模态大模型的视觉解析能力。仅在需要识别图片内容或复杂PPT图表时设为 true。默认值为 false。"
      }
    },
    "required": ["file_source"]
  }
}
```
