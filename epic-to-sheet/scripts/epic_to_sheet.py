#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epic_to_sheet.py — 史诗下需求按既有格式追加到腾讯文档「需求跟踪」表
================================================================
全链路自动化：史诗/需求号 → kjptai 查详情 → 读表格(比对) → 新增追加 / 已有差异增量更新 → D列超链接 → 回读验证。
行为：史诗下新增需求 → 追加新行；已有需求内容变化 → 仅增量更新「脚本管控列」差异列（人工维护列永不覆盖）；内容无变化 → 零写入。

用法:
    python3 epic_to_sheet.py --epic PG202204-0313 [--file F --sheet S] [--dry-run] [--force]
    python3 epic_to_sheet.py --demands R2609090038,R2609090040 [--file F --sheet S] [--dry-run] [--force]

参数:
    --epic      史诗编号（自动经 epic-statistics 的 epic_stats.py 取需求清单）
    --demands   逗号分隔需求号（快速路径，跳过史诗取数）
    --file      腾讯文档 file_id，默认 DS2hBcE5hVWpJdXJs
    --sheet     sheet_id（tab），默认 BB08J2（需求跟踪）
    --dry-run   只分析+比对，不写入
    --force     已存在需求也强制同步全部管控列（默认仅增量更新差异列）

依赖:
    td_mcp.py（腾讯文档 MCP，走系统代理直连 docs.qq.com）
    kjptai_mcp.py（kjptai MCP，内网 trust_env=False 直连）
    epic_stats.py（仅 --epic 时需要，位于 epic-statistics 技能 scripts/ 下）
"""
import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys
from html.parser import HTMLParser

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import td_mcp                 # noqa: E402
from kjptai_mcp import KjptaiClient, query_requirement_detail  # noqa: E402

DEFAULT_FILE = "DS2hBcE5hVWpJdXJs"
DEFAULT_SHEET = "BB08J2"
DEMAND_LINK = "https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId={}&templateId=8888&flag=1"
EPIC_STATS_SCRIPT = os.path.expanduser("~/.chat/skills/epic-statistics/scripts/epic_stats.py")

# ---------------------------------------------------------------- HTML 转纯文本
class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self._skip += 1
        if tag in ("p", "li", "br", "tr", "h1", "h2", "h3", "h4", "div"):
            self.parts.append("\n")
        if tag == "strong":
            self.parts.append("**")
        if tag in ("td", "th"):
            self.parts.append(" | ")
    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self._skip = max(0, self._skip - 1)
        if tag == "strong":
            self.parts.append("**")
    def handle_data(self, data):
        if self._skip == 0:
            self.parts.append(data)

def html_to_text(html):
    if not html:
        return ""
    p = _TextExtractor()
    try:
        p.feed(html)
    except Exception:
        pass
    text = "".join(p.parts)
    text = re.sub(r"[ \t\u3000]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = re.sub(r" ?\n ?", "\n", text)
    return text.strip()

# ---------------------------------------------------------------- markdown 解析
def parse_md_table(md):
    """将 markdown 中 `| 字段 | 内容 |` 表格解析为 dict。"""
    fields = {}
    for m in re.finditer(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", md, re.M):
        k = m.group(1).strip()
        v = m.group(2).strip()
        if k and v != "---" and "字段" not in k:
            fields[k] = v
    return fields

def extract_desc(md):
    """提取 ### 描述 段（HTML 富文本），转为带「一、需求背景/二、需求内容」的纯文本。"""
    m = re.search(r"### 描述\s*\n(.*?)(?=\n### |\Z)", md, re.S)
    if not m:
        return ""
    html = m.group(1)
    text = html_to_text(html)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text

def extract_review(md):
    """提取评审纪要段：返回 (评审状态, 纪要纯文本)。"""
    m = re.search(r"### 需求评审会议纪要\s*\n(.*?)(?=\n### |\Z)", md, re.S)
    if not m:
        return None, ""
    chunk = m.group(1)
    status = ""
    mm = re.search(r"\|\s*评审通过\s*\|", chunk)
    if mm:
        status = "通过"
    else:
        mm = re.search(r"评审结果\s*\|?\s*([^\|\n]+)", chunk)
        if mm:
            status = mm.group(1).strip()
    text = html_to_text(chunk)
    return (status or None), text

def pick(li, *keys, strip_prefix=True):
    """从需求链接/文本中提取需求号：R26xxxxxxx。"""
    pass

def link_to_rid(link):
    m = re.search(r"demandId=([A-Za-z0-9]+)", link or "")
    return m.group(1).upper() if m else ""

# ---------------------------------------------------------------- 需求→行数据
def build_row(detail, md):
    """由需求详情构造「需求跟踪」表的一行（列名→值，列名与表头自动对齐）。"""
    flds = parse_md_table(md)
    create_time = detail.get("createTime") or flds.get("创建时间", "")
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", create_time or "")
    propose_date = f"{m.group(1)}/{int(m.group(2))}/{int(m.group(3))}" if m else ""

    priority = detail.get("priority") or flds.get("优先级", "")
    # 表内既有 QFII 行统一用「一般紧急」；P4→一般紧急。其余 P 值保留原样待人工确认。
    priority_fmt = "一般紧急" if priority == "P4" else (priority or "")

    title = detail.get("summary") or flds.get("标题", "")
    demand_id = detail.get("demandId") or flds.get("需求编号", "")

    desc = extract_desc(md) or (flds.get("描述") or "")
    desc = desc.replace("**", "")

    review_status, review_text = extract_review(md)
    review_text = (review_text or "").replace("**", "").strip()[:4000]

    # 评审纪要推断：改造范围 / 联测涉及系统 / 依赖 / 预计上线
    scope, depends, online = "", "", ""
    if review_text:
        scope_m = re.search(r"改造范围[：:]\s*([^\n]*)", review_text)
        if scope_m:
            scope = scope_m.group(1).strip()
        dep_m = re.search(r"(?:联测涉及系统|业务参数|需求补充说明|关联需求)[：:]\s*([^\n]*)", review_text)
        if dep_m:
            depends = dep_m.group(1).strip()
        online_m = re.search(r"预计上线日期[：:]\s*([^\n]*)", review_text)
        if online_m:
            online = online_m.group(1).strip()

    plan_date = review_text and online
    m2 = re.search(r"(\d{4})年(\d{1,2})月", plan_date or "")
    plan = f"{m2.group(1)}{int(m2.group(2)):02d}01" if m2 else ""

    return {
        "提出日期": propose_date,
        "优先级": priority_fmt,
        "史诗": detail.get("epicName") or flds.get("史诗名称", ""),
        "需求链接": DEMAND_LINK.format(demand_id),
        "需求名称": title,
        "需求描述": desc,
        "关联系统": scope,
        "对应负责人": "",
        "是否有依赖关系": depends,
        "计划排期": plan,
        "评审状态": review_status or "",
        "个微是否需要改": "",
        "大集中大远期包": "",
        "大集中小远期包": "",
        "灰度升级是否影响": detail.get("grayUpgradeDisplay") or flds.get("是否影响灰度升级", ""),
        "大集中生产包": "",
        "大集中升级状态": "",
        "大集中升级日期": "",
        "是否已上线": "",
    }

# ---------------------------------------------------------------- 表格读写
def td_get_full(file_id, sheet_id):
    info = td_mcp.call_tool("sheet.get_sheet_info", {"file_id": file_id, "sheet_id": sheet_id})
    sc = info.get("structuredContent", {})
    row_count = int(sc.get("rowCount", 0) or sc.get("totalRowCount", 0) or 300)
    max_row = min(row_count, 500)
    out = td_mcp.call_tool("sheet.get_cell_data", {
        "file_id": file_id, "sheet_id": sheet_id,
        "start_row": 0, "start_col": 0, "end_row": max_row - 1, "end_col": 30,
        "return_csv": True,
    })
    csv_data = out.get("structuredContent", {}).get("csv_data", "")
    rows = list(csv.reader(io.StringIO(csv_data)))
    header = [h.strip() for h in (rows[0] if rows else [])]
    last = -1
    for i in range(len(rows) - 1, 0, -1):
        if any(c.strip() for c in rows[i]):
            last = i
            break
    return header, rows, last

def write_rows(file_id, sheet_id, start_row, rows_data):
    """rows_data: list[dict 列名→值]，按表头对齐列索引批量写入。"""
    _, rows, _ = td_get_full(file_id, sheet_id)
    header_map = {name: idx for idx, name in enumerate(rows[0])}
    values = []
    for r_i, row_dict in enumerate(rows_data):
        for col_name, val in row_dict.items():
            if col_name not in header_map or val is None or val == "":
                continue
            values.append({"row": start_row + r_i, "col": header_map[col_name],
                           "value_type": "STRING", "string_value": str(val)})
    if not values:
        return
    td_mcp.call_tool("sheet.set_range_value", {"file_id": file_id, "sheet_id": sheet_id, "values": values})

def set_links(file_id, sheet_id, start_row, rows_data):
    for r_i, row_dict in enumerate(rows_data):
        link = row_dict.get("需求链接", "")
        if not link:
            continue
        td_mcp.call_tool("sheet.set_link", {
            "file_id": file_id, "sheet_id": sheet_id,
            "row": start_row + r_i, "col": 3, "url": link, "display_text": link})

# ---------------------------------------------------------------- 差异比对与增量更新
# 脚本自动维护的列；其余列（对应负责人/个微是否需要改/大集中系列/是否已上线）视为人工维护列，永不覆盖
CTRL_COLS = ["提出日期", "优先级", "史诗", "需求名称", "需求描述", "关联系统",
             "是否有依赖关系", "计划排期", "评审状态", "灰度升级是否影响"]

def norm_cell(v):
    """规范化单元格文本用于比对：忽略所有空白（\r\n/空格/全角空格）差异。"""
    return re.sub(r"\s+", "", str(v or ""))

def build_index(rows):
    """需求号 → 行索引（优先 D 列需求链接，其次整行扫描 R 编号）。"""
    idx = {}
    for i, r in enumerate(rows):
        if i == 0:
            continue
        rid = link_to_rid(r[3]) if len(r) > 3 else ""
        if not rid:
            m = re.search(r"(R\d{8,})", " ".join(r), re.I)
            if m:
                rid = m.group(1).upper()
        if rid and rid not in idx:
            idx[rid] = i
    return idx

def diff_row(expect, row_cells, header_map):
    """比对期望行与表格现有行（仅脚本管控列），返回差异列 dict{列名: 新值}。"""
    diffs = {}
    for col in CTRL_COLS:
        ci = header_map.get(col)
        if ci is None:
            continue
        new_v = str(expect.get(col, "") or "")
        old_v = row_cells[ci] if ci < len(row_cells) else ""
        if norm_cell(old_v) != norm_cell(new_v):
            diffs[col] = new_v
    return diffs

def patch_rows(file_id, sheet_id, patches, header_map):
    """按行号增量覆盖指定列（仅写非空值，避免误清空人工维护内容）。
    patches: list[(row_index, rid, {列名: 新值})]"""
    values = []
    for r_idx, _rid, col_map in patches:
        for col_name, val in col_map.items():
            ci = header_map.get(col_name)
            if ci is None or val is None or str(val) == "":
                continue
            values.append({"row": r_idx, "col": ci,
                           "value_type": "STRING", "string_value": str(val)})
    if values:
        td_mcp.call_tool("sheet.set_range_value",
                         {"file_id": file_id, "sheet_id": sheet_id, "values": values})

def fetch_epic_demands(epic, fresh=False):
    """史诗→需求号清单：调用 epic-statistics 的 epic_stats.py --json（--fresh 强制重导出忽略缓存）。"""
    if not os.path.exists(EPIC_STATS_SCRIPT):
        raise RuntimeError(f"未找到 {EPIC_STATS_SCRIPT}\n请安装 epic-statistics/wide-table-query 技能，或改用 --demands 直接传需求号")
    cmd = [sys.executable, EPIC_STATS_SCRIPT, epic, "--json"]
    if fresh:
        cmd.append("--fresh")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"epic_stats.py 失败: {r.stderr[-800:]}")
    data = json.loads(r.stdout)
    ids = []
    details = data.get("需求明细", []) if isinstance(data, dict) else (data or [])
    for row in details if isinstance(details, list) else []:
        rid = (row.get("需求编号") if isinstance(row, dict) else None) or \
              (row.get("demandId") if isinstance(row, dict) else None) or \
              link_to_rid(str(row.get("需求链接", "")) if isinstance(row, dict) else "")
        if rid:
            ids.append(str(rid).upper())
    return sorted(set(ids))

# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epic")
    ap.add_argument("--demands")
    ap.add_argument("--file", default=DEFAULT_FILE)
    ap.add_argument("--sheet", default=DEFAULT_SHEET)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--fresh", action="store_true",
                    help="--epic 时强制 epic_stats 重导出（忽略缓存，史诗刚新增需求时用）")
    args = ap.parse_args()

    if args.epic:
        demand_ids = fetch_epic_demands(args.epic, args.fresh)
        print(f"[1] 史诗 {args.epic} 下需求 {len(demand_ids)} 条: {demand_ids}")
    elif args.demands:
        demand_ids = [d.strip().upper() for d in args.demands.split(",") if d.strip()]
        print(f"[1] 直接指定需求 {len(demand_ids)} 条: {demand_ids}")
    else:
        ap.error("必须提供 --epic 或 --demands")

    if not demand_ids:
        print("无需求可处理，退出")
        return

    print("[2] 查询需求详情(kjptai) ...")
    client = KjptaiClient()
    new_rows = []
    for rid in demand_ids:
        d = query_requirement_detail(client, rid)
        if d.get("error"):
            print(f"  !! {rid} 查询失败: {d['error']}")
            continue
        data = d.get("data") or {}
        detail = data.get("detail") or {}
        md = data.get("markdown") or ""
        row = build_row(detail, md)
        row["需求编号_内部"] = rid
        new_rows.append(row)
        print(f"  - {rid} {row['需求名称'][:40]} PKG优先级={detail.get('priority')}")

    print(f"[3] 读表格比对（file={args.file} sheet={args.sheet}）...")
    header, rows, last = td_get_full(args.file, args.sheet)
    header_map = {name: idx for idx, name in enumerate(rows[0])}
    print(f"  表头 {len(header)} 列; 最后数据行(0-based)={last}")

    row_of = build_index(rows)          # 需求号 → 行索引
    todo, updates, same = [], [], []    # todo=新增; updates=(行,rid,差异列); same=无变化
    expect_by_rid = {r["需求编号_内部"]: r for r in new_rows}
    for row in new_rows:
        rid = row["需求编号_内部"]
        r_idx = row_of.get(rid)
        if r_idx is None:
            todo.append(row)
            continue
        diffs = diff_row(row, rows[r_idx], header_map)
        if args.force:
            updates.append((r_idx, rid, {c: row[c] for c in CTRL_COLS}))
            print(f"  --force 强制同步 {rid}（行{r_idx}）全部管控列")
        elif diffs:
            updates.append((r_idx, rid, diffs))
        else:
            same.append(rid)

    n_new, n_upd = len(todo), len(updates)
    print(f"[4] 新增 {n_new} 条 | 更新 {n_upd} 条 | 无变化跳过 {len(same)} 条")
    start_row = last + 1
    for i, r in enumerate(todo):
        print(f"  + 行{start_row + i}: {r['需求名称'][:44]} | 排期={r['计划排期']} | 评审={r['评审状态']} | 关联系统={r['关联系统'][:30]}")
    for r_idx, rid, col_map in updates:
        detail = ", ".join(f"{c}→{str(v)[:24]}" for c, v in col_map.items())
        print(f"  ~ 行{r_idx} {rid}: {detail or '（无值列）'}")

    if not todo and not updates:
        print("全部已存在且内容无变化，无需写入。")
        return
    if args.dry_run:
        print("[5] --dry-run，未写入。")
        return

    # 1) 增量更新已有需求（仅脚本管控列差异）
    if updates:
        patch_rows(args.file, args.sheet, updates, header_map)
        # D 列超链接幂等补全（已有行如原链接缺失则补设）
        for r_idx, rid, _cm in updates:
            good = link_to_rid(rows[r_idx][3]) if r_idx < len(rows) and len(rows[r_idx]) > 3 else ""
            if not good:
                set_links(args.file, args.sheet, r_idx, [expect_by_rid[rid]])

    # 2) 追加新需求
    if todo:
        write_rows(args.file, args.sheet, start_row, todo)
        set_links(args.file, args.sheet, start_row, todo)

    # 3) 回读验证（更新行 + 新增行）
    v_ok = 0
    for r_idx, _rid, _cm in updates:
        out = td_mcp.call_tool("sheet.get_cell_data", {
            "file_id": args.file, "sheet_id": args.sheet,
            "start_row": r_idx, "start_col": 0, "end_row": r_idx, "end_col": 18,
            "return_csv": True})
        csv_data = out.get("structuredContent", {}).get("csv_data", "")
        vrows = list(csv.reader(io.StringIO(csv_data)))
        if vrows and any(c.strip() for c in vrows[0]):
            v_ok += 1
    if todo:
        out = td_mcp.call_tool("sheet.get_cell_data", {
            "file_id": args.file, "sheet_id": args.sheet,
            "start_row": start_row, "start_col": 0, "end_row": start_row + len(todo) - 1,
            "end_col": 18, "return_csv": True})
        csv_data = out.get("structuredContent", {}).get("csv_data", "")
        vrows = list(csv.reader(io.StringIO(csv_data)))
        v_ok += sum(1 for r in vrows if len(r) > 4 and r[4].strip())
    print(f"[5] 回读验证: 更新 {n_upd} 条 + 新增 {n_new} 行，验证有效 {v_ok} 处 ✅")

if __name__ == "__main__":
    main()
