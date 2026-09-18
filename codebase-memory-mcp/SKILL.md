---
name: codebase-memory-mcp
description: 高性能 AI 代码库知识图谱与记忆引擎 (DeusData/codebase-memory-mcp)。通过 Tree-sitter AST
  解析代码库，构建本地持久化 SQLite 知识图谱，支持极速依赖追踪、架构挖掘、死代码检测、爆炸半径分析与 Cypher 图查询，极大降低 Token 消耗。
disable: false
---


# Codebase Memory MCP

基于 [DeusData/codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) 的高性能代码智能与知识图谱引擎。

## 核心功能

1. **图谱构建（Full-Indexing）**：基于 Tree-sitter 零依赖提取 158 种语言的函数、类、接口、HTTP 路由及跨服务依赖。
2. **极速结构查询（Sub-ms Queries）**：查询调用链、依赖关系、跨服务 Link、死代码检测。
3. **爆破半径/影响分析（Impact Analysis）**：快速评估修改某一函数/接口导致的上下游影响面。
4. **可视化 3D 图谱**：内置 Web 可视化服务（访问 `http://localhost:9749`）。

## 常用命令与操作

### 1. 检查或运行二进制

二进制文件默认安装在：`~/.local/bin/codebase-memory-mcp`

```bash
# 验证版本与安装状态
~/.local/bin/codebase-memory-mcp --version

# 启动 MCP 服务 / 嵌入式 Web 界面
~/.local/bin/codebase-memory-mcp serve
```

### 2. 索引当前项目

在终端或 AI Agent 中发送：
- `Index this project` 或 `为当前项目构建 codebase-memory 图谱`

### 3. MCP 工具与能力

当 MCP Server 启动后，会自动向 Agent 暴露 15 个 MCP 工具：
- `search_symbols`: 符号精确/模糊查找
- `trace_dependencies`: 追踪函数/类的上下游依赖
- `analyze_impact`: 评估变更影响面
- `find_dead_code`: 检测未被调用的废弃代码
- `cypher_query`: 执行自定义 Cypher 图查询

## 运维与更新

```bash
# 重新安装或更新到最新版
curl -fsSL https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.sh | bash
```
