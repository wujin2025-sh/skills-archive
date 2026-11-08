#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gtht-story-split 标准提交脚本：R26xxxxxxx Story 串行提交（submit1 → re-prepare2 → submit2 → ...）

v1（2026-11-04 R2610270069 三条 Story 一次全绿实证落地）：
- 输入：prepare 产物 /tmp/kjptai_story_{key}_prepare.json（由 prepare 脚本批量生成，
  每个含 args / label / confirmationToken / expectedUpdateTime / requestId /
  serverSubmitArgs / sessionId）
- 自动扫描全部 prepare 产物按文件名排序提交：首条直接用缓存令牌；
  后续条因需求 updateTime 前移，必须同参数 re-prepare 取「服务端新生成」令牌
  三件套再提交（仅 confirmationToken 相同 ≠ 已 re-prepare）
- 提交 values 双层回传（2026-11-04 实证模板，防 `Confirmed values changed`）：
  base = {**args, **submitValues} 且 base["values"] = submitValues
  （submitValues = 本次 prepare 返回的 submitArguments.values 规范化全集，
  不自行增删/改类型——服务端规范化结果因需求而异，一律以本次全集为准）
- 用法：python3 scripts/submit_stories.py [--dry-run]
"""
import json
import glob
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "../../gtht-accept-review/scripts"))
from kjptai_prepare import (load_server, post, parse_sse, find_fields, _is_session_error,
                            initialize_session, extract_summary)

TOOL = "create_story"
GLOB = "/tmp/kjptai_story_*_prepare.json"


def discover():
    files = sorted(glob.glob(GLOB))
    if not files:
        print(f"未找到 prepare 产物：{GLOB}\n请先运行 prepare 脚本生成 /tmp/kjptai_story_*_prepare.json")
        sys.exit(1)
    out = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            p = json.load(fh)
        out.append((os.path.basename(f), p))
    return out


def do_prepare(url, headers, args):
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": TOOL, "arguments": args}}
    sid, raw = post(url, headers, call, None)
    resp = parse_sse(raw)
    if _is_session_error(resp):
        sid = initialize_session(url, headers)
        sid, raw = post(url, headers, call, sid)
        resp = parse_sse(raw)
    token = update = None
    for _p, v in find_fields(resp, ["confirmationtoken"]):
        token = v
        break
    for _p, v in find_fields(resp, ["updatetime", "expectedupdatetime"]):
        update = v
        break
    submit_args = None
    for _p, v in find_fields(resp, ["submitarguments"]):
        if isinstance(v, dict) and v.get("requestId"):
            submit_args = v
            break
    return {"token": token, "update": update, "rid": (submit_args or {}).get("requestId"),
            "submit_args": submit_args, "sid": sid, "resp": resp}


def do_submit(url, headers, prep, args):
    v = (prep.get("submit_args") or {}).get("values")
    base = dict(args)
    if isinstance(v, dict):
        base = {**base, **v}
        base["values"] = v  # 嵌套 values 以服务端规范化全集为准
    if "demandId" not in base:
        base["demandId"] = args.get("demandId")
    call = {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": TOOL, "arguments": {**base, "confirmed": True,
                "confirmationToken": prep["token"], "expectedUpdateTime": prep["update"],
                "requestId": prep["rid"], "_meta": {"sessionId": prep["sid"]}}}}
    sid, raw = post(url, headers, call, prep.get("sid"))
    return parse_sse(raw)


def check_ok(resp):
    err = ""
    if isinstance(resp, dict) and resp.get("error"):
        err = json.dumps(resp["error"], ensure_ascii=False)[:2000]
    if not err:
        r = resp.get("result", {})
        if isinstance(r, dict) and r.get("isError"):
            st = json.dumps(r, ensure_ascii=False)[:3000]
            if "created" not in st.lower():
                err = st
    return err, extract_summary(resp)


def main():
    dry = "--dry-run" in sys.argv
    items = discover()
    url, headers = load_server()
    results = {}
    print(f"发现 {len(items)} 份 prepare 产物，串行提交（submit1 → re-prepareN → submitN ...）")
    for i, (fname, p) in enumerate(items):
        label = p.get("label", fname)
        args = p["args"]
        if i == 0:
            prep = {"token": p.get("confirmationToken"), "update": p.get("expectedUpdateTime"),
                    "rid": p.get("requestId"), "submit_args": p.get("serverSubmitArgs"),
                    "sid": p.get("sessionId")}
            print(f"--- [{i+1}/{len(items)}] {fname} {label}：用 prepare 缓存令牌提交 ---")
        else:
            print(f"--- [{i+1}/{len(items)}] {fname} {label}：re-prepare（updateTime 已前移）---")
            prep = do_prepare(url, headers, args)
            if not prep["token"]:
                print(f"  ✗ re-prepare 未拿到令牌，停止。")
                print(json.dumps(prep["resp"], ensure_ascii=False)[:2000])
                results[fname] = {"label": label, "ok": False, "err": "re-prepare 无令牌"}
                break
        if dry:
            print(f"  [dry-run] 跳过实际提交")
            results[fname] = {"label": label, "ok": None, "err": None, "msg": "dry-run"}
            continue
        resp = do_submit(url, headers, prep, args)
        err, msg = check_ok(resp)
        results[fname] = {"label": label, "ok": not err, "err": err, "msg": msg[:1500]}
        if err:
            print(f"  ✗ FAILED: {err}")
            print(f"    摘要: {msg[:500]}")
        else:
            print(f"  ✓ SUCCESS: {msg[:700]}")
        time.sleep(1)

    print("=" * 70)
    if dry:
        print("DRY-RUN 完成（未实际提交）")
    else:
        ok = all(r.get("ok") for r in results.values())
        print("ALL SUBMITTED:", "SUCCESS ✓" if ok else "PARTIAL/FAILED ✗")
        for fname, r in results.items():
            print(f"  {fname}: {r['label']} -> {'OK' if r.get('ok') else 'FAILED'}")
    out = "/tmp/kjptai_story_submit_result.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    print(f"结果已存 {out}")


if __name__ == "__main__":
    main()
