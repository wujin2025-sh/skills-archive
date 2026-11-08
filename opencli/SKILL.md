---
name: opencli
description: AI 驱动的万能网站 CLI 适配器（OpenCLI）。支持 170+ 网站适配器（包含微信公众号文章转 Markdown 且图片本地化、搜狗微信搜索、B站官方 AI 总结/字幕/搜索/评论、雪球、东方财富、同花顺、通达信、微博、小红书、微信读书、知乎、维基百科等）。支持 Chrome 浏览器桥接复用真实用户登录态与 WAF 突破，极度适合非虚构深度写作、历史史料溯源、研报与多媒体内容提取。
triggers:
  - opencli
  - 微信文章下载
  - 微信文章转markdown
  - 微信文章爬取
  - 搜狗微信
  - B站AI总结
  - B站字幕提取
  - 视频总结
  - 网站cli
---

# OpenCLI：AI 驱动的万能网站 CLI 适配器

> **定位**：打破网站的反爬与 WAF 限制，将 170+ 主流中英文网站直接转化为终端 CLI 命令。
> **核心优势**：直接复用本地 Chrome 浏览器会话与 Cookie，无需逆向签名；原生输出结构化 JSON / Markdown；支持一键抓取文章与本地化图片。

---

## 🚀 写作与史料研究核心命令速查

### 1. 微信公众号文章抓取（带图片本地化）
```bash
# 抓取单篇微信公众号文章为本地 Markdown，并自动下载内嵌图片
opencli weixin download --url "https://mp.weixin.qq.com/s/xxxxxx" --output "./downloads" --download-images true

# 搜狗微信文章关键词搜索（获取文章候选与链接）
opencli weixin search "327国债期货" -f table
```

### 2. 视频与纪录片信息提取（B站 / YouTube）
```bash
# 获取 B站视频官方 AI 总结（含分段大纲与时间戳，极速通读长视频/纪录片）
opencli bilibili summary BV1xxxxxx

# 提取 B站视频全文字幕（用于人物访谈、纪录片台词核对）
opencli bilibili subtitle BV1xxxxxx

# 搜索 B站相关视频与纪录片
opencli bilibili search "国泰君安 历史纪录片" --limit 10 -f table

# 获取视频详细元数据（播放量、投币、作者、简介）
opencli bilibili video BV1xxxxxx
```

### 3. 金融、研报与证券社区史料挖掘
```bash
# 雪球股票讨论与观点抓取
opencli xueqiu search "国泰君安" -f json
opencli xueqiu hot -f table

# 东方财富公告与资讯
opencli eastmoney search "万国证券" -f table

# 微博热点与历史讨论
opencli weibo search "327事件" -f json
```

### 4. 书籍、知识库与社群
```bash
# 微信读书 / 微信读书官方版
opencli weread search "金融史" -f table
opencli weread-official search "大国证券" -f table

# 知乎深度回答
opencli zhihu search "申银万国合并历史" -f table
```

---

## 🛠️ 系统诊断与 Browser Bridge 桥接配置

OpenCLI 分为两类命令：
1. **纯 API 模式**：无需浏览器，直接调用官方/镜像 API 获取数据。
2. **Browser 桥接模式**（带 `Browser: yes` 标记）：如 `opencli weixin download`、`opencli xiaohongshu` 等，需复用真实 Chrome 会话以绕过 WAF。

### 运行环境诊断
```bash
opencli doctor
```

### 启用 Chrome 扩展（仅需配置一次）
若提示 `Browser Bridge extension not connected`：
1. 打开 Chrome，访问 `chrome://extensions/`。
2. 开启右上角 **「开发者模式」(Developer mode)**。
3. 点击 **「加载已解包的扩展程序」(Load unpacked)**。
4. 选择插件目录（可从 [OpenCLI Releases](https://github.com/jackwener/opencli/releases) 下载解压的 extension 文件夹）。
5. 扩展加载后即可无缝复用当前 Chrome 中的全部登录状态与 Cookie。

---

## 💡 官方内置能力与技能扩展
OpenCLI 官方自带 4 个进阶技能，可通过以下命令查询：
```bash
# 查看 OpenCLI 进阶技能列表
opencli skills list

# 查看浏览器驱动指南
opencli skills read opencli-browser -f plain

# 发现新网站适配器
opencli list <关键词>
```
