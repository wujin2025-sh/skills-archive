#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库表/表字段极速查询 —— SQL Server 版（pymssql 直连，凭据不落盘）

运行环境：$HOME/.workbuddy/binaries/python/versions/3.13.12/bin/python3（自带 pymssql 2.4.6）
⚠️ /usr/local/bin/python3（Homebrew 3.14）无 pymssql 且受 PEP 668 拦截无法安装，勿用。
⚠️ TDS 版本必须 tds_version='7.0'（7.1~8.0 实测报 20002 DB-Lib 连接失败，仅 7.0 可用）。
⚠️ pymysql 不能连 SQL Server（协议不同：TCP 可达但报 Connection reset by peer）。

与 query_schema.py (MySQL/OceanBase) 功能对齐：列库 / 列表 / 表字段 / 关键字搜索 / 数据样例。
SQL Server 差异：
  - information_schema / sys 视图**仅反映连接当前库**：跨库须三段限定 [db].INFORMATION_SCHEMA.COLUMNS
  - LIMIT n → SELECT TOP n；反引号 → [schema].[table]；占位符 %s（pymssql 同款）
  - rdonly 账号仅 run 库可访问（AT/his/sql 报 916 无权限），搜索类操作即 run 库范围

典型用法：
  PY="$HOME/.workbuddy/binaries/python/versions/3.13.12/bin/python3"
  S=/Users/wujin/.chat/skills/数据库查询/scripts/query_sqlserver.py
  DB_PASSWORD='***' $PY $S --profile jzjy_sit --list-databases        # 列实例数据库
  DB_PASSWORD='***' $PY $S --profile jzjy_sit --database run --list-tables   # 列 run 库全部表
  DB_PASSWORD='***' $PY $S --profile jzjy_sit --table orderrec        # 查字段+1条样例
  DB_PASSWORD='***' $PY $S --profile jzjy_sit --table run.dbo.orderrec --no-sample
  DB_PASSWORD='***' $PY $S --profile jzjy_sit --search-table order    # 表名模糊
  DB_PASSWORD='***' $PY $S --profile jzjy_sit --search-field remark   # 字段名模糊（当前库全表）
  # 降噪与摘要（run 库大，搜索默认过滤备份/回灌/临时表）：
  DB_PASSWORD='***' $PY $S --profile jzjy_sit --search-field err      # 默认过滤 bcp_/SYNC_/_bak 等噪音表
  DB_PASSWORD='***' $PY $S --profile jzjy_sit --search-field err --no-exclude-backup  # 看全部（含备份表）
  DB_PASSWORD='***' $PY $S --profile jzjy_sit --search-field err --full               # 不截断
  DB_PASSWORD='***' $PY $S --profile jzjy_sit --search-field err --max-rows 500       # 调大摘要阈值
  # 参数中心后台 SIT（SQL Server，账号 jygl_zd，业务库待实测）：
  DB_PASSWORD='***' $PY $S --profile cszx_sit --list-databases        # 列实例数据库（探测可访问范围）
  # 8) 字段值字典查询（jzjy 集中交易 / cszx 参数中心，run.dbo.dictindex + dictvalue 表）
  DB_PASSWORD='***' $PY $S --profile jzjy_sit --dict-list              # 列出所有字典分类（dictitem + itemname）
  DB_PASSWORD='***' $PY $S --profile jzjy_sit --dict Bjyqx             # 精确查 dictitem=Bjyqx 的字典条目
  DB_PASSWORD='***' $PY $S --profile jzjy_sit --dict Djsbz             # 精确查 dictitem=Djsbz 的字典条目
  DB_PASSWORD='***' $PY $S --profile jzjy_sit --dict 买卖              # 模糊匹配 itemname（中文分类名）
"""

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter

try:
    import pymssql
except ImportError:
    sys.exit("❌ pymssql 未安装。请用 ~/.workbuddy/binaries/python/versions/3.13.12/bin/python3 运行（自带 pymssql 2.4.6）。")

# 预置实例 profile（半公开连接信息；密码一律不在此定义，运行时提供）
PROFILES = {
    "jzjy_sit": dict(host="10.187.160.91", port=1433, user="rdonly", database="run",
                     label="集中交易 SIT (SQL Server 2014, run 库, rdonly 仅 run 库可访问)"),
    "cszx_sit": dict(host="10.187.64.75", port=1433, user="jygl_zd", database="run",
                     label="参数中心后台 SIT (SQL Server, 实例 5 库中仅 run 可读(实测), 参数业务库)"),
}

# --sql 安全限制：仅允许只读查询
SQL_READ_ONLY = re.compile(r'^\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN|WITH)\b', re.IGNORECASE)


def _load_cred_file(profile):
    """从 .db_credentials 文件加载密码（仅当环境变量 DB_PASSWORD 未设置时）。
    文件格式：DB_PASS_<PROFILE>=密码（profile 名转大写、非字母数字替换为下划线）。
    文件权限必须为 600，仅用户可读。"""
    if not profile:
        return None
    cred_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".db_credentials")
    if not os.path.isfile(cred_path):
        return None
    st = os.stat(cred_path)
    if st.st_mode & 0o077:
        print(f"⚠️  凭据文件 {cred_path} 权限为 {oct(st.st_mode & 0o777)}，建议 chmod 600", file=sys.stderr)
    key = "DB_PASS_" + re.sub(r'[^A-Za-z0-9]', '_', profile.upper())
    try:
        with open(cred_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                if k == key:
                    v = v.strip().strip("'").strip('"')
                    return v if v else None
    except OSError:
        pass
    return None


def parse_args():
    p = argparse.ArgumentParser(description="SQL Server 表/表字段极速查询（pymssql 直连，凭据不落盘）")
    p.add_argument("--profile", help="预置实例，如 jzjy_sit（内含 host/port/user/database，不含密码）")
    p.add_argument("--host", help="主机（缺省用 profile 或 127.0.0.1）")
    p.add_argument("--port", type=int, help="端口（缺省用 profile 或 1433）")
    p.add_argument("--user", help="用户名（缺省用 profile 或 sa）")
    p.add_argument("--password", help="密码（不推荐；优先环境变量 DB_PASSWORD 或交互输入）")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--list-databases", action="store_true", help="列出全部数据库")
    g.add_argument("--list-tables", action="store_true", help="列出 --database 下全部表")
    g.add_argument("--table", help="查表字段，支持 [库].[schema.]表 或纯表名（当前连接库）")
    g.add_argument("--search-table", help="按关键字模糊搜表名（当前连接库）")
    g.add_argument("--search-field", help="按关键字模糊搜字段名（当前连接库全表）")
    g.add_argument("--dict-list", action="store_true", help="列出所有字典分类（dictindex）")
    g.add_argument("--dict", help="查指定分类的字典条目（dictvalue WHERE dictitem），支持模糊匹配 dictitem 和 itemname")
    g.add_argument("--sql", help="执行只读 SQL（仅 SELECT/SHOW/DESCRIBE/EXPLAIN/WITH；结果按 Markdown 表格输出）")
    p.add_argument("--database", help="限定数据库（缺省用 profile 的 database，即 run）")
    p.add_argument("--dict-database", default=None,
                   help="字典表所在数据库（默认 run；配合 --dict/--dict-list）")
    p.add_argument("--match-comment", action="store_true",
                   help="与 --search-field 连用：同时匹配列注释（sys.extended_properties）")
    p.add_argument("--sample", type=int, default=3,
                   help="--table 精确查询后附加数据样例条数（默认 3）")
    p.add_argument("--no-sample", action="store_true", help="关闭数据样例输出")
    p.add_argument("--exclude-backup", action="store_true", default=True,
                   help="搜索/列表时过滤备份/回灌/临时表（bcp_/SYNC_ 前缀、_bak/_backup/_temp/_zj/_wq/_yq/_upd/纯数字日期后缀；默认开）")
    p.add_argument("--no-exclude-backup", action="store_true",
                   help="关闭备份表过滤（--exclude-backup 默认已开，用于看全部/排查）")
    p.add_argument("--max-rows", type=int, default=100,
                   help="搜索结果超过此行数进入摘要模式（按表分组 TOP20 + 明细截断 + 完整结果落盘 /tmp；默认 100）")
    p.add_argument("--full", action="store_true",
                   help="搜索结果不截断（关闭摘要模式，输出全部明细）")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    return p.parse_args()


def resolve_conn(args):
    prof = PROFILES.get(args.profile, {}) if args.profile else {}
    host = args.host or prof.get("host") or "127.0.0.1"
    port = args.port or prof.get("port") or 1433
    user = args.user or prof.get("user") or "sa"
    database = args.database or prof.get("database")
    # 密码优先级：环境变量 DB_PASSWORD > --password 参数 > .db_credentials 文件 > 交互输入
    password = os.environ.get("DB_PASSWORD") or args.password
    if not password:
        password = _load_cred_file(args.profile)
    if not password:
        try:
            import getpass
            password = getpass.getpass(f"请输入用户 {user}@{host}:{port} 的数据库密码（不回显、不落盘）: ")
        except Exception:
            sys.exit("❌ 未提供密码。请设环境变量 DB_PASSWORD 或在 .db_credentials 中配置。")
    return dict(host=host, port=port, user=user, password=password, database=database)


def connect(cfg):
    try:
        return pymssql.connect(
            server=cfg["host"], port=cfg["port"], user=cfg["user"],
            password=cfg["password"], database=cfg.get("database") or "master",
            login_timeout=10, tds_version="7.0")
    except pymssql.DatabaseError as e:
        msg = str(e)
        if "916" in msg or "cannot open database" in msg.lower():
            sys.exit(f"❌ 916 无权限访问该库（rdonly 仅 run 库可读），请检查数据库名。原始错误：{e}")
        sys.exit(f"❌ 连接失败：{e}")


def q(cur, sql, params=None):
    cur.execute(sql, params or ())
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def ident(s):
    """SQL Server 方括号标识符包裹"""
    return "[" + str(s).replace("]", "]]") + "]"


def fmt_ic_view(db):
    """返回 INFORMATION_SCHEMA 视图前缀：跨库用 [db].INFORMATION_SCHEMA，当前库用 INFORMATION_SCHEMA"""
    return f"{ident(db)}.INFORMATION_SCHEMA" if db else "INFORMATION_SCHEMA"


def fmt_len(r):
    t = (r.get("DATA_TYPE") or "").lower()
    if t in ("char", "varchar", "nchar", "nvarchar", "binary", "varbinary"):
        return str(r.get("CHARACTER_MAXIMUM_LENGTH") or r.get("CHAR_LEN") or "")
    if t in ("decimal", "numeric"):
        np, ns = r.get("NUMERIC_PRECISION"), r.get("NUMERIC_SCALE")
        return f"{np},{ns}" if np is not None else ""
    return ""


def fmt_val(v):
    if v is None:
        return ""
    if isinstance(v, (bytes, bytearray)):
        try:
            return v.decode("utf-8", "replace")
        except Exception:
            return repr(v)
    s = str(v)
    return s if len(s) <= 120 else s[:120] + "…"


# 备份/回灌/临时表识别（run 库 10593 张表含大量 bcp_/SYNC_/备份表，搜索时默认过滤降噪）
BACKUP_PREFIXES = ("bcp_", "sync_")
BACKUP_SUBSTR = ("_bak", "_backup", "_temp", "_zj", "_wq", "_yq", "_upd")


def is_backup_table(name):
    """是否备份/回灌/临时表：bcp_/SYNC_ 前缀、_bak 等子串、纯数字日期/批次后缀"""
    n = str(name or "").lower()
    if not n:
        return True
    if n.startswith(BACKUP_PREFIXES):
        return True
    if any(m in n for m in BACKUP_SUBSTR):
        return True
    if re.search(r"_\d{3,8}$", n):
        return True
    return False


def summarize_hits(args, total, counter, detail_lines, dump_lines, kind):
    """命中超过 --max-rows：分组摘要 + 明细截断 + 完整结果落盘 /tmp（--full 时不进入本模式）"""
    lines = [f"⚠️ 共 {total} 条，超过显示上限 {args.max_rows}（--full 查看全部 / --max-rows N 调阈值）："]
    if counter:
        top = counter.most_common(20)
        lines.append(f"\n📊 按表分组 TOP{min(20, len(top))}：")
        lines.append("| 表 | 命中数 |")
        lines.append("| --- | --- |")
        lines += [f"| {t} | {c} |" for t, c in top]
    lines.append(f"\n明细前 {args.max_rows} 条：")
    lines += detail_lines
    fd, path = tempfile.mkstemp(prefix=f"dbq_search_{kind}_", suffix=".tsv", dir="/tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(dump_lines) + "\n")
    lines.append(f"\n💾 完整 {total} 条已落盘：`{path}`（可 grep/导入二次加工）")
    return lines


def main():
    args = parse_args()
    cfg = resolve_conn(args)
    conn = connect(cfg)
    sample_payload = None
    try:
        with conn.cursor() as cur:
            out = []
            if args.list_databases:
                rows = q(cur, "SELECT name FROM sys.databases WHERE database_id > 4 ORDER BY name")
                out = [f"实例 {cfg['user']}@{cfg['host']}:{cfg['port']} 共 {len(rows)} 个库（rdonly 仅 run 库可读）："]
                out += [f"- {r['name']}" for r in rows]
            elif args.list_tables:
                db = args.database or cfg["database"] or "run"
                rows = q(cur,
                         f"SELECT name, create_date FROM {ident(db)}.sys.tables "
                         "WHERE is_ms_shipped=0 ORDER BY name")
                exclude = args.exclude_backup and not args.no_exclude_backup
                if exclude:
                    rows = [r for r in rows if not is_backup_table(r["name"])]
                out = [f"{db} 库共 {len(rows)} 张表（rdonly 仅对本库可读"
                       + ("，已过滤备份/回灌/临时表，--no-exclude-backup 查看全部）" if exclude else "）：")]
                out.append("| 表名 | 创建时间 |")
                out.append("| --- | --- |")
                out += [f"| {r['name']} | {r['create_date']} |" for r in rows]
            elif args.table:
                name = args.table.strip()
                db = schema = tbl = None
                parts = [x.strip() for x in name.split(".")]
                if len(parts) == 3:
                    db, schema, tbl = parts
                elif len(parts) == 2:
                    db, tbl = parts
                    schema = "dbo"
                else:
                    tbl = parts[0]
                    db = cfg.get("database") or "run"
                ic = fmt_ic_view(db)
                if schema:
                    where = "c.TABLE_SCHEMA=%s AND c.TABLE_NAME=%s"
                    params = (schema, tbl)
                else:
                    where = "c.TABLE_NAME=%s"
                    params = (tbl,)
                rows = q(cur, f"""SELECT c.TABLE_SCHEMA, c.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE,
                                        c.CHARACTER_MAXIMUM_LENGTH, c.NUMERIC_PRECISION, c.NUMERIC_SCALE,
                                        c.IS_NULLABLE, c.ORDINAL_POSITION,
                                        CAST(ep.value AS nvarchar(4000)) AS [COMMENT]
                                 FROM {ic}.COLUMNS c
                                 LEFT JOIN sys.extended_properties ep
                                   ON ep.major_id=OBJECT_ID(c.TABLE_SCHEMA+'.'+c.TABLE_NAME)
                                  AND ep.minor_id=c.ORDINAL_POSITION
                                  AND ep.name='MS_Description'
                                 WHERE {where} ORDER BY c.ORDINAL_POSITION""", params)
                if not rows:
                    sys.exit(f"❌ 未找到表 {name}（当前连接库={db}；可试 --search-table {tbl} 模糊搜表名）")
                # 主键列集合
                pk = set()
                try:
                    pkrows = q(cur, f"""SELECT kcu.COLUMN_NAME FROM {ic}.KEY_COLUMN_USAGE kcu
                                        JOIN {ic}.TABLE_CONSTRAINTS tc
                                          ON kcu.CONSTRAINT_NAME=tc.CONSTRAINT_NAME
                                         AND kcu.TABLE_NAME=tc.TABLE_NAME
                                        WHERE kcu.TABLE_SCHEMA=%s AND kcu.TABLE_NAME=%s
                                          AND tc.CONSTRAINT_TYPE='PRIMARY KEY'""", (schema or rows[0]["TABLE_SCHEMA"], tbl))
                    pk = {r["COLUMN_NAME"] for r in pkrows}
                except Exception:
                    pass
                shown_dbs = sorted({r["TABLE_SCHEMA"] for r in rows})
                for sch in shown_dbs:
                    sub = [r for r in rows if r["TABLE_SCHEMA"] == sch]
                    out.append(f"{db}.{sch}.{sub[0]['TABLE_NAME']} ({len(sub)} 字段)"
                               + (f"，主键={','.join(sorted(pk))}" if pk else ""))
                    out.append("| # | 字段 | 说明 | 类型 | 长度/精度 | 允许空 |")
                    out.append("| --- | --- | --- | --- | --- | --- |")
                    for r in sub:
                        out.append(f"| {r['ORDINAL_POSITION']} | {r['COLUMN_NAME']} | {r.get('COMMENT') or ''} | "
                                   f"{r['DATA_TYPE']} | {fmt_len(r)} | {r['IS_NULLABLE']} |")
                if not args.no_sample:
                    n = max(1, int(args.sample))
                    sch0 = rows[0]["TABLE_SCHEMA"]
                    try:
                        srows = q(cur, f"SELECT TOP {n} * FROM {ident(db)}.{ident(sch0)}.{ident(tbl)}")
                        sample_payload = [dict(r) for r in srows] if srows else []
                    except pymssql.DatabaseError:
                        sample_payload = None
            elif args.search_table:
                kw = f"%{args.search_table}%"
                db = cfg.get("database") or "run"
                rows = q(cur, f"SELECT name FROM {ident(db)}.sys.tables "
                              "WHERE is_ms_shipped=0 AND name LIKE %s ORDER BY name", (kw,))
                exclude = args.exclude_backup and not args.no_exclude_backup
                if exclude:
                    rows = [r for r in rows if not is_backup_table(r["name"])]
                total = len(rows)
                out = [f"匹配表名 {args.search_table!r} 共 {total} 张（{db} 库"
                       + ("，已过滤备份/回灌/临时表，--no-exclude-backup 查看全部）" if exclude else "）：")]
                if total > args.max_rows and not args.full:
                    out += summarize_hits(args, total, None,
                                          [f"- {r['name']}" for r in rows[: args.max_rows]],
                                          [f"{r['name']}" for r in rows], "table")
                else:
                    out += [f"- {r['name']}" for r in rows]
            elif args.search_field:
                kw = f"%{args.search_field}%"
                db = cfg.get("database") or "run"
                ic = fmt_ic_view(db)
                if args.match_comment:
                    rows = q(cur, f"""SELECT c.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH,
                                             c.NUMERIC_PRECISION, c.NUMERIC_SCALE, ep.value AS [COMMENT]
                                      FROM {ic}.COLUMNS c
                                      LEFT JOIN {ident(db)}.sys.extended_properties ep
                                        ON ep.major_id = OBJECT_ID(c.TABLE_SCHEMA + '.' + c.TABLE_NAME)
                                       AND ep.minor_id = c.ORDINAL_POSITION AND ep.name='MS_Description'
                                      WHERE c.COLUMN_NAME LIKE %s OR ep.value LIKE %s
                                      ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION""", (kw, kw))
                    tag = "字段名或字段注释"
                else:
                    rows = q(cur, f"""SELECT c.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH,
                                             c.NUMERIC_PRECISION, c.NUMERIC_SCALE
                                      FROM {ic}.COLUMNS c WHERE c.COLUMN_NAME LIKE %s
                                      ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION""", (kw,))
                    tag = "字段名"
                exclude = args.exclude_backup and not args.no_exclude_backup
                if exclude:
                    rows = [r for r in rows if not is_backup_table(r["TABLE_NAME"])]
                total = len(rows)
                out = [f"匹配{tag} {args.search_field!r} 共 {total} 个字段（{db} 库"
                       + ("，已过滤备份/回灌/临时表，--no-exclude-backup 查看全部）" if exclude else "）：")]
                if rows:
                    header = "| 表 | 字段 | 说明 | 类型 | 长度/精度 |"
                    if total > args.max_rows and not args.full:
                        counter = Counter(r["TABLE_NAME"] for r in rows)
                        detail = [header, "| --- | --- | --- | --- | --- |"]
                        detail += [f"| {r['TABLE_NAME']} | {r['COLUMN_NAME']} | {r.get('COMMENT') or ''} | "
                                   f"{r['DATA_TYPE']} | {fmt_len(r)} |"
                                   for r in rows[: args.max_rows]]
                        dump = [f"{r['TABLE_NAME']}\t{r['COLUMN_NAME']}\t{r.get('COMMENT') or ''}\t"
                                f"{r['DATA_TYPE']}\t{fmt_len(r)}" for r in rows]
                        out += summarize_hits(args, total, counter, detail, dump, "field")
                    else:
                        out.append(header)
                        out.append("| --- | --- | --- | --- | --- |")
                        for r in rows:
                            out.append(f"| {r['TABLE_NAME']} | {r['COLUMN_NAME']} | {r.get('COMMENT') or ''} | "
                                       f"{r['DATA_TYPE']} | {fmt_len(r)} |")
            elif args.dict_list or args.dict:
                # ── 字典查询（jzjy 集中交易 / cszx 参数中心）──
                # 字典表结构：dictindex(dictitem, itemname) + dictvalue(dictitem, subitem, subitemname)
                # dictitem 为字符串（如 'Bjyqx'），与 jzqs 的数字 dictitem 不同
                dict_db = args.dict_database or cfg.get("database") or "run"
                # 检测字典表是否存在
                has_dictindex = bool(q(cur, f"SELECT name FROM {ident(dict_db)}.sys.tables WHERE name='dictindex'"))
                has_dictvalue = bool(q(cur, f"SELECT name FROM {ident(dict_db)}.sys.tables WHERE name='dictvalue'"))
                if not has_dictindex and not has_dictvalue:
                    sys.exit(f"❌ 库 {dict_db} 中未找到 dictindex/dictvalue 表（用 --dict-database 指定字典库）")
                if args.dict_list:
                    if has_dictindex:
                        rows = q(cur, f"SELECT DISTINCT dictitem, itemname FROM {ident(dict_db)}.dbo.dictindex ORDER BY dictitem")
                    else:
                        rows = q(cur, f"SELECT DISTINCT dictitem, CAST('' AS varchar(128)) AS itemname FROM {ident(dict_db)}.dbo.dictvalue ORDER BY dictitem")
                    out = [f"📚 字典分类（{dict_db}.dbo.dictindex）共 {len(rows)} 个："]
                    out.append("| dictitem | itemname |")
                    out.append("| --- | --- |")
                    out += [f"| {r['dictitem']} | {r['itemname'] or ''} |" for r in rows]
                    out.append(f"\n💡 用法：--dict <dictitem> 查字典条目，如 --dict Bjyqx")
                elif args.dict:
                    cat = args.dict.strip()
                    out = []
                    # 1) 先精确匹配 dictitem
                    rows = q(cur,
                             f"SELECT DISTINCT dictitem, subitem, subitemname FROM {ident(dict_db)}.dbo.dictvalue "
                             "WHERE dictitem=%s ORDER BY subitem", (cat,))
                    if not rows:
                        # 2) 模糊匹配 dictitem
                        rows = q(cur,
                                 f"SELECT DISTINCT dictitem, subitem, subitemname FROM {ident(dict_db)}.dbo.dictvalue "
                                 "WHERE dictitem LIKE %s ORDER BY dictitem, subitem", (f"%{cat}%",))
                        if not rows:
                            # 3) 模糊匹配 itemname（中文分类名）
                            idx_rows = q(cur,
                                         f"SELECT DISTINCT dictitem, itemname FROM {ident(dict_db)}.dbo.dictindex "
                                         "WHERE itemname LIKE %s ORDER BY dictitem", (f"%{cat}%",))
                            if not idx_rows:
                                sys.exit(f"❌ 字典分类 {cat!r} 未找到（--dict-list 查看所有分类）")
                            out = [f"⚠️ {cat!r} 在 itemname 中匹配到 {len(idx_rows)} 个分类："]
                            out.append("| dictitem | itemname |")
                            out.append("| --- | --- |")
                            out += [f"| {r['dictitem']} | {r['itemname'] or ''} |" for r in idx_rows]
                            out.append(f"\n💡 请用具体 dictitem 重试，如 --dict {idx_rows[0]['dictitem']}")
                            cat = idx_rows[0]["dictitem"]
                            rows = q(cur,
                                     f"SELECT DISTINCT dictitem, subitem, subitemname FROM {ident(dict_db)}.dbo.dictvalue "
                                     "WHERE dictitem=%s ORDER BY subitem", (cat,))
                    if rows:
                        cat_name = rows[0]["dictitem"]
                        item_name = ""
                        if has_dictindex:
                            idx = q(cur, f"SELECT DISTINCT itemname FROM {ident(dict_db)}.dbo.dictindex WHERE dictitem=%s", (cat_name,))
                            if idx:
                                item_name = idx[0].get("itemname") or ""
                        header = f"📖 字典 {cat_name}"
                        if item_name:
                            header += f"（{item_name}）"
                        header += f"（{dict_db}.dbo.dictvalue）共 {len(rows)} 条："
                        out.insert(0, header)
                        out.append("| dictitem | subitem | subitemname |")
                        out.append("| --- | --- | --- |")
                        out += [f"| {r['dictitem']} | {r['subitem']} | {r['subitemname'] or ''} |" for r in rows]
            elif args.sql:
                sql_text = args.sql.strip()
                if not SQL_READ_ONLY.match(sql_text):
                    sys.exit("❌ --sql 仅允许只读查询（SELECT/SHOW/DESCRIBE/EXPLAIN/WITH）。")
                cur.execute(sql_text)
                cols = [d[0] for d in cur.description] if cur.description else []
                srows = cur.fetchall()
                out = [f"📋 SQL 查询返回 {len(srows)} 行" + (f"（{len(cols)} 列）" if cols else "") + "："]
                if cols:
                    out.append("| " + " | ".join(cols) + " |")
                    out.append("| " + " | ".join(["---"] * len(cols)) + " |")
                    for row in srows[:200]:
                        out.append("| " + " | ".join(fmt_val(v) for v in row) + " |")
                    if len(srows) > 200:
                        out.append(f"\n⚠️ 仅显示前 200 行（共 {len(srows)} 行）")
                elif not srows:
                    out.append("（查询无结果）")
            if args.json and not args.list_databases and not args.list_tables:
                payload = {"ok": True, "data": out}
                if sample_payload is not None:
                    payload["sample"] = sample_payload
                print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
            else:
                if sample_payload is not None:
                    if sample_payload:
                        out.append(f"\n📊 数据样例（{len(sample_payload)} 条）：")
                        for i, r in enumerate(sample_payload, 1):
                            if len(sample_payload) > 1:
                                out.append(f"\n**第 {i} 条**")
                            out.append("| 字段 | 值 |")
                            out.append("| --- | --- |")
                            out += [f"| {k} | {fmt_val(v)} |" for k, v in r.items()]
                    else:
                        out.append("\n（该表暂无数据）")
                print("\n".join(out))
    except pymssql.DatabaseError as e:
        msg = str(e)
        if "916" in msg:
            sys.exit("❌ 916 无权限访问该库（rdonly 仅 run 库可读）。")
        sys.exit(f"❌ 查询失败：{e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
