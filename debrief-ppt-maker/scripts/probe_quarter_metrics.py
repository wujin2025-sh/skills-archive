# -*- coding: utf-8 -*-
"""季度需求指标「口径探测」：从科技平台实时宽表复算受理/版本排期数，输出对照 JSON。

⚠️ 只做复核，**绝不自动覆盖 quarter_config.json 的季度基线**。
   2026-11-11 实测：按本脚本口径 Q3 = 50、Q4 = 25，与 SKILL 校准基线 85 / 54 不一致，
   多种过滤变体均无法复现。基线以上午拍板值为准，差异待与用户确认取数脚本后再重算。

用法：
  python probe_quarter_metrics.py --quarter 2026Q3 [--out <目录>]
"""
import os
import re
import json
import argparse
import collections
import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(SCRIPT_DIR, "quarter_config.json")
SESSION = "/Volumes/Macintosh HD_Data/WorkBuddy/需求管理/.fintech_session.json"
SHEET_URL = ("https://fintech.gtht.com.cn/api/table-service/table/row/"
             "getSheetContent?sheetId=1597051509256884224")


def quarter_range(q):
    m = re.fullmatch(r"(\d{4})Q([1-4])", q.strip(), re.I)
    if not m:
        raise ValueError("季度格式应为 YYYYQn")
    y, n = int(m.group(1)), int(m.group(2))
    first, last = (n - 1) * 3 + 1, n * 3
    end_day = 31 if last in (1, 3, 7, 8, 10, 12) else 30
    return "%d-%02d-01" % (y, first), "%d-%02d-%02d" % (y, last, end_day)


def fetch_rows():
    import requests
    if not os.path.exists(SESSION):
        raise FileNotFoundError("缺少金融科技平台会话：" + SESSION)
    d = json.load(open(SESSION, encoding="utf-8"))
    cookies = {c["name"]: c["value"] for c in d["cookies"]}
    token = next((c["value"] for c in d["cookies"] if c["name"] == "GTJA_TOKEN"), None)
    h = {"User-Agent": "Mozilla/5.0",
         "Referer": "https://fintech.gtht.com.cn/kjpt/OnlineGrid?tableId=1597051499572236288",
         "accept": "application/json", "content-type": "application/json"}
    if token:
        h["token"] = token
    r = requests.get(SHEET_URL, cookies=cookies, headers=h, timeout=90)
    j = r.json()
    rows = (j.get("data") or {}).get("data") or []
    if not rows:
        raise RuntimeError("宽表返回空（HTTP %s, code=%s）" % (r.status_code, j.get("code")))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarter", required=True)
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--out", default=None)
    ap.add_argument("--owner", default="吴进")
    args = ap.parse_args()

    cfg = json.load(open(args.config, encoding="utf-8"))
    out = args.out or cfg["paths"]["out_dir"]
    os.makedirs(out, exist_ok=True)
    q = args.quarter.upper()
    lo, hi = quarter_range(q)
    rows = fetch_rows()

    mine = [r for r in rows if args.owner in str(r.get("demandReceiver") or "")]

    def in_q(r):
        d = str(r.get("storyPlanLineDate") or "")[:10]
        return bool(d) and lo <= d <= hi and not d.startswith("2099") and not d.endswith("12-31")

    sub = [r for r in mine if in_q(r)]
    ids = {r.get("demandId") for r in sub if r.get("demandId")}
    by_status = collections.Counter(str(r.get("demandStatus") or "(空)") for r in sub)
    by_version = collections.defaultdict(set)
    for r in sub:
        by_version[str(r.get("storyPlanLineName") or "(空)")].add(r.get("demandId"))

    # 时间类字段随平台改版可能改名：动态探测所有 date/time 字段并统计季度内月份分布
    allkeys = set().union(*[set(r.keys()) for r in rows[:500]])
    date_keys = [k for k in allkeys if any(t in k.lower() for t in ("time", "date"))]
    candidates = {}
    for k in date_keys:
        c = collections.Counter()
        for r in mine:                       # 受理月份基于「本人受理行」，非版本排期命中行
            d = str(r.get(k) or "")[:7]
            if re.match(r"^\d{4}-\d{2}$", d) and lo[:7] <= d <= hi[:7]:
                c[d] += 1
        if c:
            candidates[k] = dict(sorted(c.items()))
    # 只有字段名含 receiv/accept 才认作受理时间；宽表里其余多为计划/完成日期，
    # 拿它当受理月份会与效能看板口径冲突（铁律：不编数字、不误标口径）。
    preferred = [k for k in candidates
                 if any(t in k.lower() for t in ("receiv", "accept"))]
    chosen = preferred[0] if preferred else None
    by_month = collections.Counter(candidates.get(chosen, {}))
    recv_keys = date_keys
    month_warning = (None if chosen else
                     "宽表未找到受理时间字段，未输出受理月份分布；候选多为计划/完成日期，勿当作受理月份使用。")

    baseline = cfg.get("quarters", {}).get(q, {}).get("kpi", {})
    result = {
        "quarter": q, "range": [lo, hi], "owner": args.owner,
        "wide_table_rows": len(rows), "owner_rows": len(mine),
        "matched_story_rows": len(sub), "unique_demands": len(ids),
        "by_status": dict(by_status.most_common()),
        "by_version_top": sorted(((k, len(v)) for k, v in by_version.items()),
                                 key=lambda x: -x[1])[:12],
        "by_receive_month": dict(sorted(by_month.items())),
        "chosen_receive_field": chosen,
        "receive_month_warning": month_warning,
        "date_field_candidates": list(candidates),
        "time_date_fields": recv_keys,
        "config_baseline": {
            "accept_total": baseline.get("accept_total"),
            "release_total": baseline.get("release_total"),
            "ready": cfg.get("quarters", {}).get(q, {}).get("ready", False),
        },
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "WARNING": "本文件仅供口径复核，禁止据此自动改写 quarter_config.json 基线；"
                   "差异须与用户确认上午取数脚本字段/数据源后再处理。",
    }
    path = os.path.join(out, "probe_%s.json" % q)
    json.dump(result, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print("宽表 %d 行 | 本人受理 %d 行 | %s 命中 Story %d 行 / 去重需求 %d 项"
          % (len(rows), len(mine), q, len(sub), len(ids)))
    print("配置基线：受理 %s / 版本排期 %s　→ 差异供复核，不自动覆盖"
          % (result["config_baseline"]["accept_total"],
             result["config_baseline"]["release_total"]))
    print("状态分布：", result["by_status"])
    if chosen:
        print("受理月份：", result["by_receive_month"], "（采用字段 %s）" % chosen)
    else:
        print("受理月份：未输出 ——", month_warning)
        print("时间字段候选：", list(candidates))
    print("已写出：", path)


if __name__ == "__main__":
    main()
