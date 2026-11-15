---
name: codebase-memory-mcp
description: 高性能 AI 代码库知识图谱与记忆引擎 (DeusData/codebase-memory-mcp)。通过 Tree-sitter AST
  解析代码库，构建本地持久化 SQLite 知识图谱，支持极速依赖追踪、架构挖掘、死代码检测、爆炸半径分析与 Cypher 图查询，极大降低 Token 消耗。
disable: false
---


# Codebase Memory MCP

基于 [DeusData/codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) 的高性能代码智能与知识图谱引擎。

## 核心功能

1. **图谱构建（Full-Indexing）**：基于 Tree-sitter 零依赖提取 158 种语言的函数、类、接口、HTTP 路由及跨服务依赖（本机 v0.10.0；上游当前 README 已为 163 语言 / 17 工具，升级后数字会变）。
2. **极速结构查询（Sub-ms Queries）**：查询调用链、依赖关系、跨服务 Link、死代码检测。
3. **爆破半径/影响分析（Impact Analysis）**：快速评估修改某一函数/接口导致的上下游影响面。
4. **可视化 3D 图谱**：内置 Web 可视化服务（访问 `http://localhost:9749`）。

## 常用命令与操作

### 1. 检查或运行二进制

二进制文件默认安装在：`~/.local/bin/codebase-memory-mcp`

```bash
# 验证版本与安装状态
~/.local/bin/codebase-memory-mcp --version

# 无参数运行 = 在 stdio 上启动 MCP Server（通常由客户端配置自动拉起）
~/.local/bin/codebase-memory-mcp

# 单次本地调用某工具后退出
~/.local/bin/codebase-memory-mcp cli --json list_projects

# 启用 3D 可视化（默认 http://localhost:9749，设置会持久化）
~/.local/bin/codebase-memory-mcp --ui=true --port=9749
```

> v0.10.0 没有 `serve` 子命令；旧文档里的 `... serve` 会报错。

### 2. 索引当前项目

在终端或 AI Agent 中发送：
- `Index this project` 或 `为当前项目构建 codebase-memory 图谱`

### 3. MCP 工具（v0.10.0 --help 实测，共 15 个）

**索引与状态**
- `index_repository` 索引仓库（含跨仓库模式）、`index_status` 索引与 watcher 状态
- `list_projects` / `delete_project` 项目清单与删除
- `check_index_coverage` 覆盖率检查：避免把「未索引到」误判为「仓库里不存在」

**查询与检索**
- `search_graph` 图 / 语义检索（`semantic_query` 是它的参数，不是独立工具）
- `query_graph` Cypher-like 自定义图查询
- `search_code` 图增强 grep（仅覆盖已索引文件）、`get_code_snippet` 取源码片段
- `get_graph_schema` 图 schema、`get_architecture` 架构摘要

**追踪与变更**
- `trace_path` 路径追踪（调用 / 拓扑 / 部署）、`detect_changes` 未提交变更 → 受影响符号 + 风险分级
- `ingest_traces` 注入运行时实测调用关系（静态调用路径 ≠ 实际执行）
- `manage_adr` 持久化架构决策记录

> ⚠️ 旧版文档中的 `search_symbols` / `trace_dependencies` / `analyze_impact` / `find_dead_code` / `cypher_query` 是**能力描述，不是真实工具名**，调用会报 unknown tool；对应能力分别落在 `search_graph`、`trace_path`+`query_graph`、`detect_changes`、`query_graph`、`query_graph`。
> ⚠️ Graphify 的 MCP 也暴露 `query_graph`，两者同时挂载会撞工具名，需在客户端做命名空间区分。

## 性能实测与避坑（2026-11-12，本机 i7-8750H / 16GB / v0.10.0）

- 真实库规模：`jzqs` 435K nodes / 1.96M edges / 1.44GB，`spbsrc` 373K / 1.40M / 1.12GB，`cszx` 276K / 985K / 624MB。
- **必须走常驻 MCP**：`cli` one-shot 每次进程初始化约 2.3~10s（与库大小基本无关），MCP `initialize` 冷启动约 2.3s 但只付一次。批量调用不要用 `cli` 循环。
- 慢的是工具层不是存储层：纯 SQLite 只读直连 FTS5 BM25 2~7ms、边索引点查 <0.1ms、全表 `GROUP BY label` 约 100ms。
- 常驻 MCP 热调用实测（spbsrc）：`search_graph` name_pattern ~172ms、`trace_path` depth3 ~197ms、BM25 ~578ms、`get_architecture` 全图聚合 ~2.6s。
- **避免无起点全边 Cypher**：`MATCH (n)-[r:CALLS]->(m) RETURN ... LIMIT 10` 在 1.4M 边上约 23s，带 `WHERE` 起点仍约 10s。先用 `search_graph` / `trace_path` 定位起点再查子图。
- 官方 `<1ms Cypher / <10ms 名称搜索` 是 Apple M3 Pro + 上游较新版本、带起点的关系遍历；本机 0.10.0 + 2018 年 i7 + 磁盘 97% 满达不到。对外引用性能数字必须注明机型、版本与查询形态。
- 磁盘剩余空间过少会放大冷读延迟；建议留足空间并升级到上游 17 工具版本后复测。

## 运维与更新

```bash
# 重新安装或更新到最新版
curl -fsSL https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.sh | bash
```
