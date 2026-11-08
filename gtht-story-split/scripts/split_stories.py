#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
split_stories.py —— gtht-story-split 一键拆分编排脚本（v1，2026-11-05 R2610290057 提速固化）

背景（性能优化）：原「工具通道」主路径 = Agent 逐次调用 MCP create_story prepare/confirmed，
每次 prepare 大响应（数百 KB fields+options）进对话上下文，且手工拼 values 易触发
「Confirmed values changed」失败重试。本脚本把整条链路合并进单个进程（复用
gtht-accept-review 新版 kjptai_prepare 无状态 JWE 直连 + submit_stories 串行提交），
一次 run_command 完成 flow 闸门+幂等 → 并行 prepare → 串行提交，大响应留在进程内。

流程（单进程）：
  1. flow 查询（复用 query_flow._call_flow）→ 需求状态闸门 + 存量 Story 幂等（按
     systemId / summary 精确匹配即 SKIP，防重复创建）；
  2. 对未 SKIP 的 Story 并行 prepare（线程池，直接 HTTP 直连生成令牌）→
     产物落盘 /tmp/kjptai_story_{key}_prepare.json（含 args/label/三件套/serverSubmitArgs）；
  3. --dry-run：仅展示确认摘要表（系统/开发/SIT/UAT/标签/灰度），不提交；
  4. --submit：按 submit_stories 逻辑串行提交（首条用缓存令牌，后续条自动 re-prepare
     取新三件套；values 双层回传以服务端 submitArguments.values 规范化全集为准，
     根治「Confirmed values changed」）；提交后 --verify 可选回查 flow。

用法：
  python split_stories.py --demandId R26xxxxxxx --stories '{JSON数组}' [--dry-run] [--verify]
    --stories 数组元素：{"key":"jzjy","label":"集中交易系统","summary":"...","args":{prepare 参数全集}}
    --dry-run：只 flow 闸门+幂等+并行 prepare，打印确认摘要表；产物落盘供后续 --submit 复用
    --verify ：提交完成后额外调用 query_requirement_flow 回查新 Story 数（重试场景省略）

退出码：0=成功（dry-run 演练通过 / 全部提交成功）；1=flow 异常或准备失败；2=全部幂等跳过（无需提交）
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "../../gtht-accept-review/scripts"))
from kjptai_prepare import load_server, extract_summary  # noqa: E402
from query_flow import _call_flow  # noqa: E402
from parse_flow import _unwrap, extract_data  # noqa: E402
from submit_stories import do_prepare, do_submit, check_ok  # noqa: E402

TOOL = "create_story"
PREP_DIR = "/tmp"


def flow_status(demand_id):
    """查 flow：返回 (status, existing_stories) 或 None（异常）。"""
    url, headers = load_server()
    resp = _call_flow(url, headers, demand_id)
    r = resp.get("result") if isinstance(resp, dict) else None
    if isinstance(r, dict) and (r.get("isError") or resp.get("error")):
        print("== ERROR: flow 查询失败 ==", file=sys.stderr)
        print(json.dumps(resp, ensure_ascii=False)[:2000], file=sys.stderr)
        return None, None
    text = json.dumps(resp, ensure_ascii=False)
    data = extract_data(_unwrap(text))
    if data is None:
        print("== ERROR: flow 解析失败 ==", file=sys.stderr)
        return None, None
    demand = data.get("demand") or data.get("requirement") or {}
    status = demand.get("boardName") or (data.get("flow") or {}).get("statusName")
    return status, data.get("stories") or []


def skip_check(stories, item):
    """幂等：flow 存量 Story 与待建项的 systemId 或 summary 精确匹配则跳过。"""
    args = item["args"]
    sid = str(args.get("systemId") or "").lower()
    summ = str(args.get("summary") or item.get("summary") or "").strip()
    for s in stories:
        if sid and str(s.get("systemId") or "").lower() == sid:
            return True, f"已存在同 systemId 的 Story（{s.get('storyNo') or s.get('summary')}）"
        sname = str(s.get("summary") or s.get("storyName") or "").strip()
        if summ and sname == summ:
            return True, f"已存在同名称 Story（{s.get('storyNo') or s.get('storyName')}）"
    return False, ""


def prepare_one(url, headers, item):
    """单条 prepare，产物落盘 /tmp/kjptai_story_{key}_prepare.json。"""
    key = item["key"]
    prep = do_prepare(url, headers, item["args"])
    if not prep["token"]:
        return {"key": key, "label": item["label"], "ok": False,
                "err": "prepare 未拿到令牌（NEEDS_INPUT/404 等）",
                "resp": json.dumps(prep["resp"], ensure_ascii=False)[:2000]}
    prod = {"args": item["args"], "label": item["label"],
            "confirmationToken": prep["token"], "expectedUpdateTime": prep["update"],
            "requestId": prep["rid"], "serverSubmitArgs": prep["submit_args"],
            "sessionId": prep["sid"]}
    with open(os.path.join(PREP_DIR, f"kjptai_story_{key}_prepare.json"), "w",
              encoding="utf-8") as f:
        json.dump(prod, f, ensure_ascii=False, indent=2)
    v = (prep.get("submit_args") or {}).get("values") or {}
    return {"key": key, "label": item["label"], "ok": True,
            "dev": v.get("devManagePersonId"), "sit": v.get("testManagePersonId"),
            "uat": v.get("uatUserId"), "sysLabel": v.get("systemLabelId"),
            "gray": v.get("isEffectGrayUpgrade"), "summary": prod["label"]}


def main():
    ap = argparse.ArgumentParser(description="gtht-story-split 一键拆分编排（flow 闸门 → 并行 prepare → 串行提交）")
    ap.add_argument("--demandId", required=True, help="需求编号，如 R26xxxxxxx")
    ap.add_argument("--stories", required=True, help="Story 清单 JSON 数组：[{key,label,args:{...}}, ...]")
    ap.add_argument("--dry-run", action="store_true", help="只 flow 闸门+幂等+并行 prepare，打印确认摘要，不提交")
    ap.add_argument("--verify", action="store_true", help="提交完成后回查 flow 打印新 Story 清单")
    a = ap.parse_args()

    t0 = time.time()
    try:
        items = json.loads(a.stories)
    except Exception as e:
        print(f"== ERROR: --stories JSON 解析失败：{e} ==", file=sys.stderr)
        sys.exit(1)

    status, existing = flow_status(a.demandId)
    if status is None:
        sys.exit(1)
    print(f"== 需求 {a.demandId}  [board] {status}  [存量 Story] {len(existing)}")

    todo, skipped = [], []
    for it in items:
        skip, why = skip_check(existing, it)
        if skip:
            skipped.append((it, why))
        else:
            todo.append(it)
    for it, why in skipped:
        print(f"  ⏭ SKIP {it['label']}：{why}")
    if not todo:
        print("== 全部幂等跳过，无需提交（exit 2）==\n耗时 %.1fs" % (time.time() - t0))
        sys.exit(2)

    url, headers = load_server()
    print(f"== 并行 prepare {len(todo)} 条 ...")
    with ThreadPoolExecutor(max_workers=min(len(todo), 4)) as ex:
        results = list(ex.map(lambda it: prepare_one(url, headers, it), todo))
    fails = [r for r in results if not r["ok"]]
    for r in fails:
        print(f"  ✗ PREPARE FAILED {r['label']}：{r['err']}\n    {r.get('resp', '')[:300]}")
    if fails:
        print("== 有 prepare 失败，请按 SKILL Step 4 补全参数（NEEDS_INPUT 按 options 回填）后重跑；未失败的产物已落盘 ==", file=sys.stderr)
        sys.exit(1)

    print("\n== 确认摘要 ==")
    print(f"{'系统':<16}{'开发':<14}{'SIT':<12}{'UAT':<12}{'标签':<5}{'灰度'}")
    for r in results:
        print(f"{r['label']:<16}{str(r['dev'] or ''):<14}{str(r['sit'] or ''):<12}"
              f"{str(r['uat'] or ''):<12}{str(r['sysLabel'] or ''):<5}{str(r['gray'] or '')}")
    print(f"（prepare 产物已存 /tmp/kjptai_story_*_prepare.json，后续 --submit 直接复用）")

    if a.dry_run:
        print(f"\n== [DRY-RUN] 演练通过，未提交。耗时 {time.time() - t0:.1f}s。确认后运行 --submit ==")
        sys.exit(0)

    # --submit：串行提交（首条缓存令牌，后续 re-prepare）
    from submit_stories import discover
    found = {os.path.basename(f).replace("kjptai_story_", "").replace("_prepare.json", ""): p
             for f, p in discover()}
    print(f"\n== 串行提交 {len(results)} 条（首条缓存令牌，后续 re-prepare）==")
    ok_all = True
    for i, r in enumerate(results):
        key = r["key"]
        prod = found.get(key)
        if prod is None:
            print(f"  ✗ {r['label']}：未找到 prepare 产物（/tmp/kjptai_story_{key}_prepare.json），跳过")
            ok_all = False
            continue
        prep = {"token": prod.get("confirmationToken"), "update": prod.get("expectedUpdateTime"),
                "rid": prod.get("requestId"), "submit_args": prod.get("serverSubmitArgs"),
                "sid": prod.get("sessionId")}
        if i > 0:
            nprep = do_prepare(url, headers, prod["args"])
            if not nprep["token"]:
                print(f"  ✗ {r['label']}：re-prepare 无令牌")
                ok_all = False
                continue
            prep = {"token": nprep["token"], "update": nprep["update"], "rid": nprep["rid"],
                    "submit_args": nprep["submit_args"], "sid": nprep["sid"]}
        resp = do_submit(url, headers, prep, prod["args"])
        err, msg = check_ok(resp)
        if err:
            ok_all = False
            print(f"  ✗ {r['label']} FAILED: {err}\n    摘要: {msg[:500]}")
        else:
            print(f"  ✓ {r['label']} SUCCESS: {msg[:300]}")
        time.sleep(1)

    print("=" * 70)
    print("ALL SUBMITTED:", "SUCCESS ✓" if ok_all else "FAILED ✗")
    if a.verify and ok_all:
        _, after = flow_status(a.demandId)
        print(f"== 回查：当前 Story 总数 {len(after)}（应=存量 {len(existing)} + 本次 {len(results)}）")
        for s in after:
            print(f"  - {s.get('storyNo')} | {s.get('summary')} | {s.get('systemName')}")
    print(f"总耗时 {time.time() - t0:.1f}s")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
