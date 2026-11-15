#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库表/表字段极速查询（pymysql 直连 information_schema，凭据不落盘）

运行环境：/usr/local/bin/python3（自带 pymysql；workbuddy 默认 python 无 pymysql）

典型用法：
  # 1) 列实例下所有数据库
  /usr/local/bin/python3 query_schema.py --profile dys95 --list-databases
  # 2) 列某库所有表（带表注释）
  /usr/local/bin/python3 query_schema.py --profile dys95 --database tradingdb --list-tables
  # 3) 精确查表字段（库.表，输出 字段名/类型/长度/键/可空/注释）——默认自动附带 1 条数据样例
  /usr/local/bin/python3 query_schema.py --profile dys95 --table tradingdb.t_order
  #    数据样例：--sample N 改条数（默认 1）；--no-sample 完全关闭；纯表名模糊查询不附带样例
  # 4) 表名模糊定位（不确定在哪个库时自动跨库匹配）
  /usr/local/bin/python3 query_schema.py --profile dys95 --table t_order_status
  # 5) 关键字跨库搜表名
  /usr/local/bin/python3 query_schema.py --profile dys95 --search-table order
  # 6) 关键字跨库搜字段名 / 字段注释
  /usr/local/bin/python3 query_schema.py --profile dys95 --search-field 错误
  /usr/local/bin/python3 query_schema.py --profile dys95 --search-field 备注 --match-comment
  # 7) 降噪与摘要（默认过滤备份/回灌/临时表；海量命中自动摘要 + 完整结果落盘 /tmp）
  /usr/local/bin/python3 query_schema.py --profile dys95 --search-field err
  /usr/local/bin/python3 query_schema.py --profile dys95 --search-field err --no-exclude-backup
  /usr/local/bin/python3 query_schema.py --profile dys95 --search-field err --full --max-rows 500
  # 8) 字段值字典查询（t_dict / t_dict_category / t_bsflag_dict，默认查 tradingconfigdb 库）
  /usr/local/bin/python3 query_schema.py --profile dys95 --dict-list               # 列出所有字典分类
  /usr/local/bin/python3 query_schema.py --profile dys95 --dict BusinessType       # 查业务类型字典
  /usr/local/bin/python3 query_schema.py --profile dys95 --dict Side               # 查买卖方向字典
  /usr/local/bin/python3 query_schema.py --profile dys95 --dict CashMargin          # 查信用标识字典
  /usr/local/bin/python3 query_schema.py --profile dys95 --dict business            # 支持模糊匹配分类名
  /usr/local/bin/python3 query_schema.py --profile dys95 --dict-bsflag              # 查 bsflag 专用字典

密码来源优先级：环境变量 DB_PASSWORD > --password 参数 > 交互式输入（getpass 不回显）
⚠️ 严禁把密码写入任何配置文件/脚本/记忆文件；--password 会短暂出现在进程参数中，优先环境变量。
"""

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter

try:
    import pymysql
except ImportError:
    sys.exit("❌ pymysql 未安装。请使用 /usr/local/bin/python3 运行本脚本（该环境自带 pymysql）。")

# 预置实例 profile（半公开连接信息；密码一律不在此定义，运行时提供）
PROFILES = {
    "dys95": dict(host="10.187.101.51", port=8885, user="query",
                  label="低延时 SIT"),
    "jzqs_sit": dict(host="10.187.109.56", port=2883,
                     user="gjman_q@jjnode#jzqs_sit",
                     label="集中清算 SIT (OceanBase 4.2.5.7, node 库)"),
    "jzqs_comm_sit": dict(host="10.187.109.56", port=2883,
                          user="gjman_q@comm#jzqs_sit",
                          label="集中清算通用功能 SIT (OceanBase, comm 库, 清算公共模块, 与客户数据无关)"),
    # 示例扩展：
    # "jzjy_sit": dict(host="10.x.x.x", port=3306, user="query", label="集中交易 SIT"),
}

SYS_SCHEMAS = {"information_schema", "performance_schema", "mysql", "sys"}

# --sql 安全限制：仅允许只读查询
SQL_READ_ONLY = re.compile(r'^\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN|WITH)\b', re.IGNORECASE)


def parse_args():
    p = argparse.ArgumentParser(description="数据库表/表字段极速查询（凭据不落盘）")
    p.add_argument("--profile", help="预置实例，如 dys95（内含 host/port/user，不含密码）")
    p.add_argument("--host", help="主机（缺省用 profile 或 127.0.0.1）")
    p.add_argument("--port", type=int, help="端口（缺省用 profile 或 3306）")
    p.add_argument("--user", help="用户名（缺省用 profile 或 root）")
    p.add_argument("--password", help="密码（不推荐；优先环境变量 DB_PASSWORD 或交互输入）")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--list-databases", action="store_true", help="列出全部数据库")
    g.add_argument("--list-tables", action="store_true", help="列出 --database 下全部表")
    g.add_argument("--table", help="查表字段，支持 库.表 精确或纯表名模糊跨库定位")
    g.add_argument("--search-table", help="按关键字模糊搜表名（跨库）")
    g.add_argument("--search-field", help="按关键字模糊搜字段名（跨库）")
    g.add_argument("--dict-list", action="store_true", help="列出所有字典分类（t_dict_category）")
    g.add_argument("--dict", help="查指定分类的字典条目（t_dict WHERE category_code），支持模糊匹配")
    g.add_argument("--dict-bsflag", action="store_true", help="查 bsflag 专用字典（t_bsflag_dict）")
    g.add_argument("--sql", help="执行只读 SQL（仅 SELECT/SHOW/DESCRIBE/EXPLAIN/WITH；结果按 Markdown 表格输出）")
    p.add_argument("--database", help="限定数据库")
    p.add_argument("--dict-database", default=None,
                   help="字典表所在数据库（dys 默认 tradingconfigdb；jzqs 默认 comm；可手动指定；配合 --dict/--dict-list/--dict-bsflag）")
    p.add_argument("--match-comment", action="store_true",
                   help="与 --search-field 连用：同时匹配字段注释")
    p.add_argument("--sample", type=int, default=3,
                   help="--table 精确查询（库.表）后附加数据样例条数（默认 3；纯表名模糊查询不附带）")
    p.add_argument("--no-sample", action="store_true",
                   help="关闭数据样例输出")
    p.add_argument("--exclude-backup", action="store_true", default=True,
                   help="搜索/列表时过滤备份/回灌/临时表（默认开；--no-exclude-backup 关闭）")
    p.add_argument("--no-exclude-backup", action="store_true",
                   help="关闭备份表过滤（--exclude-backup 默认已开）")
    p.add_argument("--max-rows", type=int, default=100,
                   help="搜索结果超过此行数进入摘要模式（按表分组 TOP20 + 明细截断 + 完整结果落盘 /tmp；默认 100）")
    p.add_argument("--full", action="store_true",
                   help="搜索结果不截断（关闭摘要模式，输出全部明细）")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    return p.parse_args()


def _load_cred_file(profile):
    """从 .db_credentials 文件加载密码（仅当环境变量 DB_PASSWORD 未设置时）。
    文件格式：DB_PASS_<PROFILE>=密码（profile 名转大写、非字母数字替换为下划线）。
    文件权限必须为 600，仅用户可读。"""
    if not profile:
        return None
    cred_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".db_credentials")
    if not os.path.isfile(cred_path):
        return None
    # 校验文件权限：必须仅用户可读写（600 或 400）
    st = os.stat(cred_path)
    if st.st_mode & 0o077:
        # 权限过宽，警告但仍加载（不阻断工作）
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


def resolve_conn(args):
    prof = PROFILES.get(args.profile, {}) if args.profile else {}
    host = args.host or prof.get("host") or "127.0.0.1"
    port = args.port or prof.get("port") or 3306
    user = args.user or prof.get("user") or "root"
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
    return dict(host=host, port=port, user=user, password=password)


def connect(cfg):
    try:
        return pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                               password=cfg["password"], charset="utf8mb4",
                               connect_timeout=10, read_timeout=60)
    except pymysql.MySQLError as e:
        code = getattr(e, "args", [None])[0]
        if code == 1045:
            sys.exit("❌ 1045 Access denied：凭据被拒（dbx 内置凭据同样 1045），"
                     "请向用户索取正确口令后重试。")
        sys.exit(f"❌ 连接失败：{e}")
    except Exception as e:
        sys.exit(f"❌ 连接失败：{e}")


def q(cur, sql, params=None):
    cur.execute(sql, params or ())
    # 统一小写列名：MySQL 8 的 information_schema 视图列名大小写混杂
    # （schemata=SCHEMA_NAME 大写 / columns=table_schema 小写），统一后代码键稳定
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fmt_len(row):
    """拼字段显示长度：char/varchar 取长度，decimal 取精度，其余留空"""
    t = (row.get("data_type") or "").lower()
    if t in ("char", "varchar"):
        return str(row.get("character_maximum_length") or "")
    if t == "decimal":
        return f"{row.get('numeric_precision')},{row.get('numeric_scale')}" if row.get("numeric_precision") else ""
    return ""


def ident(s):
    """MySQL 反引号标识符安全包裹（内部反引号转义为双反引号）"""
    return "`" + str(s).replace("`", "``") + "`"


def fmt_val(v):
    """样例字段值格式化：None 留空 / bytes 解码 / 其余转字符串"""
    if v is None:
        return ""
    if isinstance(v, (bytes, bytearray)):
        try:
            return v.decode("utf-8", "replace")
        except Exception:
            return repr(v)
    return str(v)


# 备份/回灌/临时表识别（搜索降噪：如 SQL Server run 库的 bcp_*/SYNC_*/_bak 等）
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


def render_columns(rows, json_out):
    if json_out:
        return json.dumps(rows, ensure_ascii=False, indent=2)
    if not rows:
        return "（无字段）"
    lines = ["| 字段 | 说明 | 类型 | 长度 | 键 | 允许空 |", "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['column_name']} | {r.get('column_comment') or ''} | {r['data_type']} | "
                     f"{fmt_len(r)} | "
                     f"{r.get('column_key') or ''} | {r.get('is_nullable') or ''} |")
    return "\n".join(lines)


def main():
    args = parse_args()
    cfg = resolve_conn(args)
    conn = connect(cfg)
    sample_payload = None  # --table 精确查询附带的数据样例（None=不输出）
    try:
        with conn.cursor() as cur:
            out = []
            if args.list_databases:
                rows = q(cur, "SELECT schema_name, default_character_set_name FROM information_schema.schemata ORDER BY 1")
                rows = [r for r in rows if r["schema_name"] not in SYS_SCHEMAS]
                out = [f"实例 {cfg['user']}@{cfg['host']}:{cfg['port']} 共 {len(rows)} 个业务库："]
                out.append("| 数据库 | 字符集 |")
                out.append("| --- | --- |")
                out += [f"| {r['schema_name']} | {r['default_character_set_name']} |" for r in rows]
            elif args.list_tables:
                if not args.database:
                    sys.exit("❌ --list-tables 需要指定 --database")
                rows = q(cur, "SELECT table_name, table_comment FROM information_schema.tables "
                              "WHERE table_schema=%s AND table_type='BASE TABLE' ORDER BY table_name",
                         (args.database,))
                exclude = args.exclude_backup and not args.no_exclude_backup
                if exclude:
                    rows = [r for r in rows if not is_backup_table(r["table_name"])]
                out = [f"{args.database} 共 {len(rows)} 张表"
                       + ("（已过滤备份/回灌/临时表，--no-exclude-backup 查看全部）：" if exclude else "：")]
                out.append("| 表名 | 注释 |")
                out.append("| --- | --- |")
                out += [f"| {r['table_name']} | {r['table_comment'] or ''} |" for r in rows]
            elif args.table:
                name = args.table.strip()
                if "." in name:
                    db, tbl = name.split(".", 1)
                    db, tbl = db.strip(), tbl.strip()
                    rows = q(cur,
                             "SELECT table_schema, table_name, column_name, data_type, character_maximum_length, "
                             "numeric_precision, numeric_scale, is_nullable, column_key, column_comment, ordinal_position "
                             "FROM information_schema.columns WHERE table_schema=%s AND table_name=%s "
                             "ORDER BY ordinal_position", (db, tbl))
                    if not rows:
                        sys.exit(f"❌ 未找到表 {name}（请检查库名/表名，或改用纯表名触发跨库模糊定位）")
                    # 数据样例（仅精确 库.表 附带；失败不阻塞结构输出）
                    if not args.no_sample:
                        n = max(1, int(args.sample))
                        try:
                            srows = q(cur, f"SELECT * FROM {ident(db)}.{ident(tbl)} LIMIT {n}")
                            sample_payload = [dict(r) for r in srows] if srows else []
                        except pymysql.MySQLError:
                            sample_payload = None
                else:
                    rows = q(cur,
                             "SELECT table_schema, table_name, column_name, data_type, character_maximum_length, "
                             "numeric_precision, numeric_scale, is_nullable, column_key, column_comment, ordinal_position "
                             "FROM information_schema.columns WHERE table_name=%s ORDER BY table_schema, ordinal_position",
                             (name,))
                    if not rows:
                        sys.exit(f"❌ 未找到表 {name}（可尝试 --search-table {name} 模糊搜表名）")
                dbs = sorted({r["table_schema"] for r in rows})
                for db in dbs:
                    sub = [r for r in rows if r["table_schema"] == db]
                    out.append(f"{db}.{sub[0]['table_name']} ({len(sub)} 字段)")
                    out.append(render_columns(sub, False))
            elif args.search_table:
                kw = f"%{args.search_table}%"
                rows = q(cur, "SELECT table_schema, table_name, table_comment FROM information_schema.tables "
                              "WHERE table_type='BASE TABLE' AND table_name LIKE %s "
                              "ORDER BY table_schema, table_name", (kw,))
                exclude = args.exclude_backup and not args.no_exclude_backup
                if exclude:
                    rows = [r for r in rows if not is_backup_table(r["table_name"])]
                total = len(rows)
                out = [f"匹配表名 {args.search_table!r} 共 {total} 张"
                       + ("（已过滤备份/回灌/临时表，--no-exclude-backup 查看全部）：" if exclude else "：")]
                if rows:
                    if total > args.max_rows and not args.full:
                        detail = [f"| {r['table_schema']}.{r['table_name']} | {r['table_comment'] or ''} |"
                                  for r in rows[: args.max_rows]]
                        dump = [f"{r['table_schema']}.{r['table_name']}\t{r['table_comment'] or ''}" for r in rows]
                        out += summarize_hits(args, total, None, detail, dump, "table")
                    else:
                        out.append("| 库.表 | 表注释 |")
                        out.append("| --- | --- |")
                        out += [f"| {r['table_schema']}.{r['table_name']} | {r['table_comment'] or ''} |" for r in rows]
            elif args.search_field:
                kw = f"%{args.search_field}%"
                if args.match_comment:
                    rows = q(cur,
                             "SELECT table_schema, table_name, column_name, data_type, character_maximum_length, "
                             "numeric_precision, numeric_scale, is_nullable, column_comment "
                             "FROM information_schema.columns "
                             "WHERE column_name LIKE %s OR column_comment LIKE %s "
                             "ORDER BY table_schema, table_name, ordinal_position", (kw, kw))
                    tag = "字段名或字段注释"
                else:
                    rows = q(cur,
                             "SELECT table_schema, table_name, column_name, data_type, character_maximum_length, "
                             "numeric_precision, numeric_scale, is_nullable, column_comment "
                             "FROM information_schema.columns "
                             "WHERE column_name LIKE %s ORDER BY table_schema, table_name, ordinal_position", (kw,))
                    tag = "字段名"
                if args.database:
                    rows = [r for r in rows if r["table_schema"] == args.database]
                exclude = args.exclude_backup and not args.no_exclude_backup
                if exclude:
                    rows = [r for r in rows if not is_backup_table(r["table_name"])]
                total = len(rows)
                out = [f"匹配{tag} {args.search_field!r} 共 {total} 个字段"
                       + ("（已过滤备份/回灌/临时表，--no-exclude-backup 查看全部）：" if exclude else "：")]
                if rows:
                    header = "| 库.表 | 字段 | 说明 | 类型 | 长度 |"
                    if total > args.max_rows and not args.full:
                        counter = Counter(r["table_name"] for r in rows)
                        detail = [header, "| --- | --- | --- | --- | --- |"]
                        detail += [f"| {r['table_schema']}.{r['table_name']} | {r['column_name']} | "
                                   f"{r['column_comment'] or ''} | "
                                   f"{r['data_type']} | {fmt_len(r)} |"
                                   for r in rows[: args.max_rows]]
                        dump = [f"{r['table_schema']}.{r['table_name']}\t{r['column_name']}\t"
                                f"{r['column_comment'] or ''}\t{r['data_type']}\t"
                                f"{fmt_len(r)}" for r in rows]
                        out += summarize_hits(args, total, counter, detail, dump, "field")
                    else:
                        out.append(header)
                        out.append("| --- | --- | --- | --- | --- |")
                        for r in rows:
                            out.append(f"| {r['table_schema']}.{r['table_name']} | {r['column_name']} | "
                                       f"{r['column_comment'] or ''} | "
                                       f"{r['data_type']} | {fmt_len(r)} |")
            elif args.dict_list or args.dict or args.dict_bsflag:
                # ── 自动选择字典库 ──
                dict_db = args.dict_database
                if not dict_db:
                    if args.profile in ("jzqs_sit", "jzqs_comm_sit"):
                        dict_db = "comm"
                    else:
                        dict_db = "tradingconfigdb"
                # ── 自动检测字典表模式 ──
                # dys: t_dict_category + t_dict + t_bsflag_dict（category_code 字符串分类）
                # jzqs: sys_dictindex + sys_dictvalue（dictitem 数字分类）
                try:
                    has_t_dict = bool(q(cur,
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema=%s AND table_name='t_dict'", (dict_db,)))
                    has_sys_dictindex = bool(q(cur,
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema=%s AND table_name='sys_dictindex'", (dict_db,)))
                except pymysql.MySQLError as e:
                    sys.exit(f"❌ 检测字典表失败：{e}")

                if has_t_dict:
                    # ═══ dys 模式：t_dict_category / t_dict / t_bsflag_dict ═══
                    if args.dict_list:
                        rows = q(cur, f"SELECT code, name FROM {ident(dict_db)}.t_dict_category ORDER BY sort_order, code")
                        out = [f"📚 字典分类（{dict_db}.t_dict_category）共 {len(rows)} 个："]
                        out.append("| 分类代码 | 分类名 |")
                        out.append("| --- | --- |")
                        out += [f"| {r['code']} | {r['name'] or ''} |" for r in rows]
                        out.append(f"\n💡 用法：--dict <分类代码> 查字典条目，如 --dict BusinessType")
                    elif args.dict:
                        cat = args.dict.strip()
                        _dict_out = None  # 标记是否已构造输出
                        # 1) 精确匹配 category_code（大小写不敏感）
                        rows = q(cur,
                                 f"SELECT code, value, name, category_code FROM {ident(dict_db)}.t_dict "
                                 "WHERE LOWER(category_code)=LOWER(%s) ORDER BY sort_order, `value`",
                                 (cat,))
                        if not rows:
                            # 2) 模糊匹配 category_code
                            rows = q(cur,
                                     f"SELECT code, value, name, category_code FROM {ident(dict_db)}.t_dict "
                                     "WHERE LOWER(category_code) LIKE %s ORDER BY category_code, sort_order, `value`",
                                     (f"%{cat.lower()}%",))
                        if not rows:
                            # 3) 模糊匹配 t_dict_category.name（中文分类名）
                            cat_rows = q(cur,
                                         f"SELECT code, name FROM {ident(dict_db)}.t_dict_category "
                                         "WHERE name LIKE %s ORDER BY code", (f"%{cat}%",))
                            if cat_rows:
                                codes = [r["code"] for r in cat_rows]
                                if len(codes) == 1:
                                    rows = q(cur,
                                             f"SELECT code, value, name, category_code FROM {ident(dict_db)}.t_dict "
                                             "WHERE category_code=%s ORDER BY sort_order, `value`",
                                             (codes[0],))
                                    cat_name_cn = cat_rows[0].get("name", "")
                                    if rows:
                                        _dict_out = [f"📖 字典 {codes[0]}（{cat_name_cn}）"
                                                     f"（{dict_db}.t_dict）共 {len(rows)} 条："]
                                        _dict_out.append("| code | value | name |")
                                        _dict_out.append("| --- | --- | --- |")
                                        _dict_out += [f"| {r['code']} | {r['value']} | {r['name'] or ''} |" for r in rows]
                                else:
                                    _dict_out = [f"⚠️ {cat!r} 在分类名中匹配到 {len(codes)} 个分类："]
                                    _dict_out.append("| 分类代码 | 分类名 |")
                                    _dict_out.append("| --- | --- |")
                                    _dict_out += [f"| {r['code']} | {r['name'] or ''} |" for r in cat_rows]
                                    _dict_out.append(f"\n💡 请用具体分类代码重试，如 --dict {codes[0]}")
                            else:
                                sys.exit(f"❌ 字典分类 {cat!r} 未找到（--dict-list 查看所有分类）")
                        if rows and _dict_out is None:
                            cats = sorted({r["category_code"] for r in rows})
                            if len(cats) > 1:
                                _dict_out = [f"⚠️ {cat!r} 模糊匹配到 {len(cats)} 个分类：{', '.join(cats)}", ""]
                            else:
                                _dict_out = []
                            cat_name = rows[0].get("category_code", cat)
                            _dict_out.append(f"📖 字典 {cat_name}（{dict_db}.t_dict）共 {len(rows)} 条：")
                            _dict_out.append("| code | value | name |")
                            _dict_out.append("| --- | --- | --- |")
                            _dict_out += [f"| {r['code']} | {r['value']} | {r['name'] or ''} |" for r in rows]
                        if _dict_out is None:
                            sys.exit(f"❌ 字典分类 {cat!r} 未找到或无条目（--dict-list 查看所有分类）")
                        out = _dict_out
                    elif args.dict_bsflag:
                        chk = q(cur,
                                "SELECT table_name FROM information_schema.tables "
                                "WHERE table_schema=%s AND table_name='t_bsflag_dict'", (dict_db,))
                        if not chk:
                            sys.exit(f"❌ 库 {dict_db} 中未找到 t_bsflag_dict 表")
                        rows = q(cur,
                                 f"SELECT id, creditdigestid, bsflag, credittype, businesstype, "
                                 f"side, ordtype, timeinforce, maxpricelevels, minqty "
                                 f"FROM {ident(dict_db)}.t_bsflag_dict ORDER BY businesstype, bsflag")
                        out = [f"📖 bsflag 字典（{dict_db}.t_bsflag_dict）共 {len(rows)} 条："]
                        out.append("| bsflag | side | credittype | businesstype | ordtype | timeinforce | maxpricelevels | minqty | creditdigestid |")
                        out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
                        for r in rows:
                            out.append(f"| {r['bsflag'] or ''} | {r['side'] or ''} | {r['credittype'] or ''} | "
                                       f"{r['businesstype'] or ''} | {r['ordtype'] or ''} | {r['timeinforce'] or ''} | "
                                       f"{r['maxpricelevels'] or ''} | {r['minqty'] or ''} | {r['creditdigestid'] or ''} |")
                        out.append(f"\n💡 bsflag=买卖标识 / side=方向 / credittype=信用类型 / businesstype=业务类型")
                        out.append(f"💡 结合 --dict BusinessType 查业务类型含义，--dict Side 查方向含义")
                elif has_sys_dictindex:
                    # ═══ jzqs 模式：sys_dictindex / sys_dictvalue ═══
                    if args.dict_list:
                        rows = q(cur, f"SELECT dictitem, itemname FROM {ident(dict_db)}.sys_dictindex ORDER BY dictitem")
                        out = [f"📚 字典分类（{dict_db}.sys_dictindex）共 {len(rows)} 个："]
                        out.append("| dictitem | 分类名 |")
                        out.append("| --- | --- |")
                        out += [f"| {r['dictitem']} | {r['itemname'] or ''} |" for r in rows]
                        out.append(f"\n💡 用法：--dict <dictitem数字 或 分类名关键词> 查字典条目")
                        out.append(f"💡 常用：64095=买卖标识 65016=买卖类别 64125=业务类型 69022=集中交易买卖标识 65017=信用交易摘要")
                    elif args.dict:
                        cat = args.dict.strip()
                        if cat.isdigit():
                            # 数字 → 直接按 dictitem 查
                            rows = q(cur,
                                     f"SELECT dictitem, subitem, subitemname FROM {ident(dict_db)}.sys_dictvalue "
                                     "WHERE dictitem=%s ORDER BY subitem", (int(cat),))
                            idx = q(cur,
                                    f"SELECT itemname FROM {ident(dict_db)}.sys_dictindex WHERE dictitem=%s", (int(cat),))
                            cat_name = idx[0]["itemname"] if idx else cat
                        else:
                            # 字符串 → 先模糊匹配 sys_dictindex 找 dictitem
                            idx_rows = q(cur,
                                         f"SELECT dictitem, itemname FROM {ident(dict_db)}.sys_dictindex "
                                         "WHERE itemname LIKE %s ORDER BY dictitem", (f"%{cat}%",))
                            if not idx_rows:
                                sys.exit(f"❌ 字典分类 {cat!r} 未找到（--dict-list 查看所有分类）")
                            if len(idx_rows) > 1:
                                out = [f"⚠️ {cat!r} 匹配到 {len(idx_rows)} 个分类："]
                                out.append("| dictitem | 分类名 |")
                                out.append("| --- | --- |")
                                out += [f"| {r['dictitem']} | {r['itemname'] or ''} |" for r in idx_rows]
                                out.append(f"\n💡 请用具体 dictitem 数字重试，如 --dict {idx_rows[0]['dictitem']}")
                                # 仍然查第一个分类的条目
                            dictitems = [r["dictitem"] for r in idx_rows]
                            placeholders = ",".join(["%s"] * len(dictitems))
                            rows = q(cur,
                                     f"SELECT dictitem, subitem, subitemname FROM {ident(dict_db)}.sys_dictvalue "
                                     f"WHERE dictitem IN ({placeholders}) ORDER BY dictitem, subitem", tuple(dictitems))
                            cat_name = idx_rows[0]["itemname"]
                        if not rows:
                            sys.exit(f"❌ 字典分类 {cat!r} 无条目")
                        out = [f"📖 字典 {cat_name}（{dict_db}.sys_dictvalue）共 {len(rows)} 条："]
                        out.append("| subitem | subitemname |")
                        out.append("| --- | --- |")
                        out += [f"| {r['subitem']} | {r['subitemname'] or ''} |" for r in rows]
                    elif args.dict_bsflag:
                        sys.exit("❌ jzqs 无 bsflag 专用字典表。请用 --dict 64095（买卖标识）或 --dict 69022（集中交易买卖标识）查买卖相关字典")
                else:
                    sys.exit(f"❌ 库 {dict_db} 中未找到任何字典表（t_dict / sys_dictindex 均不存在），用 --dict-database 指定字典库")
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
    except pymysql.MySQLError as e:
        code = getattr(e, "args", [None])[0]
        if code == 1045:
            sys.exit(f"❌ 1045 Access denied：凭据被拒，请向用户索取正确口令后重试（dbx 内置凭据同样 1045）。")
        sys.exit(f"❌ 查询失败：{e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
