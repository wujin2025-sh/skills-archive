#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
query_flow.py —— query_requirement_flow 一键极速查询（gtht-accept-review 专用）

背景：执行写操作前必须查 flow 真实状态（状态感知幂等闸门）。旧做法是每次手写临时脚本、
易走代理超时（60s 挂起）。本脚本复用 kjptai_prepare.py 的「内置禁代理 + 无状态直连
（服务端 JWE 鉴权无需 initialize 握手，2026-11-01 实测）+ SSE 解析」基础设施，
一条命令完成查询，秒级返回。

用法：
  python query_flow.py --demandId R26xxxxxxx
      # 打印原始 MCP 响应（JSON，供调试）；退出码 0=成功
  python query_flow.py --demandId R26xxxxxxx --parse
      # 直接打印精炼摘要（等价 原始响应 | parse_flow.py，省 1 次管道往返）
  python query_flow.py --demandId R26xxxxxxx --out <文件>
      # 同时把原始响应 JSON 持久化到文件（供 parse_flow.py 复用/留痕）

退出码：0=查询+解析成功；1=响应含 error / isError / 未提取到 flow 内容
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kjptai_prepare import (load_server, post, initialize_session,
                            _is_session_error, parse_sse)

TOOL = "query_requirement_flow"


def _call_flow(url, headers, demand_id):
    """无状态直连 tools/call（服务端 JWE 鉴权无需握手，2026-11-01 实测）；session 报错才 initialize 兜底"""
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": TOOL, "arguments": {"demandId": demand_id}}}
    sid2, raw2 = post(url, headers, call, None)
    resp = parse_sse(raw2)
    if _is_session_error(resp):  # 兜底：重新 initialize 后带 session 重试
        sid = initialize_session(url, headers)
        sid2, raw2 = post(url, headers, call, sid)
        resp = parse_sse(raw2)
    return resp


def _check_error(resp):
    """有 error / isError 时打印并返回 True"""
    if isinstance(resp, dict) and resp.get("error"):
        print("== ERROR:", json.dumps(resp["error"], ensure_ascii=False)[:2000], file=sys.stderr)
        return True
    result = resp.get("result") if isinstance(resp, dict) else None
    if isinstance(result, dict) and result.get("isError"):
        print("== TOOL ERROR:", json.dumps(result, ensure_ascii=False)[:2000], file=sys.stderr)
        return True
    return False


def main():
    ap = argparse.ArgumentParser(description="query_requirement_flow 一键极速查询（内置禁代理 + 共享会话缓存）")
    ap.add_argument("--demandId", required=True, help="需求编号，如 R26xxxxxxx")
    ap.add_argument("--parse", action="store_true", help="直接打印精炼摘要（等价 原始响应 | parse_flow.py）")
    ap.add_argument("--out", help="可选：保存原始响应 JSON 到文件")
    a = ap.parse_args()

    url, headers = load_server()
    resp = _call_flow(url, headers, a.demandId)
    if _check_error(resp):
        sys.exit(1)

    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(resp, f, ensure_ascii=False, indent=2)
        print(f"== 原始响应已保存到 {a.out} ==", file=sys.stderr)

    if a.parse:
        from parse_flow import _unwrap, extract_data, summarize
        text = json.dumps(resp, ensure_ascii=False)
        inner = _unwrap(text)
        data = extract_data(inner)
        if data is None:
            print("== ERROR: 未提取到 flow 内容（解析失败）==", file=sys.stderr)
            print(text[:2000], file=sys.stderr)
            sys.exit(1)
        summarize(data)
    else:
        print(json.dumps(resp, ensure_ascii=False, indent=2)[:5000])
    sys.exit(0)


if __name__ == "__main__":
    main()
