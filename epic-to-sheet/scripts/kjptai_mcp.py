#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kjptai_mcp.py — 国泰海通科技平台(kjptai) MCP 直连客户端
=========================================================
从 ~/.workbuddy/mcp.json 读取 kjptai 服务器配置（streamable_http + Bearer token），
提供 initialize + tools/call 两段式 RPC，供脚本批量调用 query_requirement 等工具。
用法（模块内直接 import，也可命令行单发）:
    python3 kjptai_mcp.py query_requirement '{"demandId": "R2609090038"}'
"""
import json
import os
import sys
import uuid
import requests

MCP_CFG = os.path.expanduser("~/.workbuddy/mcp.json")


def _server_cfg():
    with open(MCP_CFG, encoding="utf-8") as f:
        cfg = json.load(f)
    srv = cfg.get("mcpServers", {}).get("kjptai")
    if not srv:
        raise RuntimeError("~/.workbuddy/mcp.json 中未找到 kjptai 服务器配置")
    return srv["url"], dict(srv.get("headers", {}))


class KjptaiClient:
    """streamable_http 协议客户端：initialize 握手后 tools/call。"""

    def __init__(self):
        self.url, self.headers = _server_cfg()
        for k, v in [("Accept", "application/json, text/event-stream"),
                     ("Content-Type", "application/json")]:
            self.headers.setdefault(k, v)
        self.session_id = None
        self._initialized = False

    def _post(self, payload):
        h = dict(self.headers)
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        s = requests.Session()
        s.trust_env = False  # 内网域直连：macOS 系统代理(172.16.0.11:3128) 对 fintech.gtht.com.cn 隧道 502
        s.headers.update(h)
        r = s.post(self.url, data=json.dumps(payload, ensure_ascii=False), stream=True,
                   timeout=(15, 60), verify=True)
        sess = r.headers.get("Mcp-Session-Id")
        if sess:
            self.session_id = sess
        obj, error = None, None
        try:
            for raw in r.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                line = raw[5:].strip() if raw.startswith("data:") else raw.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get("id") != payload.get("id"):
                    continue
                if "error" in obj:
                    error = obj["error"]
                break
        finally:
            r.close()
        if error:
            raise RuntimeError(f"kjptai MCP error: {json.dumps(error, ensure_ascii=False)}")
        if obj is None:
            raise RuntimeError(f"kjptai MCP 无响应: {payload.get('method')}")
        return obj

    def call(self, tool, args):
        rid = str(uuid.uuid4())
        if not self._initialized:
            self._post({"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "initialize",
                        "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                                   "clientInfo": {"name": "kjtcli", "version": "1.0"},
                                   "serverCapabilities": {}}})
            self._initialized = True
        obj = self._post({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                          "params": {"name": tool, "arguments": args}})
        return obj.get("result", {})


def extract_text(result):
    """从 tools/call result 中稳健提取文本内容。
    兼容两种返回：structuredContent 直接存放字段 / content[].text 为 JSON 字符串。"""
    if result is None:
        return {}
    # 尝试 structuredContent
    sc = result.get("structuredContent")
    if isinstance(sc, dict) and sc:
        return sc
    # 尝试 content[].text（可能为 JSON 字符串）
    content = result.get("content") or []
    texts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            texts.append(item.get("text", ""))
    blob = "\n".join(texts).strip()
    if not blob:
        return result
    try:
        parsed = json.loads(blob)
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict) and "structuredContent" in parsed[0]:
            return parsed[0].get("structuredContent", parsed[0])
        if isinstance(parsed, dict) and "structuredContent" in parsed:
            return parsed["structuredContent"]
        return parsed
    except Exception:
        return {"raw_text": blob}


def query_requirement_detail(client, demand_id):
    """查询单条需求详情，返回结构化 dict（失败时返回 {demandId, error}）。"""
    try:
        res = client.call("query_requirement", {"demandId": demand_id})
        return extract_text(res)
    except Exception as e:
        return {"demandId": demand_id, "error": str(e)}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: kjptai_mcp.py <tool> '<json-args>' [--raw]")
        sys.exit(1)
    tool = sys.argv[1]
    args = json.loads(sys.argv[2])
    c = KjptaiClient()
    r = c.call(tool, args)
    if "--raw" in sys.argv:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(json.dumps(extract_text(r), ensure_ascii=False, indent=1))
