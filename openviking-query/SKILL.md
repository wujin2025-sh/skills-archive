---
name: openviking-query
description: 通过 OpenViking MCP（csgl.gtht.com.cn）查询国泰海通内部知识库（需求/语料/文档）。当用户要"查 openviking""查科技平台知识库""查某需求/董监高/某主题文件"时使用。支持 find 语义检索、list 列目录、glob 按文件名通配、read 读正文。
---

# OpenViking 知识库查询

OpenViking 是火山引擎开源的 Agent 上下文数据库，GTHT 内部部署在 `https://csgl.gtht.com.cn/openviking/server`，MCP 端点为 `/openviking/server/mcp`。

## 配置（已写入 ~/.workbuddy/mcp.json）
```json
"openviking": {
  "transport": "streamable_http",
  "url": "https://csgl.gtht.com.cn/openviking/server/mcp",
  "headers": { "X-Api-Key": "<API_KEY>", "Accept": "application/json, text/event-stream", "Content-Type": "application/json" }
}
```
鉴权：`X-Api-Key` 或 `Authorization: Bearer` 均可（已验证两者都返回 200）。
WorkBuddy 内启用需在连接器管理页面对该 MCP 点 "Trust" 才会加载 `mcp__openviking__*` 工具；在此之前可用本技能脚本直接走 JSON-RPC 查询。

## 查询脚本
路径：`~/.workbuddy/skills/openviking-query/openviking_mcp.py`
```bash
PY=/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python
# 语义检索
$PY openviking_mcp.py find "上海董监高"
# 列根资源（先看清有哪些 resource）
$PY openviking_mcp.py list "viking://resources/"
# 按文件名通配（务必限定在某个 resource 内，全库 glob 易超时）
$PY openviking_mcp.py glob "**/*董监高*" "viking://resources/科技平台需求知识-20260622.zip/"
# 读正文
$PY openviking_mcp.py read "viking://resources/.../xxx.md"
```

## 关键经验（踩坑）
- 全局 `glob "**/*董监高*"`（不限 resource）会**超时**（HTTP chunked 读超时）。必须先 `list viking://resources/` 找到资源名，再在其目录下 glob。
- `find` 是语义检索，对 "上海董监高文件" 这类词会偏向召回"机构"等高频近义词，不一定命中文件名。**要按文件名找，用 glob 限定资源目录最稳**。
- streamable_http 需在每个非初始化请求带 `Mcp-Session-Id`（初始化响应头返回），脚本已处理。
- 资源根目录：`viking://resources/`，已知资源有：`科技平台需求知识-20260622.zip`、`行业测试大模型语料库`、`2026年6月份周末测试文档`、`交易结算创新`、`requirement.zip`、`方案设计_账户新一代OTC账户相关改造需求设计_V1.1`。
