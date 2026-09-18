#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ndw_stat.py — 国泰海通科技平台 需求分析非开发工作量 (NDW / 价值量) 统计

按当前登录用户（默认吴进-125360）拉取已登记的非开发工作量记录（taskType=1 需求分析），
输出汇总统计：总条数 / 总价值量(人月) / 按状态 / 按月份 / 按系统 / 明细。

用法:
  python3 ndw_stat.py                 # 全量统计
  python3 ndw_stat.py --json          # 输出原始 JSON（含明细）
  python3 ndw_stat.py --assign 050599 # 指定经办人 userNo
"""
import sys
import os
import json
import argparse
from pathlib import Path
from collections import defaultdict

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import session as SESSION


def fetch_all_ndw(assign_user_no: str = None, page_size: int = 100, max_pages: int = 50) -> list:
    """全量拉取非开发工作量记录；优先不带 demandId，逐页翻取。"""
    records = []
    for page in range(1, max_pages + 1):
        body = {"current": page, "pageSize": page_size}
        if assign_user_no:
            body["assignUserNo"] = assign_user_no
        try:
            res = SESSION.api_post("/task-service/nonDevTask/getNonDevTaskList", body)
        except Exception as e:
            # 接口可能不接受 assignUserNo，回退不带
            if assign_user_no and page == 1:
                print(f"[warn] 带 assignUserNo 查询失败({e})，回退全量...", file=sys.stderr)
                body.pop("assignUserNo", None)
                res = SESSION.api_post("/task-service/nonDevTask/getNonDevTaskList", body)
            else:
                raise
        if not isinstance(res, dict):
            break
        page_records = res.get("records") or res.get("voList") or res.get("list") or []
        records.extend(page_records)
        total = res.get("total") or len(records)
        if len(records) >= total or not page_records:
            break
    return records


def summarize(records: list) -> dict:
    """按需求分析(taskType=1)口径汇总"""
    ndw = [r for r in records if str(r.get("taskType")) == "1"]
    total_value = sum(float(r.get("reapplicationTaskValue") or 0) for r in ndw)

    by_status = defaultdict(lambda: {"count": 0, "value": 0.0})
    by_month = defaultdict(lambda: {"count": 0, "value": 0.0})
    by_system = defaultdict(lambda: {"count": 0, "value": 0.0})
    by_demand = {}

    for r in ndw:
        val = float(r.get("reapplicationTaskValue") or 0)
        status_name = "已完成" if str(r.get("status")) == "2" else "未完成"
        by_status[status_name]["count"] += 1
        by_status[status_name]["value"] += val

        start = (r.get("startTime") or "")[:7]
        if start:
            by_month[start]["count"] += 1
            by_month[start]["value"] += val

        sys_name = r.get("systemName") or r.get("system") or "未知"
        by_system[sys_name]["count"] += 1
        by_system[sys_name]["value"] += val

        did = r.get("demandId") or ""
        if did:
            entry = by_demand.setdefault(did, {
                "demandId": did, "taskNo": r.get("taskNo", ""),
                "taskTitle": r.get("taskTitle", ""), "count": 0, "value": 0.0,
                "start": start, "end": (r.get("endTime") or "")[:10],
                "system": sys_name, "status": status_name,
                "evaluator": f"{r.get('evaluatorName','')}-{r.get('evaluatorStaffId','')}",
            })
            entry["count"] += 1
            entry["value"] += val

    return {
        "total_records": len(records),
        "ndw_count": len(ndw),
        "total_value": round(total_value, 2),
        "by_status": {k: {"count": v["count"], "value": round(v["value"], 2)} for k, v in by_status.items()},
        "by_month": {k: {"count": v["count"], "value": round(v["value"], 2)} for k, v in sorted(by_month.items())},
        "by_system": {k: {"count": v["count"], "value": round(v["value"], 2)} for k, v in sorted(by_system.items(), key=lambda x: -x[1]["value"])},
        "by_demand": list(by_demand.values()),
    }


def main():
    parser = argparse.ArgumentParser(description="NDW 价值量统计")
    parser.add_argument("--json", action="store_true", help="输出原始 JSON")
    parser.add_argument("--assign", default=None, help="经办人 userNo（默认不指定，按全量）")
    args = parser.parse_args()

    records = fetch_all_ndw(assign_user_no=args.assign)
    summary = summarize(records)

    if args.json:
        print(json.dumps({"summary": summary, "records": records}, ensure_ascii=False, indent=2))
        return

    print(f"=== NDW 统计 ===")
    print(f"记录总数: {summary['total_records']} | 需求分析(taskType=1): {summary['ndw_count']} 条 | 总价值量: {summary['total_value']} 人月")
    print(f"\n-- 按状态 --")
    for k, v in summary["by_status"].items():
        print(f"  {k}: {v['count']} 条, {v['value']} 人月")
    print(f"\n-- 按月份(开始) --")
    for k, v in summary["by_month"].items():
        print(f"  {k}: {v['count']} 条, {v['value']} 人月")
    print(f"\n-- 按系统 --")
    for k, v in summary["by_system"].items():
        print(f"  {k}: {v['count']} 条, {v['value']} 人月")
    print(f"\n-- 需求明细 --")
    for d in summary["by_demand"]:
        print(f"  {d['demandId']} [{d['status']}] {d['taskTitle'][:40]} | {d['value']}人月 x{d['count']} | {d['system']} | {d['start']}~{d['end']}")


if __name__ == "__main__":
    main()
