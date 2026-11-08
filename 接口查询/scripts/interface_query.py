# -*- coding: utf-8 -*-
"""
接口统一查询路由器 (Local-First)
==================================================
四级降级策略：
  L1   本地 SQLite 知识库  (.interface_store.db)   —— 毫秒级，覆盖 实时接口 + 文件接口 + 字段明细
  L2   本地 Markdown 规格文档 (*.md)               —— 补充 L1 未收录的接口规格
  L1.5 功能号注册表索引 (.funcid_index.db)         —— 纯数字内部功能号兜底（KCBPSPD.xml + sysfunc_init.sql 权威源，
                                                    弥补代码图谱符号级索引盲区；由 build_funcid_index.py 生成）
  L3   服务治理平台 (Playwright 自动化)             —— 前几级均未命中时才走网络

用法:
  interface_query.py 7300780                 # 自动路由
  interface_query.py T13 A51 L28 --no-fields  # 关闭字段明细
  interface_query.py 展期 --type file        # 限定文件接口
  interface_query.py 7390704 --source web    # 强制走服务治理平台
  interface_query.py 7300780 --json          # 结构化输出
退出码: 0=命中(L1/L2)  10=L1/L2未命中需升级  11=本地资源不可用
"""

import argparse
import io
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------- 路径配置
# 数据源（外置盘）：可被环境变量 INTERFACE_BASE_DIR 覆盖
DEFAULT_BASE_DIR = Path(os.environ.get(
    "INTERFACE_BASE_DIR", "/Volumes/Macintosh HD_Data/WorkBuddy/需求分析"))
BASE_DIR = DEFAULT_BASE_DIR
RULES_DIR = BASE_DIR / "rules-raw"
DB_PATH = RULES_DIR / ".interface_store.db"
FUNCID_DB_PATH = RULES_DIR / ".funcid_index.db"
CSV_PATH = RULES_DIR / "文件接口明细_汇总.csv"
LOCAL_MD_GLOB = "*.md"

INFO_COLS = ["id", "system_type", "system_name", "category", "code", "name",
             "table_name", "version", "manager", "direction", "paired_code", "description"]

# 解析 Excel 时泄漏进来的模板表头行（特征固定：场景名称/子场景名称/示例描述）
JUNK_FIELDS = {("场景名称", "子场景名称", "示例描述")}

SECTION_LABEL = {
    "input": "📥 输入参数",
    "output": "📤 输出参数",
    "file_fields": "📑 文件字段",
    "header": "📑 文件头",
    "body": "📑 文件体",
}


# ---------------------------------------------------------------- 工具
def die(msg, code=11):
    print(f"❌ {msg}")
    sys.exit(code)


def is_junk(field_name, field_type, field_label):
    return (field_name, field_type, field_label) in JUNK_FIELDS


def connect():
    if not DB_PATH.exists():
        die(f"本地接口库不存在: {DB_PATH}\n   请先执行 build_interface_cache.py 构建。", 11)
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    for stmt in ("CREATE INDEX IF NOT EXISTS idx_if_code ON interfaces(code)",
                 "CREATE INDEX IF NOT EXISTS idx_ifld_code ON interface_fields(code)",
                 "CREATE INDEX IF NOT EXISTS idx_ifld_iid ON interface_fields(interface_id)"):
        try:
            con.execute(stmt)
        except sqlite3.OperationalError:
            pass  # 只读库无法建索引属正常
    con.commit()
    return con


# ---------------------------------------------------------------- 检索
def classify_kw(kw):
    """推断查询意图: realtime(纯数字功能号) / file(字母开头文件编号) / keyword"""
    k = kw.strip()
    if re.fullmatch(r"\d{6,}", k):
        return "realtime"
    if re.fullmatch(r"[A-Za-z]{1,3}\d{0,2}", k):
        return "file"
    return "keyword"


def search_db(con, kw, type_filter="any", limit=40):
    """L1: SQLite 检索。优先级: 精确 code > 精确 table_name > 模糊。"""
    hint = classify_kw(kw)
    cur = con.cursor()

    def fetch(sql, params):
        cur.execute(sql, params)
        return cur.fetchall()

    base = "SELECT " + ",".join(INFO_COLS) + " FROM interfaces WHERE 1=1"
    type_sql = {"realtime": " AND system_type='实时接口'",
                "file": " AND system_type='文件接口'",
                "any": ""}[type_filter]
    params_extra = []
    if hint == "realtime" and type_filter == "any":
        type_sql = " AND system_type='实时接口'"
    if hint == "file" and type_filter == "any":
        type_sql = " AND system_type='文件接口'"

    # 1) 精确匹配 code / table_name
    rows = fetch(base + type_sql +
                 " AND (UPPER(code)=UPPER(?) OR UPPER(table_name)=UPPER(?)) ORDER BY code",
                 params_extra + [kw, kw])
    if rows:
        return rows, "exact", hint

    # 2) 模糊匹配
    like = f"%{kw}%"
    rows = fetch(base + type_sql +
                 " AND (code LIKE ? OR UPPER(table_name) LIKE UPPER(?) OR name LIKE ?"
                 " OR system_name LIKE ? OR category LIKE ? OR description LIKE ?)"
                 " ORDER BY (code = ?) DESC, code LIMIT ?",
                 [like, like, like, like, like, like, kw, limit])
    return rows, "fuzzy", hint


def get_fields(con, iid, code):
    cur = con.cursor()
    cur.execute("""SELECT section, field_name, field_type, field_label,
                          is_required, is_pk, default_val, dict_code, remark
                   FROM interface_fields WHERE interface_id=? ORDER BY id""", (iid,))
    out, skipped = [], 0
    for sec, fn, ft, fl, req, pk, dv, dc, rk in cur.fetchall():
        if is_junk(fn, ft, fl):
            skipped += 1
            continue
        out.append({"section": sec, "field_name": fn, "field_type": ft,
                    "field_label": fl, "is_required": req, "is_pk": pk,
                    "default_val": dv, "dict_code": dc, "remark": rk})
    return out, skipped


def search_local_md(kw):
    """L2: 本地 Markdown 规格文档全文检索"""
    hits = []
    if not RULES_DIR.exists():
        return hits
    rx = re.compile(r"\b" + re.escape(kw) + r"\b", re.I)
    for md in sorted(RULES_DIR.glob(LOCAL_MD_GLOB)):
        if md.name.startswith("."):
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if rx.search(text) or kw.lower() in text.lower():
            title = next((l.lstrip("# ").strip() for l in text.splitlines()
                          if l.startswith("# ")), md.stem)
            hits.append({"file": str(md), "name": md.stem, "title": title,
                         "lines": len(text.splitlines())})
    return hits


def search_funcid(kw, limit=20):
    """L1.5: 功能号注册表索引兜底。

    数据源 = 集中交易 KCBPSPD.xml + sysfunc_init.sql 编译的 .funcid_index.db
    （build_funcid_index.py 生成）。弥补代码图谱符号级索引盲区：数字功能号以
    整数常量 / 注释 / XML 属性 / SQL 值形式存在时，图谱 nodes_fts 不建索引必然检索不到；
    本索引以功能注册表为权威源，可确认功能号真实存在并给出 功能名/模块/DLL。
    """
    if not FUNCID_DB_PATH.exists():
        return []
    try:
        con = sqlite3.connect(f"file:{FUNCID_DB_PATH}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("SELECT code, func_name, module, dll, ftype, cache, userexit "
                    "FROM funcids WHERE code=? ORDER BY code", (kw,))
        rows = [dict(r) for r in cur.fetchall()]
        if not rows:
            like = f"%{kw}%"
            cur.execute("SELECT code, func_name, module, dll, ftype, cache, userexit "
                        "FROM funcids WHERE func_name LIKE ? OR module LIKE ? LIMIT ?",
                        (like, like, limit))
            rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return rows
    except sqlite3.Error:
        return []


# ---------------------------------------------------------------- 渲染
def render_iface(row, fields, skipped, src_label):
    d = dict(zip(INFO_COLS, row))
    L = []
    tag = "实时接口" if d["system_type"] == "实时接口" else "文件接口"
    L.append(f"### 📌 {tag} `{d['code']}` — {d['name'] or '(未命名)'}")
    L.append("")
    L.append(f"> 数据来源: **{src_label}** | 系统: {d['system_name'] or '-'}"
             f" | 分类: {d['category'] or '-'}")
    L.append("")
    L.append("| 属性 | 内容 |")
    L.append("| --- | --- |")
    L.append(f"| **功能号 / 文件编号** | `{d['code']}` |")
    L.append(f"| **名称** | {d['name'] or '-'} |")
    if d["table_name"]:
        L.append(f"| **数据库表名** | `{d['table_name']}` |")
    L.append(f"| **接口类型** | {d['system_type']} / {d['system_name'] or '-'} |")
    if d["version"]:
        L.append(f"| **版本号** | {d['version']} |")
    if d["direction"]:
        L.append(f"| **请求应答** | {d['direction']} |")
    if d["manager"]:
        L.append(f"| **负责人** | {d['manager']} |")
    if d["description"]:
        L.append(f"| **功能描述** | {d['description']} |")
    L.append("")

    if not fields:
        L.append("> ℹ️ 本地库未收录该接口的字段明细。")
        L.append("")
        return "\n".join(L)

    order, groups = [], {}
    for f in fields:
        s = f["section"] or "fields"
        if s not in groups:
            groups[s] = []
            order.append(s)
        groups[s].append(f)

    for s in order:
        items = groups[s]
        L.append(f"#### {SECTION_LABEL.get(s, '📑 ' + s)} (共 {len(items)} 项)")
        L.append("")
        if d["system_type"] == "文件接口":
            L.append("| 序号 | 字段 ID | 数据类型 | 中文含义 | 主键 | 格式说明 | 字典代码 |")
            L.append("| :---: | --- | --- | --- | :---: | --- | :---: |")
            for i, f in enumerate(items, 1):
                pk = "**Y**" if f["is_pk"] == "Y" else "-"
                L.append(f"| {i} | `{f['field_name']}` | `{f['field_type']}` | "
                         f"{f['field_label'] or '-'} | {pk} | {f['remark'] or '-'} | "
                         f"{f['dict_code'] or '-'} |")
        else:
            L.append("| 序号 | 字段名 | 数据类型 | 业务说明 | 必须 | 缺省值 / 说明 | 字典代码 |")
            L.append("| :---: | --- | --- | --- | :---: | --- | :---: |")
            for i, f in enumerate(items, 1):
                req = "**Y**" if f["is_required"] == "Y" else "-"
                L.append(f"| {i} | `{f['field_name']}` | `{f['field_type']}` | "
                         f"{f['field_label'] or '-'} | {req} | {f['default_val'] or '-'} | "
                         f"{f['dict_code'] or '-'} |")
        L.append("")

    if skipped:
        L.append(f"> ℹ️ 已自动过滤 {skipped} 行 Excel 模板表头脏数据。")
        L.append("")
    return "\n".join(L)


def render_funcid(rec, src_label):
    """L1.5 功能号索引命中渲染（无字段明细，输出注册表要素）。"""
    d = rec
    L = [f"### ⚙️ 集中交易功能号 `{d['code']}` — {d['func_name'] or '(未命名)'}", ""]
    L.append(f"> 数据来源: **{src_label}** | 系统: 集中交易系统")
    L.append("")
    L.append("| 属性 | 内容 |")
    L.append("| --- | --- |")
    L.append(f"| **功能号** | `{d['code']}` |")
    L.append(f"| **功能名** | {d['func_name'] or '-'} |")
    if d["module"]:
        L.append(f"| **实现模块** | `{d['module']}` |")
    if d["dll"]:
        L.append(f"| **承载 DLL** | `{d['dll']}` |")
    if d["ftype"]:
        L.append(f"| **类型** | {d['ftype']} |")
    if d["cache"]:
        L.append(f"| **缓存** | {d['cache']} |")
    if d["userexit"]:
        L.append(f"| **用户出口数** | {d['userexit']} |")
    L.append("")
    L.append("> ℹ️ 来源：集中交易功能注册表 `KCBPSPD.xml`（module↔DLL）+ `sysfunc_init.sql`（功能名），"
             "功能号真实存在的权威印证。")
    L.append("> 本地接口库（服务治理平台导出）未收录该功能号字段明细；如需字段请用 `--source web` 平台查询。")
    L.append("")
    return "\n".join(L)


def to_json(rows, con, meta):
    data = []
    for r in rows:
        d = dict(zip(INFO_COLS, r))
        flds, skipped = get_fields(con, d["id"], d["code"])
        d["fields"] = flds
        d["_skipped_junk"] = skipped
        data.append(d)
    return json.dumps({**meta, "count": len(data), "results": data},
                      ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- L3
def query_web(keywords, groups=None, headless=True):
    """L3: 服务治理平台查询 (复用 low_latency_query.py)"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, script_dir)
    try:
        import low_latency_query as lwq
    except ImportError as e:
        print(f"⚠️ 无法加载平台查询模块 ({e})，跳过 L3。")
        return False
    for kw in keywords:
        print(f"\n**[L3] 服务治理平台查询: {kw}**")
        try:
            lwq.LowLatencyQuery(keyword=kw, headless=headless, groups=groups).run()
            return True
        except Exception as e:
            print(f"⚠️ L3 查询失败: {e}")
    return False


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        description="接口统一查询 (本地知识库优先，未命中自动升级服务治理平台)",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="示例:\n"
               "  interface_query.py 7300780\n"
               "  interface_query.py T13 A51 L28\n"
               "  interface_query.py 展期 --type file\n"
               "  interface_query.py 9999999            # 本地无 -> 自动升级平台\n"
               "  interface_query.py 7300780 --source web\n")
    ap.add_argument("keywords", nargs="+", help="接口号/文件编号/表名/关键字，支持多个")
    ap.add_argument("-t", "--type", default="any",
                    choices=["any", "realtime", "file"], help="限定接口类型 (默认自动推断)")
    ap.add_argument("-s", "--source", default="local",
                    choices=["local", "web", "auto"],
                    help="local=仅本地; web=强制平台; auto=本地未命中才升级平台")
    ap.add_argument("--no-fields", action="store_true", help="不输出字段明细")
    ap.add_argument("--no-md", action="store_true", help="跳过 L2 本地 Markdown 检索")
    ap.add_argument("--no-web", action="store_true", help="禁止升级到服务治理平台")
    ap.add_argument("--limit", type=int, default=40, help="模糊查询返回上限 (默认40)")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("-n", "--no-headless", action="store_true", help="平台查询显示浏览器界面")
    ap.add_argument("-g", "--groups", help="平台查询按所属分组过滤，逗号分隔")
    args = ap.parse_args()

    t0 = time.perf_counter()
    force_web = args.source == "web"
    allow_web = (args.source == "auto") and not args.no_web

    # 强制走平台
    if force_web:
        sys.exit(0 if query_web(args.keywords, args.groups, not args.no_headless) else 10)

    con = connect()
    total = 0
    funcid_total = 0
    blocks = []
    json_results = []
    matched_any = False

    for kw in args.keywords:
        rows, mode, hint = search_db(con, kw, args.type, args.limit)
        if not rows and not args.no_md:
            md_hits = search_local_md(kw)
        else:
            md_hits = []
        # L1.5 功能号注册表索引兜底（纯数字功能号；图谱符号级盲区的本地权威补偿）
        funcid_hits = (search_funcid(kw)
                       if (not rows and not md_hits and hint == "realtime") else [])

        if not rows and not md_hits and not funcid_hits:
            print(f"\n### ❌ 本地知识库未命中: `{kw}`")
            blocks.append((kw, None, None, 0, 0, []))
            continue

        matched_any = True
        funcid_total += len(funcid_hits)
        if rows:
            mode_cn = "精确命中" if mode == "exact" else "模糊命中"
            src_label = f"本地接口知识库 ({mode_cn} · {hint})"
        else:
            mode_cn, src_label = "功能号索引", "功能号注册表索引 (KCBPSPD.xml + sysfunc_init.sql)"

        if args.json:
            for r in rows:
                json_results.append((kw, r))
            for rec in funcid_hits:
                json_results.append((kw, rec))
            blocks.append((kw, rows, src_label, 0, 0, md_hits))
        else:
            elapsed = (time.perf_counter() - t0) * 1000
            if rows:
                head = (f"\n## 🔎 查询: `{kw}` — 命中 **{len(rows)}** 条 "
                        f"({mode_cn} · {hint}) · 耗时 **{elapsed:.1f} ms**")
            elif funcid_hits:
                head = (f"\n## 🔎 查询: `{kw}` — 本地接口库无记录，"
                        f"命中 **{len(funcid_hits)}** 条功能号注册表索引 (L1.5)"
                        f" · 耗时 **{elapsed:.1f} ms**")
            else:
                head = (f"\n## 🔎 查询: `{kw}` — 本地接口库无记录，"
                        f"命中 **{len(md_hits)}** 份本地规格文档 · 耗时 **{elapsed:.1f} ms**")
            body = []
            for r in rows:
                d = dict(zip(INFO_COLS, r))
                flds, skipped = (get_fields(con, d["id"], d["code"])
                                 if not args.no_fields else ([], 0))
                body.append(render_iface(r, flds, skipped, src_label))
            for rec in funcid_hits:
                body.append(render_funcid(rec, src_label))
            if md_hits:
                body.append("#### 📄 本地规格文档命中 (L2)")
                body.append("")
                for m in md_hits:
                    body.append(f"- `{m['file']}` — {m['title']} ({m['lines']} 行)")
                body.append("")
            print(head)
            print("\n---\n\n".join(body))
            print("\n---\n")

        for r in rows:
            d = dict(zip(INFO_COLS, r))
            flds, skipped = get_fields(con, d["id"], d["code"])
            blocks.append((kw, d, src_label, len(flds), skipped, md_hits))
            total += 1

    if args.json:
        payload = {
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
            "total": len(json_results),
            "source": "local-sqlite",
            "db": str(DB_PATH),
            "matched": matched_any,
            "results": [
                (dict(zip(INFO_COLS, r),
                      fields=get_fields(con, dict(zip(INFO_COLS, r))["id"],
                                        dict(zip(INFO_COLS, r))["code"])[0])
                 if isinstance(r, tuple) else r)
                for _, r in json_results
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    # 汇总 + 升级判定
    elapsed = (time.perf_counter() - t0) * 1000
    extra = f" | 功能号索引命中 **{funcid_total}** 条" if funcid_total else ""
    print(f"\n> ⚡ 本地查询耗时 **{elapsed:.1f} ms** | 命中 **{total}** 条"
          f"{extra} | 数据源 `rules-raw/.interface_store.db`")

    if not matched_any:
        print("\n> 🔺 本地 L1/L2 均未命中，按需升级 L3 服务治理平台…")
        if allow_web:
            query_web(args.keywords, args.groups, not args.no_headless)
            sys.exit(0)
        print("> ⛔ 已按参数禁止联网升级。改用 `--source auto` 开启平台查询。")
        sys.exit(10)

    sys.exit(0)


if __name__ == "__main__":
    main()
