#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功能号索引构建脚本 (L1.5 兜底数据源)
==================================================
从集中交易源码权威源提取「功能号 → 功能名 / 模块 / DLL」映射，编译为 SQLite 功能号索引，
弥补两个缺口：
  1) L1 接口库（服务治理平台导出）未收录的内部功能号
  2) 代码知识图谱符号级索引盲区（数字功能号以整数常量 / 注释 / XML 属性 / SQL 值
     形式存在时，nodes_fts 不建索引必然检索不到）

数据源（只读）:
  1) {spbsrc}/lbmdll/bin/KCBPSPD.xml       功能注册表（6054 个 <program>：name↔module↔path/type/cache/userexitnumber）  [UTF-8]
  2) {spbsrc}/server/init/sysfunc_init.sql 功能表初始化（6229 条 insert run..sysfunc：funcid↔funcname）                    [GBK]

用法:
  build_funcid_index.py                          # 默认路径构建（输出到 rules-raw/.funcid_index.db）
  build_funcid_index.py --spbsrc <集中交易源码根路径>
  build_funcid_index.py --check                  # 仅体检数据源，不建库
"""

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path

DEFAULT_SPBSRC = Path("/Volumes/Macintosh HD_Data/Project/jzjy/spbsrc")
DEFAULT_BASE_DIR = Path("/Volumes/Macintosh HD_Data/WorkBuddy/需求分析")
DEFAULT_DB_NAME = ".funcid_index.db"

# KCBPSPD.xml 中与 sysfunc_init.sql 的 funcid 一起出现的非数字 name（特殊功能，保留但查询时按数字功能号匹配）
XML_ATTRS = ("name", "module", "path", "type", "cache", "userexitnumber")


def resolve_paths(base_dir=None, spbsrc=None, db_path=None):
    base = Path(base_dir).expanduser() if base_dir else DEFAULT_BASE_DIR
    src = Path(spbsrc).expanduser() if spbsrc else DEFAULT_SPBSRC
    db = Path(db_path).expanduser() if db_path else base / "rules-raw" / DEFAULT_DB_NAME
    xml = src / "lbmdll" / "bin" / "KCBPSPD.xml"
    sql = src / "server" / "init" / "sysfunc_init.sql"
    return base, src, db, xml, sql


def read_text_maybe_gbk(p: Path):
    """优先 UTF-8，失败回退 GBK（sysfunc_init.sql 为 GBK）。"""
    raw = p.read_bytes()
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_kcbpspd(xml_path: Path):
    """KCBPSPD.xml → {funcid: {module, dll, ftype, cache, userexit}}"""
    txt = read_text_maybe_gbk(xml_path)
    out = {}
    for m in re.finditer(r"<program\s+([^>]*?)/?>", txt):
        attrs = m.group(1)
        name = re.search(r'name="([^"]*)"', attrs)
        if not name:
            continue
        code = name.group(1)
        rec = {}
        mod = re.search(r'module="([^"]*)"', attrs)
        rec["module"] = mod.group(1) if mod else ""
        pth = re.search(r'path="([^"]*)"', attrs)
        rec["dll"] = os.path.basename((pth.group(1) if pth else "").replace("\\", "/"))
        t = re.search(r'type="([^"]*)"', attrs)
        rec["ftype"] = t.group(1) if t else ""
        c = re.search(r'cache="([^"]*)"', attrs)
        rec["cache"] = c.group(1) if c else ""
        u = re.search(r'userexitnumber="([^"]*)"', attrs)
        rec["userexit"] = u.group(1) if u else ""
        out[code] = rec
    return out


def parse_sysfunc(sql_path: Path):
    """sysfunc_init.sql → {funcid: funcname}（GBK）"""
    txt = read_text_maybe_gbk(sql_path)
    out = {}
    pat = re.compile(
        r"insert\s+run\.\.sysfunc\b[^;]*?select\s+@sid\s*,\s*(\d+)\s*,\s*'([^']*)'",
        re.I | re.S)
    for fid, fname in pat.findall(txt):
        out.setdefault(fid, fname)
    return out


def init_db(conn):
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS funcids")
    cur.execute("DROP TABLE IF EXISTS meta")
    cur.execute("""
    CREATE TABLE funcids (
        code TEXT PRIMARY KEY,     -- 功能号（纯数字）
        func_name TEXT,            -- 功能名（来自 sysfunc_init.sql）
        module TEXT,               -- 实现模块/函数（来自 KCBPSPD.xml）
        dll TEXT,                  -- 承载 DLL（来自 path 提取）
        ftype TEXT,                -- biz / qry / job ...
        cache TEXT,                -- yes / no
        userexit TEXT              -- 用户出口数
    )""")
    cur.execute("CREATE INDEX idx_funcid_name ON funcids(func_name)")
    cur.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT)")
    conn.commit()


def main():
    ap = argparse.ArgumentParser(description="功能号索引构建（L1.5 兜底数据源）")
    ap.add_argument("--base-dir", default=None, help="需求分析目录（默认外置盘路径）")
    ap.add_argument("--spbsrc", default=None, help="集中交易源码根路径（含 lbmdll/bin/KCBPSPD.xml）")
    ap.add_argument("--db", default=None, help="输出 SQLite 路径（默认 rules-raw/.funcid_index.db）")
    ap.add_argument("--check", action="store_true", help="仅体检数据源，不建库")
    args = ap.parse_args()

    base, src, db, xml_p, sql_p = resolve_paths(args.base_dir, args.spbsrc, args.db)
    miss = [str(p) for p in (xml_p, sql_p) if not p.exists()]
    if miss:
        print("❌ 数据源缺失:\n  " + "\n  ".join(miss))
        print("  可用 --spbsrc <集中交易源码根路径> 指定。")
        sys.exit(1)

    progs = parse_kcbpspd(xml_p)
    funcs = parse_sysfunc(sql_p)
    print(f"数据源体检:")
    print(f"  KCBPSPD.xml (UTF-8)   : {len(progs)} 个 program（其中纯数字功能号 "
          f"{sum(1 for k in progs if k.isdigit())}）")
    print(f"  sysfunc_init.sql (GBK): {len(funcs)} 条 funcid↔funcname")

    if args.check:
        print("\n[check 模式] 未建库。可用接口: 121335 →"
              f" {funcs.get('121335', '-')} / module={progs.get('121335', {}).get('module', '-')}")
        return

    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        bak = db.with_suffix(db.suffix + ".bak")
        bak.unlink(missing_ok=True)
        db.rename(bak)
        print(f"  已备份旧库 -> {bak.name}")

    conn = sqlite3.connect(str(db))
    init_db(conn)
    w = 0
    for code, rec in progs.items():
        conn.execute(
            "INSERT OR REPLACE INTO funcids(code, func_name, module, dll, ftype, cache, userexit) "
            "VALUES (?,?,?,?,?,?,?)",
            (code, funcs.get(code, ""), rec["module"], rec["dll"],
             rec["ftype"], rec["cache"], rec["userexit"]))
        w += 1
    conn.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('built_at', ?)",
                 (__import__("datetime").datetime.now().isoformat(timespec="seconds"),))
    conn.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('kcbpspd', ?)", (str(xml_p),))
    conn.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('sysfunc', ?)", (str(sql_p),))
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM funcids").fetchone()[0]
    fn = conn.execute("SELECT COUNT(*) FROM funcids WHERE func_name!=''").fetchone()[0]
    conn.close()
    print(f"\n✅ 功能号索引已构建: {db}")
    print(f"   收录功能号 {n} 个（含功能名 {fn} 个），耗时 {w} 行写入。")


if __name__ == "__main__":
    main()
