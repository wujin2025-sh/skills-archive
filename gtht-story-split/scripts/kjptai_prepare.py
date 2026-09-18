#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kjptai MCP 通用 prepare + 令牌提取工具（gtht-story-split / gtht-accept-review 共用）

背景：kjptai MCP 两段式确认中，confirmationToken 藏在 prepare 响应 structuredContent.data 里，
工具渲染层只显示 content[0].text 摘要，Agent 拿不到令牌。本脚本 HTTP 直连 kjptai MCP，
一步完成 prepare + 摘要提取 + 令牌提取 + requestId 生成，省掉「对话内 prepare → HTTP 重放」两遍调用。

用法：
  python kjptai_prepare.py --tool create_story --args '{"demandId":"R2608130111", ...}'
  python kjptai_prepare.py --tool start_technical_evaluation --args '{"demandId":"R2608130111","reloadEvaluateMessage":"0"}'
  python kjptai_prepare.py --tool add_requirement_review_minutes --args '{"demandId":"...", ...}'

输出：
  1. 打印确认摘要（content[0].text，供向用户展示并等待明确确认）
  2. 保存 /tmp/kjptai_confirm_params.json：
     {"tool": ..., "confirmationToken": ..., "expectedUpdateTime": ..., "sessionId": ...,
      "requestId": <新UUID, 提交时复用>, "args": <prepare 原参数>}
  提交时在对话内用 MCP 工具携带 confirmed=true + 上述字段完成落库。
"""
import argparse
import json
import os
import ssl
import sys
import urllib.request
import uuid

MCP_JSON = os.path.expanduser("~/.workbuddy/mcp.json")
OUT = "/tmp/kjptai_confirm_params.json"


def load_server():
    cfg = json.load(open(MCP_JSON, encoding="utf-8"))
    srv = cfg.get("mcpServers", {}).get("kjptai")
    if not srv:
        sys.exit("ERROR: mcp.json 中未找到 mcpServers.kjptai")
    return srv["url"], dict(srv.get("headers", {}))


def post(url, headers, body, session_id=None):
    h = dict(headers)
    if session_id:
        h["Mcp-Session-Id"] = session_id
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=h, method="POST")
    resp = urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=60)
    sid = resp.headers.get("Mcp-Session-Id")
    raw = resp.read().decode("utf-8")
    return sid, raw


def parse_sse(raw):
    last = None
    for line in raw.split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            try:
                last = json.loads(line[5:].strip())
            except Exception:
                pass
    if last is not None:
        return last
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}


def find_fields(obj, keys, path=""):
    """递归查找指定 key（不区分大小写包含匹配）的所有值"""
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if any(t in k.lower() for t in keys):
                hits.append((p, v))
            hits.extend(find_fields(v, keys, p))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(find_fields(v, keys, f"{path}[{i}]"))
    return hits


def extract_summary(resp):
    """取 content[0].text（markdown 摘要），无则取结构化内容 json"""
    try:
        for c in resp["result"]["content"]:
            if c.get("type") == "text" and c.get("text"):
                return c["text"]
        return json.dumps(resp["result"].get("structuredContent", {}), ensure_ascii=False)[:2000]
    except Exception:
        return json.dumps(resp, ensure_ascii=False)[:2000]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", required=True, help="MCP 工具名，如 create_story")
    ap.add_argument("--args", required=True, help="prepare 参数 JSON 字符串（不带 confirmed）")
    a = ap.parse_args()

    args = json.loads(a.args)
    url, headers = load_server()

    # initialize
    sid, raw = post(url, headers, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "kjptai-prepare", "version": "1.0"}}})
    post(url, headers, {"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)

    # tools/call prepare（不带 confirmed）
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": a.tool, "arguments": args}}
    sid2, raw2 = post(url, headers, call, sid)
    resp = parse_sse(raw2)
    if sid2:
        sid = sid2

    # 提取令牌字段
    token = update = None
    for p, v in find_fields(resp, ["confirmationtoken"]):
        token = v
        break
    for p, v in find_fields(resp, ["updatetime", "expectedupdatetime"]):
        update = v
        break
    if not token:
        print("== ERROR: 未提取到 confirmationToken ==", file=sys.stderr)
        print(json.dumps(resp, ensure_ascii=False, indent=2)[:3000], file=sys.stderr)
        sys.exit(1)

    summary = extract_summary(resp)
    request_id = str(uuid.uuid4())
    out = {"tool": a.tool, "confirmationToken": token, "expectedUpdateTime": update,
           "sessionId": sid, "requestId": request_id, "args": args}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("== 确认摘要 ==")
    print(summary)
    print("\n== 提交参数（已保存到 %s）==" % OUT)
    print("  confirmationToken    =", token)
    print("  expectedUpdateTime   =", update)
    print("  sessionId            =", sid)
    print("  requestId            =", request_id)


if __name__ == "__main__":
    main()
