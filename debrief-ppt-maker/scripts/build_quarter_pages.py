# -*- coding: utf-8 -*-
"""【一键入口】按季度生成 02 模块双页 PPT：本季度需求指标看板 + 版本集成发布情况。

    python build_quarter_pages.py --quarter 2026Q3

默认：用本地《各系统发版汇总.xlsx》→ 生成两页 SVG/HTML/内页片段 →
      幂等落入述职主 HTML（P7/P8 + 目录 02 模块 + 页码）→ 重导 PDF。

常用开关：
  --refresh      重新登录全连接文档中心下载最新 Excel（默认复用本地文件）
  --probe        额外输出实时宽表口径探测 JSON（只复核，不覆盖基线）
  --no-insert    只生成两页图表产物，不改主 HTML
  --no-pdf       不重导 PDF
  --quarter 2026Q4   换季度；需先在该季度配置的 kpi 段补齐基线并置 ready=true

铁律：需求指标基线来自效能度量看板季度截图 + 用户拍板值，脚本不自动抓取、不估算；
      版本发布数据全量来自在线文档，可 --refresh 自动更新。
"""
import os
import sys
import json
import argparse
import datetime
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(SCRIPT_DIR, "quarter_config.json")
sys.path.insert(0, SCRIPT_DIR)
from gen_kpi_dashboard_q import quarter_meta, load_config  # noqa: E402

PY = sys.executable


def run(script, *args, **kw):
    cmd = [PY, os.path.join(SCRIPT_DIR, script)] + [str(x) for x in args]
    print("\n>>>", " ".join(cmd[1:]))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout:
        print(r.stdout.rstrip())
    if r.returncode != 0:
        print(r.stderr.rstrip(), file=sys.stderr)
        if not kw.get("soft"):
            raise RuntimeError("%s 执行失败（exit=%d）" % (script, r.returncode))
        print("[warn] %s 失败，但不阻断主流程" % script)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarter", required=True, help="YYYYQn，如 2026Q3")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--refresh", action="store_true", help="重新下载在线《各系统发版汇总》")
    ap.add_argument("--probe", action="store_true", help="输出实时宽表口径探测（仅复核）")
    ap.add_argument("--no-insert", action="store_true")
    ap.add_argument("--no-pdf", action="store_true")
    args = ap.parse_args()

    try:
        meta = quarter_meta(args.quarter)
        cfg, k = load_config(args.config, meta["quarter"])
    except (ValueError, KeyError) as e:
        print("❌ 季度配置校验失败：%s" % e, file=sys.stderr)
        return 2
    paths, doc = cfg["paths"], cfg["release_doc"]
    out, tag = paths["out_dir"], meta["tag"]
    os.makedirs(out, exist_ok=True)
    today = datetime.date.today().isoformat()
    ongoing = today < meta["end"]

    print("=" * 78)
    print("02 模块双页生成 | %s（%s ~ %s，%s）| 月份 %s | tag %s"
          % (meta["quarter"], meta["start"], meta["end"],
             "进行中" if ongoing else "已完结", meta["months"], tag))
    print("需求指标基线：受理 %s / 版本排期 %s / %s 天 / %s（来自季度配置，不自动抓取）"
          % (k["accept_total"], k["release_total"], k["e2e_days"], k["flow_eff"]))
    print("=" * 78)

    # 0) 可选：在线数据源刷新 / 口径探测
    if args.refresh:
        run("fetch_release_workbook.py", "--config", args.config, "--out", paths["xlsx"])
    if args.probe:
        run("probe_quarter_metrics.py", "--quarter", meta["quarter"],
            "--config", args.config, "--out", out, soft=True)

    if not os.path.exists(paths["xlsx"]):
        raise FileNotFoundError("缺少 %s；请先加 --refresh 下载" % paths["xlsx"])

    # 1) 需求指标看板（S7）
    kpi_args = ["--quarter", meta["quarter"], "--config", args.config, "--out", out]
    if ongoing:
        kpi_args.append("--ongoing")
    run("gen_kpi_dashboard_q.py", *kpi_args)

    # 2) 版本集成发布（S8）——先留旧快照，用于提示在线数据源被维护者改动
    snap_path = os.path.join(out, "release_stats_%s.json" % tag)
    before = json.load(open(snap_path, encoding="utf-8")) if os.path.exists(snap_path) else None
    rel_args = ["--xlsx", paths["xlsx"], "--quarter", meta["quarter"],
                "--months", ",".join(str(m) for m in meta["months"]),
                "--owner", doc["owner"], "--out", out,
                "--tag", tag, "--downloaded", today]
    if ongoing:
        rel_args.append("--ongoing")
    run("gen_release_dashboard.py", *rel_args)
    after = json.load(open(snap_path, encoding="utf-8")) if os.path.exists(snap_path) else None
    if before and after:
        changes = ["%s: %s → %s" % (key, before.get(key), after.get(key))
                   for key in ("total", "times", "systems", "by_system", "by_month",
                               "registered", "problems", "all_versions")
                   if before.get(key) != after.get(key)]
        if changes:
            print("\n[⚠ 在线数据源变化] 与上版快照相比：")
            for c in changes:
                print("   ", c)
            print("    → 目录文案与图表已按最新数据重算；如属维护者改名/补录，请在汇报说明中带一句。\n")
        else:
            print("[OK] 在线数据源与上版快照一致")

    # 3) 双页落版 + 目录/页码重组
    if not args.no_insert:
        run("insert_quarter_pages.py", "--quarter", meta["quarter"],
            "--config", args.config, "--main", paths["main_html"], "--out", out)

        # 4) 重导 PDF
        if not args.no_pdf:
            run("convert_html.py", paths["main_html"])

    print("\n" + "=" * 78)
    print("完成。产物目录：", out)
    for name in ("本季度需求指标看板_%s.svg" % tag,
                 "本季度需求指标看板_%s.html" % tag,
                 "版本集成发布情况_%s.svg" % tag,
                 "版本集成发布情况_%s.html" % tag,
                 "kpi_slide_inner_%s.html" % tag,
                 "release_slide_inner_%s.html" % tag):
        p = os.path.join(out, name)
        print("  %s %s" % ("OK " if os.path.exists(p) else "MISS", name))
    if not args.no_insert:
        print("主 HTML：", paths["main_html"])
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
