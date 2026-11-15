#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
腾讯文档 MCP 的「代理模式」HTTP 客户端。

背景：AILink 自带的 connector-runtime node 二进制损坏，导致 mcporter 一启动就
V8 崩溃（Check failed: 12 == (*__error()) 于 SetPermissions）。因此无法通过
mcporter 调用 tencent-docs 连接器。

解决方案：tencent-docs 本质是远程 HTTP MCP（baseUrl=https://docs.qq.com/openapi/mcp，
Authorization token 见 ~/.mcporter/mcporter.json）。本模块绕过 mcporter，
直接通过 HTTP(S) 代理 http://172.16.0.11:3128 访问该 MCP 端点，实现 MCP
Streamable HTTP 协议（initialize → notifications/initialized → tools/call），
对外暴露与 sync_utils.call_mcp 相同签名的 call_mcp(tool_name, args) -> dict。
"""
import json
import os
import requests

# 默认值（可通过自身读取 ~/.mcporter/mcporter.json 覆盖）
_DEFAULT_PROXY = os.environ.get("AILINK_MCP_PROXY", "http://172.16.0.11:3128")
_DEFAULT_BASE_URL = os.environ.get("TENCENT_DOCS_MCP_BASE_URL", "https://docs.qq.com/openapi/mcp")
_DEFAULT_TOKEN = os.environ.get("TENCENT_DOCS_MCP_TOKEN", "")


def _load_mcporter_config():
    """从 mcporter 配置读取 baseUrl 与 token（若有）。"""
    cfg = os.path.expanduser("~/.mcporter/mcporter.json")
    try:
        with open(cfg, "r", encoding="utf-8") as f:
            data = json.load(f)
        server = data.get("mcpServers", {}).get("tencent-docs", {})
        base = server.get("baseUrl") or _DEFAULT_BASE_URL
        tok = (server.get("headers") or {}).get("Authorization") or _DEFAULT_TOKEN
        return base, tok
    except Exception:
        return _DEFAULT_BASE_URL, _DEFAULT_TOKEN


class TencentDocsMCPHttpClient:
    """面向腾讯文档远程 MCP 的 Streamable HTTP 客户端（代理模式）。"""

    def __init__(self, base_url=None, token=None, proxy=None):
        self.base_url = base_url or _DEFAULT_BASE_URL
        self.token = token or _DEFAULT_TOKEN
        self.proxy = proxy or _DEFAULT_PROXY
        self._session_id = None
        self._initialized = False
        self._req_id = 0
        self._http = requests.Session()
        self._http.proxies = {"http": self.proxy, "https": self.proxy}
        self._http.headers.update({
            "Authorization": self.token,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        })

    def _post(self, payload):
        headers = {"MCP-Protocol-Version": "2025-03-26"}
        if self._session_id:
            headers["mcp-session-id"] = self._session_id
        r = self._http.post(
            self.base_url,
            data=json.dumps(payload, ensure_ascii=False),
            headers=headers,
            timeout=180,
        )
        sid = r.headers.get("mcp-session-id") or r.headers.get("MCP-Session-Id")
        if sid:
            self._session_id = sid
        r.raise_for_status()
        ct = r.headers.get("content-type", "")
        if "text/event-stream" in ct:
            result = self._parse_sse(r.text, payload.get("id"))
        else:
            # 可能是单条 JSON，也可能是 JSONL/多事件，统一解析
            try:
                result = r.json()
            except Exception:
                result = self._parse_json_multi(r.text)
        if "error" in result:
            raise RuntimeError("MCP 协议错误: %s" % (result["error"],))
        return result.get("result")

    @staticmethod
    def _parse_json_multi(text):
        """容错：兼容单 JSON 或多行 JSON。"""
        t = text.strip()
        if not t:
            raise RuntimeError("MCP 返回为空")
        try:
            return json.loads(t)
        except Exception:
            pass
        for line in t.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except Exception:
                continue
        raise RuntimeError("无法解析 MCP 返回")

    @staticmethod
    def _parse_sse(text, rid):
        for line in text.splitlines():
            s = line.strip()
            if not s.startswith("data:"):
                continue
            data = s[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                obj = json.loads(data)
            except Exception:
                continue
            if obj.get("id") == rid or "result" in obj or "error" in obj:
                return obj
        raise RuntimeError("未找到 SSE 事件结果")

    def initialize(self):
        if self._initialized:
            return
        self._req_id += 1
        self._post({
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "ailink-mcp-proxy", "version": "1.0"},
            },
        })
        # 发送 initialized 通知（失败可忽略）
        try:
            self._http.post(
                self.base_url,
                data=json.dumps({
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                }),
                headers={
                    "MCP-Protocol-Version": "2025-03-26",
                    "Content-Type": "application/json",
                    **({"mcp-session-id": self._session_id} if self._session_id else {}),
                },
                timeout=60,
            )
        except Exception:
            pass
        self._initialized = True

    def call_tool(self, tool_name, args):
        self.initialize()
        self._req_id += 1
        res = self._post({
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args or {}},
        })
        if isinstance(res, dict) and res.get("isError"):
            raise RuntimeError("工具 %s 调用出错: %s" % (tool_name, res))
        content = (res or {}).get("content", [])
        text = "".join(
            item.get("text", "") for item in content if item.get("type") == "text"
        )
        if isinstance(text, str) and text.strip():
            try:
                return json.loads(text)
            except Exception:
                return {"_raw": text}
        return res


_client = None


def call_mcp(tool_name: str, args: dict) -> dict:
    """与 sync_utils.call_mcp 签名一致的代理模式客户端入口。"""
    global _client
    if _client is None:
        base, tok = _load_mcporter_config()
        _client = TencentDocsMCPHttpClient(base_url=base, token=tok)
    return _client.call_tool(tool_name, args or {})