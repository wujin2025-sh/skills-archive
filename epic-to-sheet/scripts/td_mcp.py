#!/usr/bin/env python3
"""精简 MCP Streamable-HTTP 客户端：调用 tencent-docs MCP 工具（requests 走 macOS 系统代理）"""
import json, sys, uuid, requests

BASE = "https://docs.qq.com/openapi/mcp"
with open("/Users/wujin/.mcporter/credentials.json", encoding="utf-8") as f:
    cred = json.load(f)
TOKEN = list(cred["entries"].values())[0]["tokens"]["access_token"]
HEADERS = {"Authorization": f"Bearer {TOKEN}",
           "Content-Type": "application/json",
           "Accept": "application/json, text/event-stream"}


def rpc(method: str, params: dict = None):
    req_id = str(uuid.uuid4())
    payload = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        payload["params"] = params
    r = requests.post(BASE, headers=HEADERS, data=json.dumps(payload, ensure_ascii=False),
                      stream=True, timeout=(15, 240))
    result, error = None, None
    mcp_session = r.headers.get("Mcp-Session-Id")
    for raw in r.iter_lines(decode_unicode=True):
        if not raw:
            continue
        if raw.startswith("data:"):
            raw = raw[5:].strip()
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        if obj.get("id") != req_id:
            continue
        if "result" in obj:
            result = obj["result"]
        if "error" in obj:
            error = obj["error"]
        break
    r.close()
    if error:
        raise RuntimeError(f"MCP error: {json.dumps(error, ensure_ascii=False)}")
    if result is None:
        raise RuntimeError(f"无响应: {method}")
    if mcp_session:
        HEADERS["Mcp-Session-Id"] = mcp_session
    return result


def call_tool(tool_name: str, args: dict):
    # 初始化
    rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "tdcli", "version": "1.0"}})
    return rpc("tools/call", {"name": tool_name, "arguments": args})


if __name__ == "__main__":
    tool = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    out = call_tool(tool, args)
    print(json.dumps(out, ensure_ascii=False, indent=2))
