#!/usr/bin/env python3
"""OpenViking MCP 轻量客户端（streamable_http）。用法见 SKILL.md。
子命令：find <query> | list <uri> | glob <pattern> [uri] | read <uri>
"""
import json
import sys
import urllib.request
import urllib.error

URL = "https://csgl.gtht.com.cn/openviking/server/mcp"
API_KEY = "Y3NnbA.dXNlcjQ.YWMzZjY2NGVlOTg4ZjBhZDZjOTc0YzU5MjcyMzFhNDI5MmRkNTEyYzI4MGQ0MGMxNGJkZmMzOTdiM2NlOWY5Yg"
HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "X-Api-Key": API_KEY}


def rpc(method, params=None, msg_id=1, session_id=None, timeout=60):
    body = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        body["params"] = params
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(URL, data=data, method="POST")
    for k, v in HEADERS.items():
        req.add_header(k, v)
    if session_id:
        req.add_header("Mcp-Session-Id", session_id)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        return None, e.headers, e.read().decode("utf-8", "ignore")
    except Exception as e:
        return {"_error": str(e)}, None, str(e)
    sid = resp.headers.get("Mcp-Session-Id")
    raw = resp.read().decode("utf-8", "ignore")
    result = None
    for line in raw.splitlines():
        if line.startswith("data:"):
            try:
                result = json.loads(line[len("data:"):].strip())
            except Exception:
                pass
    return result, resp.headers, raw


def call(name, args, sid, mid, timeout=60):
    res, _, _ = rpc("tools/call", {"name": name, "arguments": args}, msg_id=mid, session_id=sid, timeout=timeout)
    if res and "result" in res:
        return "\n".join(c["text"] for c in res["result"].get("content", []) if c.get("type") == "text")
    if res and "_error" in res:
        return "ERROR: " + res["_error"]
    return json.dumps(res, ensure_ascii=False)


def main():
    if len(sys.argv) < 3:
        print("usage: openviking_mcp.py <find|list|glob|read> <arg> [uri]")
        sys.exit(1)
    cmd, arg = sys.argv[1], sys.argv[2]
    uri = sys.argv[3] if len(sys.argv) > 3 else None

    init, h, _ = rpc("initialize", {
        "protocolVersion": "2024-11-05", "capabilities": {},
        "clientInfo": {"name": "wb", "version": "1.0"}})
    sid = h.get("Mcp-Session-Id")
    rpc("notifications/initialized", None, msg_id="init", session_id=sid)

    if cmd == "find":
        print(call("find", {"query": arg, "limit": 15}, sid, 1))
    elif cmd == "list":
        print(call("list", {"uri": arg}, sid, 1))
    elif cmd == "glob":
        args = {"pattern": arg}
        if uri:
            args["uri"] = uri
        print(call("glob", args, sid, 1))
    elif cmd == "read":
        print(call("read", {"uris": arg}, sid, 1))
    else:
        print("unknown cmd:", cmd)


if __name__ == "__main__":
    main()
