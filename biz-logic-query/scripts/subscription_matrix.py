#!/usr/bin/env python3
"""订阅矩阵库 (subscription_matrix.db)

从「新一代文件交互接口订阅矩阵.xlsx」构建可查询的 SQLite 库，回答
「某文件编号（如 A37）有哪些消费者 / 某系统订阅了哪些文件」。

数据源
  XLSX     新一代文件交互接口订阅矩阵.xlsx  (Sheet1, 文件×系统打勾矩阵, √=订阅)
  IFACE_DB .interface_store.db             (接口主记录/字段明细, 用于补元数据)

用法
  python3 subscription_matrix.py build                # 重建数据库（xlsx 更新后重跑）
  python3 subscription_matrix.py query A37            # 查某文件的消费者 + 实证证据
  python3 subscription_matrix.py consumer 低延时交易系统  # 反查某系统订阅了哪些文件
  python3 subscription_matrix.py stats                # 总览
  python3 subscription_matrix.py sql "SELECT ..."      # 自由查询

设计要点
  * 原 xlsx 只读，绝不写回；产物是独立 .db，与 .interface_store.db 并列。
  * A 列「输出系统」为稀疏合并单元格 -> 前向填充(forward fill)。
  * 第 17 列「是否根据分区号下发（仅限低延时订阅）」是属性列，不是消费者。
  * subscriptions.evidence_status 默认「🟢 矩阵原样」；A37/Q49/S140 等多源实证行标「🟢 多源实证」。
  * evidence 表沉淀跨源实证与待确认项，status: 🟢已实证 / 🟡可追溯 / 🔴待确认。
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path

BASE = Path("/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/rules-raw")
XLSX = BASE / "文件接口明细" / "新一代文件交互接口订阅矩阵.xlsx"
IFACE_DB = BASE / ".interface_store.db"
OUT_DB = BASE / ".subscription_matrix.db"
CHECKED = date.today().isoformat()

# 非消费者列（属性列）
ATTR_COLUMNS = {"是否根据分区号下发（仅限低延时订阅）"}

# 多源实证/待确认证据（2026-11-13 A37 证据链调研结论）
EVIDENCE = [
    ("A37", "订阅矩阵", f"{XLSX.name} Sheet1 R299",
     "A37 大宗交易预委托记录信息表：输出系统=集中清算系统，唯一消费者=低延时交易系统(虚拟)", "🟢已实证"),
    ("A37", "接口库", ".interface_store.db interfaces code=A37",
     "集中清算系统｜交易参数文件｜表 dzjypreorder｜39 字段｜主键 serverid+sysdate+sno", "🟢已实证"),
    ("A37", "源码", "jzqs/src/src/src_sql/4_file_import/文件导出脚本/低延时按serverid拆分/node_dzjypreorder_out_file.sql",
     "fileid=JZQS_DZJYPREORDER_DYS、intfid=JZQS_DYS、iodirect=O；文件名 CFD_130_@receiver_@nextbusidate_A37.TXT（按 serverid 拆分）；CRLF + CHAR(1) 列分隔、文件头 totalnum、37 列", "🟢已实证"),
    ("A37", "源码", "jzqs 信创-文件导出脚本/同路径 node_dzjypreorder_out_file.sql",
     "信创版同构，同为 37 列", "🟢已实证"),
    ("A37", "数据库", "jzqs_sit node.dys_dzjypreorder",
     "SIT 抽样 market=9 / stkcode=920745 / extstr=0899074922（北交所对手方股东账户），改造已落地", "🟢已实证"),
    ("A37", "需求", "20261012-R2610120043-关于北交所信用账户大宗交易需求.md L233-243 / L278",
     "Q49 低延时→集中交易/集中清算下发；A37 集中清算→低延时回流（清算核对）；两者复用 extstr 承载北交所对手方股东账户；预计 2026-11 上线", "🟢已实证"),
    ("A37", "口径核销", "订阅矩阵 R299 + 需求 R2610120043 vs jzqs 导出脚本注释",
     "上一轮待确认项②「源码注释接收方=集中交易系统 vs 需求=低延时」已核销：订阅矩阵明确 A37 唯一订阅者为低延时交易系统(虚拟)，源码注释为泛称/口径偏差", "🟢已实证"),
    ("A37", "待确认", "接口库 39 字段 vs 源码导出脚本 37 列",
     "差 operwayext / userinfo 两字段，需开发确认是否漏导出", "🔴待确认"),
    ("A37", "待确认", "jzqs_sit node.cjs_dzjypreorder",
     "SIT 当前 0 行，A37 回流通道暂无测试数据（dys 侧已有数据）", "🔴待确认"),
    ("Q49", "订阅矩阵", f"{XLSX.name} Sheet1 R523",
     "Q49 大宗交易预委托记录信息表：输出系统=低延时交易系统(虚拟)，消费者=集中清算系统 + 集中交易系统", "🟢已实证"),
    ("Q49", "接口库", ".interface_store.db interfaces code=Q49",
     "低延时交易系统(虚拟)｜同表 dzjypreorder｜35 字段（独有 custid/fundid/orderwayext）", "🟢已实证"),
    ("Q49", "待确认", "jzqs src_sql 全库检索",
     "Q49 的文件定义在 jzqs 侧未找到，疑在低延时侧或文件接口平台", "🔴待确认"),
    ("S140", "订阅矩阵", f"{XLSX.name} Sheet1 R49",
     "S140 大宗交易预委托营业部审批权限信息：输出=交易参数管理后台系统，消费者=低延时交易系统(虚拟)", "🟢已实证"),
    ("S140", "接口库", ".interface_store.db interfaces code=S140",
     "交易参数管理后台｜表 dzjy_brhright｜2 字段 brhid/opendate", "🟢已实证"),
]

SCHEMA = """
CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE columns_meta (
    col_index INTEGER PRIMARY KEY, col_name TEXT,
    is_consumer INTEGER, mark_count INTEGER
);
CREATE TABLE files (
    file_code TEXT PRIMARY KEY,
    file_name TEXT,
    producer_system TEXT,          -- 订阅矩阵「输出系统」(前向填充)
    interface_system TEXT,          -- 接口库 system_name
    category TEXT,
    interface_table TEXT,
    version TEXT,
    manager TEXT,
    interface_id INTEGER,
    interface_matched INTEGER DEFAULT 0,
    source_row INTEGER,
    evidence_status TEXT DEFAULT '🟢 矩阵原样'
);
CREATE TABLE consumers (
    consumer TEXT PRIMARY KEY,
    subscription_count INTEGER DEFAULT 0
);
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_code TEXT NOT NULL,
    consumer TEXT NOT NULL,
    mark TEXT DEFAULT '√',
    producer_system TEXT,
    source_row INTEGER,
    source_col INTEGER,
    source_col_name TEXT,
    evidence_status TEXT DEFAULT '🟢 矩阵原样',
    note TEXT,
    UNIQUE(file_code, consumer)
);
CREATE INDEX idx_sub_file ON subscriptions(file_code);
CREATE INDEX idx_sub_consumer ON subscriptions(consumer);
CREATE INDEX idx_sub_producer ON subscriptions(producer_system);
CREATE TABLE evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_code TEXT,
    source_type TEXT,
    source_ref TEXT,
    finding TEXT,
    status TEXT,
    checked_at TEXT
);
CREATE INDEX idx_ev_file ON evidence(file_code);
CREATE VIEW v_file_consumers AS
    SELECT s.file_code, f.file_name, f.producer_system, f.interface_system,
           f.interface_table, s.consumer, s.evidence_status, s.source_row
    FROM subscriptions s JOIN files f ON f.file_code = s.file_code;
CREATE VIEW v_a37_consumers AS
    SELECT * FROM v_file_consumers WHERE file_code = 'A37';
"""


def load_rows():
    try:
        import openpyxl
    except ImportError:
        sys.exit("缺少 openpyxl：请用带 openpyxl 的 Python 运行")
    if not XLSX.exists():
        sys.exit(f"订阅矩阵 xlsx 不存在（外部卷是否已挂载？）：{XLSX}")
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    return rows


def build() -> None:
    rows = load_rows()
    hdr = rows[0]
    # 有效列：仅取表头非空的连续前 22 列（max_column=16384 是格式噪声）
    cols = [(i, str(h).strip()) for i, h in enumerate(hdr[:22]) if h not in (None, "")]
    consumer_cols = [(i, h) for i, h in cols[3:] if h not in ATTR_COLUMNS]
    attr_cols = [(i, h) for i, h in cols[3:] if h in ATTR_COLUMNS]

    iface = {}
    if IFACE_DB.exists():
        c = sqlite3.connect(f"file:{IFACE_DB}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        for r in c.execute("SELECT * FROM interfaces"):
            iface[str(r["code"]).strip()] = dict(r)
        c.close()

    tmp = OUT_DB.with_suffix(".db.tmp")
    if tmp.exists():
        tmp.unlink()
    db = sqlite3.connect(tmp)
    db.executescript(SCHEMA)

    files, subs, marks = [], [], {}
    cur_producer = ""
    for rn, r in enumerate(rows[1:], 2):
        if r[0] not in (None, ""):
            cur_producer = str(r[0]).strip()
        code = str(r[1] or "").strip()
        if not code:                       # 81 行空行/分组间隔
            continue
        name = str(r[2] or "").strip()
        meta = iface.get(code)
        files.append((
            code, name, cur_producer,
            meta["system_name"] if meta else None,
            meta["category"] if meta else None,
            meta["table_name"] if meta else None,
            meta["version"] if meta else None,
            meta["manager"] if meta else None,
            meta["id"] if meta else None,
            1 if meta else 0,
            rn,
            "🟢 多源实证" if code in {e[0] for e in EVIDENCE} else "🟢 矩阵原样",
        ))
        for ci, cname in consumer_cols:
            v = r[ci] if ci < len(r) else None
            if str(v or "").strip() != "√":
                continue
            marks[cname] = marks.get(cname, 0) + 1
            subs.append((code, cname, "√", cur_producer, rn, ci + 1, cname,
                         "🟢 多源实证" if code in {e[0] for e in EVIDENCE} else "🟢 矩阵原样",
                         None))

    db.executemany("INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", files)
    db.executemany(
        "INSERT INTO subscriptions (file_code,consumer,mark,producer_system,"
        "source_row,source_col,source_col_name,evidence_status,note) "
        "VALUES (?,?,?,?,?,?,?,?,?)", subs)
    db.executemany("INSERT INTO consumers VALUES (?,?)",
                   [(h, marks.get(h, 0)) for _, h in consumer_cols])
    db.executemany("INSERT INTO columns_meta VALUES (?,?,?,?)",
                   [(i + 1, h, 1, marks.get(h, 0)) for i, h in consumer_cols] +
                   [(i + 1, h, 0, 0) for i, h in attr_cols])
    db.executemany("INSERT INTO evidence (file_code,source_type,source_ref,finding,status,checked_at) "
                   "VALUES (?,?,?,?,?,?)",
                   [(c, t, ref, f, s, CHECKED) for c, t, ref, f, s in EVIDENCE])
    matched = sum(1 for f in files if f[9])
    db.executemany("INSERT INTO meta VALUES (?,?)", [
        ("source_xlsx", str(XLSX)),
        ("source_sheet", "Sheet1"),
        ("source_iface_db", str(IFACE_DB)),
        ("built_at", CHECKED),
        ("file_count", str(len(files))),
        ("subscription_count", str(len(subs))),
        ("consumer_column_count", str(len(consumer_cols))),
        ("interface_matched", f"{matched}/{len(files)}"),
        ("evidence_status_legend", "🟢 矩阵原样=仅来自订阅矩阵；🟢 多源实证=另有接口库/源码/数据库/需求佐证；🔴待确认=见 evidence 表"),
    ])
    db.commit()
    db.close()
    os.replace(tmp, OUT_DB)
    print(f"✅ 已构建 {OUT_DB}")
    print(f"   文件 {len(files)}｜订阅关系 {len(subs)}｜消费者列 {len(consumer_cols)}｜"
          f"接口库关联 {matched}/{len(files)}｜实证记录 {len(EVIDENCE)}")


def connect():
    if not OUT_DB.exists():
        sys.exit(f"数据库不存在，请先运行 build：{OUT_DB}")
    db = sqlite3.connect(f"file:{OUT_DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def query(code: str) -> None:
    db = connect()
    f = db.execute("SELECT * FROM files WHERE file_code=?", (code,)).fetchone()
    if not f:
        print(f"❌ 订阅矩阵中无文件编号 {code}")
        like = db.execute("SELECT file_code,file_name FROM files WHERE file_code LIKE ? OR file_name LIKE ? LIMIT 8",
                          (f"%{code}%", f"%{code}%")).fetchall()
        for r in like:
            print(f"   近似: {r['file_code']} | {r['file_name']}")
        return
    print(f"\n📄 {f['file_code']}  {f['file_name']}")
    print(f"   输出系统(生产者) : {f['producer_system']}")
    print(f"   接口库            : {f['interface_system'] or '未命中'} | {f['category'] or '-'} | "
          f"表 {f['interface_table'] or '-'} | {f['version'] or '-'}")
    print(f"   矩阵行 R{f['source_row']} | 实证状态 {f['evidence_status']}")
    subs = db.execute("SELECT * FROM subscriptions WHERE file_code=? ORDER BY consumer", (code,)).fetchall()
    print(f"\n   消费者 ({len(subs)}):")
    for s in subs:
        print(f"     √ {s['consumer']}  [{s['evidence_status']}]  (矩阵列 {s['source_col']})")
    ev = db.execute("SELECT * FROM evidence WHERE file_code=? ORDER BY id", (code,)).fetchall()
    if ev:
        print(f"\n   实证证据 ({len(ev)}):")
        for e in ev:
            print(f"     {e['status']} [{e['source_type']}] {e['source_ref']}")
            print(f"        {e['finding']}")
    db.close()


def consumer(system: str) -> None:
    db = connect()
    rows = db.execute(
        "SELECT s.file_code, f.file_name, f.producer_system, s.evidence_status "
        "FROM subscriptions s JOIN files f ON f.file_code=s.file_code "
        "WHERE s.consumer LIKE ? ORDER BY s.file_code", (f"%{system}%",)).fetchall()
    print(f"\n『{system}』订阅文件 {len(rows)} 个：")
    for r in rows[:40]:
        print(f"  {r['file_code']:<6} | {str(r['file_name'])[:38]:<38} | 输出={r['producer_system']} | {r['evidence_status']}")
    if len(rows) > 40:
        print(f"  ... 其余 {len(rows)-40} 条，用 sql 子查询")
    by_prod = db.execute(
        "SELECT producer_system, COUNT(*) n FROM subscriptions WHERE consumer LIKE ? "
        "GROUP BY producer_system ORDER BY n DESC", (f"%{system}%",)).fetchall()
    print("\n  按输出系统分布:")
    for r in by_prod:
        print(f"    {r['producer_system']}: {r['n']}")
    db.close()


def stats() -> None:
    db = connect()
    print("\n== meta ==")
    for r in db.execute("SELECT * FROM meta"):
        print(f"  {r['k']}: {r['v']}")
    print("\n== 消费者订阅数 TOP ==")
    for r in db.execute("SELECT * FROM consumers ORDER BY subscription_count DESC"):
        print(f"  {r['consumer']}: {r['subscription_count']}")
    print("\n== 输出系统（生产者）文件数 ==")
    for r in db.execute("SELECT producer_system, COUNT(*) n FROM files GROUP BY producer_system ORDER BY n DESC"):
        print(f"  {r['producer_system']}: {r['n']}")
    db.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="订阅矩阵库：构建与查询")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("build", help="从 xlsx 重建数据库")
    q = sub.add_parser("query", help="查某文件编号的消费者")
    q.add_argument("code")
    c = sub.add_parser("consumer", help="反查某系统订阅了哪些文件")
    c.add_argument("system")
    sub.add_parser("stats", help="总览")
    s = sub.add_parser("sql", help="自由查询")
    s.add_argument("statement")
    a = ap.parse_args()
    if a.cmd == "build":
        build()
    elif a.cmd == "query":
        query(a.code.strip())
    elif a.cmd == "consumer":
        consumer(a.system.strip())
    elif a.cmd == "stats":
        stats()
    elif a.cmd == "sql":
        db = connect()
        for r in db.execute(a.statement):
            print(" | ".join(str(x) for x in tuple(r)))
        db.close()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
