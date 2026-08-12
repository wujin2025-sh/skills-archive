---
name: crawl4ai
description: AI驱动的网页抓取框架，用于从网站提取结构化数据。支持AI智能解析、处理动态内容及复杂HTML结构。
---

# Crawl4ai 网页抓取框架

## 概述

Crawl4ai 是一个 AI 驱动的网页抓取框架，旨在高效地从网站提取结构化数据。它将传统 HTML 解析与 AI 能力结合，可以轻松处理动态 JavaScript 内容、智能提取文本，并清洗结构化复杂网页的数据。

> [!IMPORTANT]
> **默认保存路径规范**：使用本技能提取/生成的 Markdown (.md) 文件，默认必须归档保存至目录：
> `/Volumes/Macintosh HD_Data/obsidian/300_Resources/html文件/`

## 何时使用本技能

当需要执行以下操作时使用：
- 从网页中提取结构化数据（商品、文章、表单、表格等）
- 抓取包含动态内容或复杂 JavaScript 的网站
- 清洗并规范化来自各种 HTML 结构提取的数据
- 与返回 HTML 的 API 或 Web 服务交互
- 通过直接抓取解决 CORS 跨域限制
- 高可靠地大批量处理网页内容

**触发短语：**
- "从这个网站提取数据"
- "抓取此页面的 [特定数据]"
- "解析这段 HTML"
- "从 [URL] 获取数据"
- "从 [网站] 提取结构化信息"
- "抓取 [网站] 的 [数据类型]"
- "网页抓取 [URL]"

## 快速开始

### 基本用法

```python
from crawl4ai import AsyncWebCrawler, BrowserMode

async def scrape_page(url):
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url=url,
            browser_mode=BrowserMode.LATEST,
            headless=True
        )
        return result.markdown, result.clean_html
```

### 提取结构化数据

```python
from crawl4ai import AsyncWebCrawler, JsonModeScreener
import json

async def extract_products(url):
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url=url,
            screenshot=True,
            javascript=True,
            bypass_cache=True
        )
        # 提取商品数据
        products = []
        for item in result.extracted_content:
            if item['type'] == 'product':
                products.append({
                    'name': item['name'],
                    'price': item['price'],
                    'url': item['url']
                })
        return products
```

## 常见任务

### 网页抓取基础

**场景：** 用户想抓取某个网站的所有文章标题。

```python
from crawl4ai import AsyncWebCrawler

async def scrape_articles(url):
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url=url,
            javascript=True,
            verbose=True
        )
        # 从 HTML 中提取文章标题
        articles = result.extracted_content if result.extracted_content else []
        titles = [item.get('name', item.get('text', '')) for item in articles]
        return titles
```

**触发词：** "抓取此网站的文章标题" 或 "从 [URL] 获取所有标题"

### 动态内容处理

**场景：** 网站通过 JavaScript 异步加载数据。

```python
from crawl4ai import AsyncWebCrawler

async def scrape_dynamic_site(url):
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url=url,
            javascript=True,  # 等待 JS 执行
            wait_for="body",   # 等待特定元素加载
            delay=1.5,         # 加载后等待时间(秒)
            headless=True
        )
        return result.markdown
```

**触发词：** "抓取这个动态网站" 或 "该页面需要 JavaScript 来加载数据"

### 结构化数据提取

**场景：** 提取特定的字段（如价格、描述等）。

```python
from crawl4ai import AsyncWebCrawler

async def extract_product_details(url):
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url=url,
            screenshot=True,
            js_code="""
                const products = document.querySelectorAll('.product');
                return Array.from(products).map(p => ({
                    name: p.querySelector('.name')?.textContent,
                    price: p.querySelector('.price')?.textContent,
                    url: p.querySelector('a')?.href
                }));
            """
        )
        return result.extracted_content
```

**触发词：** "从该页面提取商品详情" 或 "从 [URL] 获取价格和名称"

### HTML 清洗与解析

**场景：** 清理杂乱的 HTML 并提取干净的纯文本。

```python
from crawl4ai import AsyncWebCrawler

async def clean_and_parse(url):
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url=url,
            remove_tags=['script', 'style', 'nav', 'footer', 'header'],
            only_main_content=True
        )
        # 清洗并返回 markdown
        clean_text = result.clean_html
        return clean_text
```

**触发词：** "清洗此 HTML" 或 "提取此页面的主要内容"

## 高级特性

### 自定义 JavaScript 注入

```python
async def custom_scrape(url, custom_js):
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url=url,
            js_code=custom_js,
            js_only=True  # 仅执行 JS，不下载其他资源
        )
        return result.extracted_content
```

### 会话管理 (Session Management)

```python
from crawl4ai import AsyncWebCrawler

async def multi_page_scrape(base_url, urls):
    async with AsyncWebCrawler() as crawler:
        results = []
        for url in urls:
            result = await crawler.arun(
                url=url,
                session_id=f"session_{url}",
                bypass_cache=True
            )
            results.append({
                'url': url,
                'content': result.markdown,
                'status': result.success
            })
        return results
```

## 最佳实践

1. **始终检查网站是否允许抓取** - 尊重 robots.txt 和服务条款
2. **使用适当的请求延迟** - 在请求之间添加延迟以避免给服务器造成过大压力
3. **优雅处理错误** - 实现重试逻辑与异常捕获
4. **选择性提取数据** - 仅提取所需内容，避免倾倒整页无用数据
5. **可靠存储数据** - 将提取的数据保存为结构化格式 (JSON, CSV)
6. **清洗 URL** - 处理重定向和格式错误的 URL

## 错误处理

```python
async def robust_scrape(url):
    try:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(
                url=url,
                timeout=30000  # 30秒超时设置
            )
            if result.success:
                return result.markdown, result.extracted_content
            else:
                print(f"抓取失败: {result.error_message}")
                return None, None
    except Exception as e:
        print(f"抓取异常: {str(e)}")
        return None, None
```

## 输出格式

Crawl4ai 支持多种输出格式：

- **Markdown**：干净且易读的文本 (`result.markdown`)
- **Clean HTML**：结构化清洗后的 HTML (`result.clean_html`)
- **Extracted Content**：结构化 JSON 数据 (`result.extracted_content`)
- **Screenshot**：网页截图图像 (`result.screenshot`)
- **Links**：页面上找到的所有链接 (`result.links`)

## 资源目录说明

### scripts/
常用抓取操作的 Python 脚本：
- `scrape_single_page.py` - 单页抓取基础工具
- `scrape_multiple_pages.py` - 带分页的批量抓取
- `extract_from_html.py` - HTML 解析辅助脚本
- `clean_html.py` - HTML 清洗工具

### references/
参考文档与示例：
- `api_reference.md` - 完整 API 文档
- `examples.md` - 常见使用场景和模式
- `error_handling.md` - 故障排查与错误处理指南

