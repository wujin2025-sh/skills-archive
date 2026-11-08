#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
接口知识库构建脚本 (Local-First L1 数据源)
==================================================
将「实时接口明细」「文件接口明细」下的 Excel 编译为 SQLite 接口知识库，
供 interface_query.py 毫秒级查询（真实接口号 / 表名 / 关键字 + 全部字段明细）。

用法:
  build_interface_cache.py                    # 使用默认路径重建
  build_interface_cache.py --db /tmp/x.db     # 指定输出库
  build_interface_cache.py --base-dir <需求分析目录>
  build_interface_cache.py --check            # 仅体检源数据，不重建

依赖: openpyxl
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("❌ 缺少依赖 openpyxl: pip install openpyxl")
    sys.exit(1)

# 默认数据源（外置盘）
DEFAULT_BASE_DIR = Path("/Volumes/Macintosh HD_Data/WorkBuddy/需求分析")
DEFAULT_DB_NAME = ".interface_store.db"

# Excel 模板表头脏数据（特征固定：场景名称/子场景名称/示例描述），解析时源头过滤
JUNK_TRIADS = {("场景名称", "子场景名称", "示例描述")}


def resolve_paths(base_dir=None, db_path=None):
    base = Path(base_dir).expanduser() if base_dir else DEFAULT_BASE_DIR
    rules = base / "rules-raw"
    db = Path(db_path).expanduser() if db_path else rules / DEFAULT_DB_NAME
    return base, rules, db


# ---------------------------------------------------------------- 建库
def init_db(conn):
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS interfaces")
    cur.execute("DROP TABLE IF EXISTS interface_fields")
    cur.execute("""
    CREATE TABLE interfaces (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        system_type TEXT,      -- 实时接口 / 文件接口
        system_name TEXT,      -- 低延时交易系统 / 集中交易 / 交易参数管理后台系统 等
        category TEXT,         -- 外围接口 / 柜台接口 / AGW / 交易参数 等
        code TEXT,             -- 功能号 / 文件编号 (如 7390704, S03, 420662)
        name TEXT,             -- 接口名称 / 表中文名
        table_name TEXT,       -- 对应数据库表名 (如 credittargetstk)
        version TEXT,
        manager TEXT,
        direction TEXT,        -- 请求 / 应答 / 双向 / 文件
        paired_code TEXT,      -- 关联功能号
        description TEXT,
        raw_json TEXT
    )""")
    cur.execute("""
    CREATE TABLE interface_fields (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        interface_id INTEGER,
        code TEXT,
        section TEXT,          -- input / output / file_fields
        field_name TEXT,
        field_type TEXT,
        field_label TEXT,
        is_required TEXT,
        is_pk TEXT,
        default_val TEXT,
        dict_code TEXT,
        remark TEXT,
        FOREIGN KEY(interface_id) REFERENCES interfaces(id)
    )""")
    for stmt in ("CREATE INDEX idx_iface_code ON interfaces(code)",
                 "CREATE INDEX idx_iface_table ON interfaces(table_name)",
                 "CREATE INDEX idx_iface_name ON interfaces(name)",
                 "CREATE INDEX idx_iface_stype ON interfaces(system_type)",
                 "CREATE INDEX idx_fields_code ON interface_fields(code)",
                 "CREATE INDEX idx_fields_name ON interface_fields(field_name)",
                 "CREATE INDEX idx_fields_iid ON interface_fields(interface_id)"):
        cur.execute(stmt)
    conn.commit()


def is_junk(fname, ftype, flabel):
    return (fname, ftype, flabel) in JUNK_TRIADS


def load_grid(ws):
    """一次性把整个 sheet 读入内存二维列表。

    openpyxl 的 ws.cell(r, c) 每次调用都会重新解析底层 XML，
    在本量级（源 xlsx 约 4MB / 十万级单元格）下耗时可达数十分钟；
    改用 iter_rows 一次性读入后按索引访问，耗时降至秒级。
    """
    return [[("" if v is None else v) for v in row]
            for row in ws.iter_rows(values_only=True)]


def cell(grid, r, c):
    """按 openpyxl 的 1-based (row, col) 取值，越界返回空串。"""
    if 1 <= r <= len(grid) and 1 <= c <= len(grid[r - 1]):
        return grid[r - 1][c - 1]
    return ""


def s(v):
    return str(v).strip()


# ---------------------------------------------------------------- 文件接口
def parse_file_interfaces(wb_path, conn):
    print(f"[解析] 文件接口: {wb_path.name}")
    wb = openpyxl.load_workbook(wb_path, data_only=True)
    cur = conn.cursor()

    for sheetname in wb.sheetnames:
        g = load_grid(wb[sheetname])
        max_r, r = len(g), 1
        while r <= max_r:
            c2 = s(cell(g, r, 2))
            c3 = s(cell(g, r, 3))

            if c2 == "文件编号" or (c2 == "" and c3 in
                                   ["S01", "S02", "S03", "S04", "S05", "Z59", "Z60", "Z61"]):
                file_code = c3
                table_name = s(cell(g, r, 7))

                if_name = ""
                if r + 1 <= max_r and s(cell(g, r + 1, 2)) == "接口名称":
                    if_name = s(cell(g, r + 1, 3))

                if file_code:
                    cur.execute("""
                    INSERT INTO interfaces (system_type, system_name, category, code, name,
                                            table_name, direction, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                                ("文件接口", sheetname, "交易参数文件", file_code, if_name,
                                 table_name, "文件", f"{if_name} ({table_name})"))
                    iface_id = cur.lastrowid

                    rf = r + 2
                    while rf <= max_r:
                        if rf > r + 3 and s(cell(g, rf, 2)) in ("文件编号", "功能号", "备注说明"):
                            break

                        f_id = s(cell(g, rf, 4))
                        f_type = s(cell(g, rf, 5))
                        f_label = s(cell(g, rf, 6))
                        f_fmt = s(cell(g, rf, 7))
                        f_pk = s(cell(g, rf, 8))
                        f_dict = s(cell(g, rf, 10))

                        if f_id and f_id != "字段ID" and f_type and not is_junk(f_id, f_type, f_label):
                            cur.execute("""
                            INSERT INTO interface_fields (interface_id, code, section, field_name,
                                field_type, field_label, is_required, is_pk, default_val,
                                dict_code, remark)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                        (iface_id, file_code, "file_fields", f_id, f_type, f_label,
                                         "Y" if f_pk == "Y" else "", f_pk, "", f_dict, f_fmt))
                        rf += 1
                    r = rf
                    continue
            r += 1
    conn.commit()


# ---------------------------------------------------------------- 实时接口
def parse_realtime_interfaces(wb_path, conn):
    print(f"[解析] 实时接口: {wb_path.name}")
    wb = openpyxl.load_workbook(wb_path, data_only=True)
    cur = conn.cursor()
    sys_base = wb_path.stem.replace("接口列表-", "")

    for sheetname in wb.sheetnames:
        if sheetname in ("接口列表", "字典", "字典基础信息"):
            continue
        g = load_grid(wb[sheetname])
        max_r, r = len(g), 1
        ncol = max((len(row) for row in g), default=0)

        while r <= max_r:
            if s(cell(g, r, 2)) != "功能号":
                r += 1
                continue

            func_code = s(cell(g, r, 3))
            func_name = version = manager = desc = ""

            for sr in range(r + 1, min(r + 8, max_r + 1)):
                s2, s3 = s(cell(g, sr, 2)), s(cell(g, sr, 3))
                if s2 == "功能名称":
                    func_name = s3
                    if s(cell(g, sr, 4)) == "版本号":
                        version = s(cell(g, sr, 5))
                elif s2 == "接口负责人":
                    manager = s3
                elif s2 == "功能描述":
                    desc = s3

            direction = ("请求" if func_code.startswith(("73", "41"))
                         else "应答" if func_code.startswith("74") else "双向")

            cur.execute("""
            INSERT INTO interfaces (system_type, system_name, category, code, name,
                                    version, manager, direction, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        ("实时接口", sys_base, sheetname, func_code, func_name,
                         version, manager, direction, desc))
            iface_id = cur.lastrowid

            section = "input"
            sr = r + 5
            while sr <= max_r:
                row_c2 = s(cell(g, sr, 2))
                if row_c2 == "功能号" and sr > r + 5:
                    break
                if row_c2 == "输入参数":
                    section = "input"
                    sr += 1
                    continue
                if row_c2 == "输出参数":
                    section = "output"
                    sr += 1
                    continue

                f_name = s(cell(g, sr, 3))
                f_type = s(cell(g, sr, 4))
                f_desc = s(cell(g, sr, 5))
                f_req = s(cell(g, sr, 6))
                f_def = s(cell(g, sr, 7))
                f_dict = s(cell(g, sr, 8)) if ncol >= 8 else ""

                if (f_name and f_name not in ("参数名", "错误号") and f_type
                        and not f_name.startswith("（") and not is_junk(f_name, f_type, f_desc)):
                    cur.execute("""
                    INSERT INTO interface_fields (interface_id, code, section, field_name,
                        field_type, field_label, is_required, default_val, dict_code, remark)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (iface_id, func_code, section, f_name, f_type, f_desc,
                                 f_req, f_def, f_dict, ""))
                sr += 1
            r = sr
    conn.commit()


# ---------------------------------------------------------------- 体检
def check_sources(base, rules):
    print(f"📂 数据源体检: {base}")
    ok = True
    rt = rules / "实时接口明细"
    fi = rules / "文件接口明细"
    for label, d in (("实时接口明细", rt), ("文件接口明细", fi)):
        if not d.exists():
            print(f"  ❌ {label} 目录缺失: {d}")
            ok = False
            continue
        files = sorted(d.glob("*.xlsx"))
        if not files:
            print(f"  ⚠️  {label} 无 xlsx 文件")
        for f in files:
            print(f"  ✅ {label}: {f.name} ({f.stat().st_size // 1024} KB)")
    db = rules / DEFAULT_DB_NAME
    if db.exists():
        print(f"  ✅ 现有库: {db.name} ({db.stat().st_size // 1024 // 1024} MB)")
    else:
        print("  ℹ️  尚未构建接口库")
    return ok


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="构建接口 SQLite 知识库（interface_query.py 的 L1 数据源）")
    ap.add_argument("--base-dir", help=f"需求分析根目录（默认 {DEFAULT_BASE_DIR}）")
    ap.add_argument("--db", help="输出 SQLite 路径（默认 <base-dir>/rules-raw/.interface_store.db）")
    ap.add_argument("--check", action="store_true", help="仅体检源数据，不重建")
    args = ap.parse_args()

    base, rules, db_path = resolve_paths(args.base_dir, args.db)

    if args.check:
        sys.exit(0 if check_sources(base, rules) else 1)

    if not rules.exists():
        print(f"❌ 目录不存在: {rules}")
        print(f"   请确认外置盘已挂载，或用 --base-dir 指定正确路径。")
        sys.exit(1)

    rt, fi = rules / "实时接口明细", rules / "文件接口明细"
    src = sorted(rt.glob("*.xlsx")) + sorted(fi.glob("*.xlsx"))
    if not src:
        print(f"❌ 未找到任何源 xlsx（{rt} / {fi}），无法构建。")
        sys.exit(1)

    print(f"🔨 重建接口知识库 -> {db_path}")
    if db_path.exists():
        backup = db_path.with_suffix(".db.bak")
        os.replace(db_path, backup)
        print(f"   原库已备份: {backup.name}")

    conn = sqlite3.connect(db_path)
    init_db(conn)
    for xlsx in sorted(rt.glob("*.xlsx")):
        parse_realtime_interfaces(xlsx, conn)
    for xlsx in sorted(fi.glob("*.xlsx")):
        parse_file_interfaces(xlsx, conn)

    cur = conn.cursor()
    n_if = cur.execute("SELECT count(*) FROM interfaces").fetchone()[0]
    n_fd = cur.execute("SELECT count(*) FROM interface_fields").fetchone()[0]
    n_junk = cur.execute(
        "SELECT count(*) FROM interface_fields WHERE field_name='场景名称' AND field_type='子场景名称'"
    ).fetchone()[0]
    by_type = dict(cur.execute(
        "SELECT system_type, count(*) FROM interfaces GROUP BY system_type").fetchall())
    conn.close()

    print(f"\n✅ 构建完成")
    print(f"📦 路径: {db_path}")
    print(f"📊 接口: {n_if} 个  {by_type}")
    print(f"📑 字段: {n_fd} 条")
    print(f"🧹 残留模板表头脏数据: {n_junk} 行" + (" ✅" if n_junk == 0 else " ⚠️"))


if __name__ == "__main__":
    main()
