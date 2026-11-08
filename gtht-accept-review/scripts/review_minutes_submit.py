#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
review_minutes_submit.py —— 补纪要「一键提交」合并脚本（gtht-accept-review 极速版）

背景（2026-11-05 R2610290057 实测性能优化）：原补纪要链路 = query_flow.py（分派判定）
→ md_to_review_html.py（HTML 生成）→（读脚本确认用法）→ kjptai_prepare.py --submit，
共 4 次 Agent 工具往返，墙钟耗时主要花在往返等待而非命令本身。本脚本把整条链路
合并进单个进程（复用 query_flow / parse_flow / md_to_review_html 的纯函数），
一次 run_command 完成，命令内耗时约 8-10s，Agent 往返从 4 次降为 1 次。

流程（单进程，无子进程嵌套除 prepare 落库）：
  1. flow 查询（复用 query_flow._call_flow 无状态直连）→ 提取 demand / coReceiver / statusName；
  2. 分派判定：共同受理人（coReceiver 含吴进）OU 状态=待拆分 → 允许补纪要；否则输出分派
     建议并退出（不提交，交给 gtht-accept-review 完整流程处理受理/评审）；
  3. MD 定位：--md 显式指定，否则扫描需求分析目录下同编号 MD 取最新（Front Matter updated
     或文件名日期最大者）；
  4. HTML 生成：复用 md_to_review_html.extract_review_lines + build_html（无需子进程）；
  5. 构造 add_requirement_review_minutes 参数并调用 kjptai_prepare.py --submit 落库
     （补纪要默认自动提交，符合技能 P0-1；--dry-run 只演练不提交）。

用法：
  python review_minutes_submit.py --demandId R26xxxxxxx [--md <需求MD路径>] [--title <会议主题>] [--dry-run]
  python review_minutes_submit.py --demandId R26xxxxxxx --dry-run   # 演练：打印分派与参数，不落库

退出码：0=提交成功（或 dry-run 演练通过）；1=未找到 MD / 无评审纪要 / flow 异常；
         2=分派判定非补纪要场景（不提交，提示按完整流程）
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from query_flow import _call_flow            # noqa: E402
from kjptai_prepare import load_server       # noqa: E402
from parse_flow import _unwrap, extract_data # noqa: E402
from md_to_review_html import extract_review_lines, build_html  # noqa: E402

DEMAND_DIR = os.environ.get(
    "GTHT_DEMAND_DIR",
    "/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析",
)
CURRENT_USER = "吴进"  # 共同受理人判定用（技能固定：吴进-125360）


def find_latest_md(demand_id):
    """扫描需求分析目录下同编号 MD，按 Front Matter updated / 文件名日期取最新。"""
    hits = sorted(glob.glob(os.path.join(DEMAND_DIR, f"*{demand_id}*.md")))
    if not hits:
        return None

    def _key(p):
        try:
            txt = Path(p).read_text(encoding="utf-8")
            m = re.search(r"^updated:\s*(\d{4}-\d{2}-\d{2})", txt, re.M)
            if m:
                return m.group(1)
        except Exception:
            pass
        m = re.search(r"(\d{8})", os.path.basename(p))
        if m:
            d = m.group(1)
            return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        return "0000-00-00"

    return max(hits, key=_key)


def extract_doc_title(md_text):
    """取第一个一级标题（# xxx）作为需求名称。"""
    m = re.search(r"^#\s+(.+?)\s*$", md_text, re.M)
    return m.group(1).strip() if m else None


def main():
    ap = argparse.ArgumentParser(description="补纪要一键提交（flow 判定 → MD → HTML → prepare+submit）")
    ap.add_argument("--demandId", required=True, help="需求编号，如 R26xxxxxxx")
    ap.add_argument("--md", help="评审纪要来源 MD 路径（默认自动定位需求分析目录最新同编号 MD）")
    ap.add_argument("--title", help="会议主题（默认：{需求名称}_{YYYYMMDD}）")
    ap.add_argument("--dry-run", action="store_true", help="只演练：打印分派判定与构造参数，不提交")
    a = ap.parse_args()

    t0 = time.time()
    url, headers = load_server()
    resp = _call_flow(url, headers, a.demandId)
    text = json.dumps(resp, ensure_ascii=False)
    data = extract_data(_unwrap(text))
    if data is None:
        print("== ERROR: flow 响应解析失败，无法判定状态 ==", file=sys.stderr)
        sys.exit(1)
    demand = (data.get("demand") or data.get("requirement") or {})
    status = demand.get("boardName") or (data.get("flow") or {}).get("statusName")
    co = demand.get("commonReceiver")
    co_str = ",".join(co) if isinstance(co, list) else (co or "")
    is_co = CURRENT_USER in co_str
    print(f"== 需求 {a.demandId}  [状态] {status}  [共同受理人] {co_str or '无'}")

    # 分派判定：共同受理人 或 状态=待拆分（已评审，补纪要兜底）才允许提交
    if not is_co and status not in ("待拆分",):
        print(f"== 分派判定：非共同受理人且状态「{status}」非待拆分 → 不走补纪要（exit 2）", file=sys.stderr)
        print("   请按 gtht-accept-review 完整流程处理（待受理→受理+评审；讨论中→仅评审）", file=sys.stderr)
        sys.exit(2)

    # 定位 MD
    md_path = a.md or find_latest_md(a.demandId)
    if not md_path or not os.path.isfile(md_path):
        print(f"== ERROR: 未找到需求分析 MD（{DEMAND_DIR}/*{a.demandId}*.md）", file=sys.stderr)
        sys.exit(1)
    md_text = Path(md_path).read_text(encoding="utf-8")
    lines = extract_review_lines(md_text)
    if lines is None:
        print("== ERROR: MD 中无「评审纪要」小节", file=sys.stderr)
        sys.exit(1)
    html_out = build_html(lines)
    if "预计上线日期" not in html_out:
        print("== ERROR: 评审纪要缺少「预计上线日期」行，禁止提交", file=sys.stderr)
        sys.exit(1)

    # 构造参数
    name = extract_doc_title(md_text) or a.demandId
    title = a.title or f"{name}_{time.strftime('%Y%m%d')}"
    args = {
        "demandId": a.demandId,
        "title": title,
        "reviewType": "评审通过",
        "summaryType": "2",
        "mettingSummary": html_out,
    }
    print(f"== 纪要来源 : {md_path}")
    print(f"== title    : {title}  |  reviewType=评审通过  |  summaryType=2")
    print(f"== 纪要字数 : {len(html_out)} 字符（含预计上线日期行）")

    if a.dry_run:
        print(f"\n== [DRY-RUN] 演练通过，未提交。耗时 {time.time() - t0:.1f}s ==")
        sys.exit(0)

    # 落库：调 kjptai_prepare.py --submit（args 列表透传，无 shell 转义问题）
    py = sys.executable
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kjptai_prepare.py")
    r = subprocess.run(
        [py, script, "--tool", "add_requirement_review_minutes",
         "--args", json.dumps(args, ensure_ascii=False), "--submit"],
        capture_output=True, text=True,
    )
    print(r.stdout)
    if r.stderr:
        print(r.stderr, file=sys.stderr)
    if r.returncode != 0 or "SUCCESS" not in r.stdout:
        print(f"== ERROR: 提交失败（rc={r.returncode}），请检查上方 prepare/submit 输出 ==", file=sys.stderr)
        sys.exit(1)
    print(f"== 补纪要提交成功，总耗时 {time.time() - t0:.1f}s ==")
    sys.exit(0)


if __name__ == "__main__":
    main()
