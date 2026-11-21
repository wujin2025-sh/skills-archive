# -*- coding: utf-8 -*-
"""
接口号 → 菜单 反查（用于 ba-to-dev 评审纪要第 4 项「前端界面」填写）

数据源：/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/rules-raw/菜单调用接口汇总.md
  - 723 个数字菜单（## 菜单编号 - 菜单名称）
  - 11008 条 ESB 调用（serviceId / 综合理财接口号 / 外围系统接口号 / Dao类 / 方法 / 调用条件 / 条件说明）
接口号分三类：综合理财接口号(多为8位)、外围系统接口号(6/8/12位)、serviceId(esb.xxx)。
一个接口号常出现在多个菜单（公共接口），本脚本给出命中菜单清单 + 出现次数，供 BA 结合需求业务语义判定哪些菜单属于本次评审纪要第 4 项。

用法:
  menu_interface_query.py --build                      # 首次/源文件更新后重建索引(.menu_interface.db)
  menu_interface_query.py --code 11811004              # 按接口号反查菜单（自动同时匹配三类列）
  menu_interface_query.py --code 7390747 --top 20      # 限制每接口展示菜单数（默认 30）
  menu_interface_query.py --batch 11811004,7390747     # 批量接口号，一次反查
  menu_interface_query.py --menu 联合开户               # 正向：菜单名/编号→完整接口号清单(去重分类)
  menu_interface_query.py --menu-extract "<需求原文>"    # 从原文抽【菜单】/功能号，批量反查接口号(供后续检索)
  menu_interface_query.py --kw 展期                     # 模糊：菜单名 or serviceId or 方法
  menu_interface_query.py --extract "需求原文文本..."    # 从需求原文自动抽取接口号并批量反查（评审纪要第4项辅助）
  menu_interface_query.py --stats                       # 索引统计

退出码: 0 命中 / 10 未命中 / 2 参数或索引错误
"""
import sqlite3, sys, io, os, re, argparse, time

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

SRC = "/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/rules-raw/菜单调用接口汇总.md"
DB = "/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/rules-raw/.menu_interface.db"

MENU_HDR = re.compile(r'^## (\d+) - (.+)$')
NUM = re.compile(r'^\d+$')


def build(con):
    if not os.path.exists(SRC):
        print(f"[ERR] 源文件不存在: {SRC}", file=sys.stderr)
        return False
    cur = con.cursor()
    cur.executescript("""
    DROP TABLE IF EXISTS menus;
    DROP TABLE IF EXISTS calls;
    DROP TABLE IF EXISTS meta;
    CREATE TABLE menus(
      menu_no TEXT PRIMARY KEY, menu_name TEXT, biz_class TEXT, biz_file TEXT,
      jsp TEXT, dao_refs TEXT, esb_count TEXT
    );
    CREATE TABLE calls(
      id INTEGER PRIMARY KEY AUTOINCREMENT, menu_no TEXT, menu_name TEXT,
      service_id TEXT, zh_code TEXT, peripheral_code TEXT, dao TEXT, method TEXT,
      cond TEXT, cond_desc TEXT
    );
    CREATE INDEX idx_calls_zh ON calls(zh_code);
    CREATE INDEX idx_calls_peripheral ON calls(peripheral_code);
    CREATE INDEX idx_calls_svc ON calls(service_id);
    CREATE INDEX idx_calls_menu ON calls(menu_no);
    CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
    """)
    lines = open(SRC, encoding='utf-8').read().split('\n')
    blocks = []
    cur_m = None
    for i, l in enumerate(lines):
        m = MENU_HDR.match(l)
        if m:
            if cur_m:
                blocks.append(cur_m)
            cur_m = {'no': m.group(1), 'name': m.group(2).strip(), 'attrs': {}, 'rows': [], 'ln': i + 1}
        elif cur_m is not None:
            if l.startswith('## '):
                blocks.append(cur_m)
                cur_m = None
                continue
            if l.startswith('| ') and not l.startswith('| serviceId') and not l.startswith('|---'):
                parts = [p.strip() for p in l.strip().strip('|').split('|')]
                # 属性表：| 菜单编号 | xxx |
                if len(parts) >= 2 and parts[0] in ('菜单编号','菜单名称','Business类','Business文件','JSP页面','Dao引用','ESB接口数'):
                    cur_m['attrs'][parts[0]] = parts[1].strip('`')
                # ESB 调用行：| `serviceId` | 综合理财 | 外围 | Dao | 方法 | 条件 | 说明 |
                elif len(parts) >= 5 and (parts[0].startswith('`') or NUM.match(parts[0].strip('`')) or 'Service' in parts[0]):
                    cur_m['rows'].append(parts)
    if cur_m:
        blocks.append(cur_m)

    n_menu = n_call = 0
    for b in blocks:
        a = b['attrs']
        g = lambda k: a.get(k, '')
        cur.execute("INSERT OR REPLACE INTO menus VALUES(?,?,?,?,?,?,?)",
                    (b['no'], b['name'], g('Business类'), g('Business文件'),
                     g('JSP页面'), g('Dao引用'), g('ESB接口数')))
        n_menu += 1
        for p in b['rows']:
            sid = p[0].strip('`').strip()
            zh = p[1].strip() if len(p) > 1 else ''
            peri = p[2].strip() if len(p) > 2 else ''
            dao = p[3].strip() if len(p) > 3 else ''
            method = p[4].strip() if len(p) > 4 else ''
            cond = p[5].strip() if len(p) > 5 else ''
            desc = p[6].strip() if len(p) > 6 else ''
            # 过滤掉换行断裂的条件说明噪声行（无 serviceId 且无接口号）
            if not sid and not zh and not peri:
                continue
            cur.execute("INSERT INTO calls(menu_no,menu_name,service_id,zh_code,peripheral_code,dao,method,cond,cond_desc) VALUES(?,?,?,?,?,?,?,?,?)",
                        (b['no'], b['name'], sid, zh, peri, dao, method, cond, desc))
            n_call += 1
    cur.execute("INSERT OR REPLACE INTO meta VALUES('src_mtime',?)", (str(int(os.path.getmtime(SRC))),))
    cur.execute("INSERT OR REPLACE INTO meta VALUES('n_menu',?)", (str(n_menu),))
    cur.execute("INSERT OR REPLACE INTO meta VALUES('n_call',?)", (str(n_call),))
    con.commit()
    n_unique = cur.execute("SELECT count(*) FROM menus").fetchone()[0]
    dup = n_menu - n_unique
    dup_note = f"（含 {dup} 个重复编号块已去重）" if dup else ""
    print(f"[build] 完成：{n_menu} 菜单块 → {n_unique} 唯一菜单{dup_note} / {n_call} 调用行 -> {DB}", file=sys.stderr)
    return True


def ensure(con, force=False):
    cur = con.cursor()
    try:
        has = cur.execute("SELECT count(*) FROM menus").fetchone()[0]
    except sqlite3.Error:
        has = 0
    if force or has == 0 or not os.path.exists(SRC):
        return build(con)
    try:
        old = cur.execute("SELECT v FROM meta WHERE k='src_mtime'").fetchone()
        new = str(int(os.path.getmtime(SRC)))
        if old and old[0] != new:
            return build(con)
    except sqlite3.Error:
        return build(con)
    return True


def lookup_code(con, code, top):
    """按接口号反查菜单：返回 (zh_hits, peri_hits, svc_hits)，命中按出现次数降序。
    每个 hit = (menu_no, menu_name, service_id, zh, peri, dao, method)"""
    cur = con.cursor()
    res = {'zh': [], 'peripheral': [], 'service': []}
    # 综合理财接口号
    for (no, name, sid, zh, peri, dao, method) in cur.execute(
            "SELECT menu_no,menu_name,service_id,zh_code,peripheral_code,dao,method FROM calls WHERE zh_code=?", (code,)):
        res['zh'].append((no, name, sid, zh, peri, dao, method))
    # 外围系统接口号
    for (no, name, sid, zh, peri, dao, method) in cur.execute(
            "SELECT menu_no,menu_name,service_id,zh_code,peripheral_code,dao,method FROM calls WHERE peripheral_code=?", (code,)):
        res['peripheral'].append((no, name, sid, zh, peri, dao, method))
    # serviceId（精确 + 后缀模糊）
    q = code if code.startswith('esb.') else None
    if q:
        svc_rows = list(cur.execute(
            "SELECT menu_no,menu_name,service_id,zh_code,peripheral_code,dao,method FROM calls WHERE service_id=?", (q,)))
    else:
        svc_rows = []
    for r in svc_rows:
        res['service'].append(r)
    return res


def menu_count(con, no):
    return con.execute("SELECT count(*) FROM calls WHERE menu_no=?", (no,)).fetchone()[0]


def render_code(con, code, top):
    r = lookup_code(con, code, top)
    menus = {}
    for kind in ('zh', 'peripheral', 'service'):
        for (no, name, sid, zh, peri, dao, method) in r[kind]:
            d = menus.setdefault((no, name), {'kinds': set(), 'svc': set(), 'dao': set(), 'method': set()})
            d['kinds'].add(kind)
            if sid: d['svc'].add(sid)
            if dao: d['dao'].add(dao)
            if method: d['method'].add(method)
    if not menus:
        return None, 0
    # 每菜单在该接口下的调用行数作为排序权重（同接口重复调用优先）
    total_calls = sum(len(v) for v in r.values())
    lines = [f"\n### 接口号 `{code}` → 命中 {len(menus)} 个菜单（{total_calls} 条调用）"]
    lines.append("| 菜单编号(功能号) | 菜单名称 | 命中列 | serviceId | Dao | 方法 | 该菜单ESB调用数 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    ordered = sorted(menus.items(), key=lambda kv: (-menu_count(con, kv[0][0]), kv[0][1]))
    for (no, name), d in ordered[:top]:
        kinds = '/'.join(sorted(d['kinds']))
        svc = ', '.join(sorted(d['svc']))[:60] or '-'
        dao = ', '.join(sorted(d['dao']))[:40] or '-'
        method = ', '.join(sorted(d['method']))[:40] or '-'
        lines.append(f"| {no} | {name} | {kinds} | {svc} | {dao} | {method} | {menu_count(con,no)} |")
    if len(menus) > top:
        lines.append(f"\n> ⚠️ 该接口为公共接口，命中 {len(menus)} 个菜单，上表仅列前 {top} 个。请结合需求业务语义判断本次实际涉及的菜单（可用 `--menu` 正向核对）。")
    return "\n".join(lines), len(menus)


def guess_codes(text):
    """从需求原文抽取候选接口号：优先已知接口号前缀，再兜底 7-8 位纯数字。"""
    # 已知前缀：118/119/739/749/1181 等综合理财，6 位外围
    cands = set(re.findall(r'(?<!\d)(\d{7,8})(?!\d)', text))
    # 排除日期段（20开头8位）
    cands = {c for c in cands if not (len(c) == 8 and c.startswith('20'))}
    svc = set(re.findall(r'(esb\.[\w.]+)', text))
    return sorted(cands), sorted(svc)


def menu_to_codes(con, menu_no):
    """菜单→接口号清单：返回 (综合理财号[], 外围号[], serviceId[])，各去重保序。"""
    zh, peri, svc = [], [], []
    for z, p, s in con.execute(
            "SELECT zh_code, peripheral_code, service_id FROM calls WHERE menu_no=? ORDER BY id", (menu_no,)):
        if z and NUM.match(z) and z not in zh:
            zh.append(z)
        if p and NUM.match(p) and p not in peri:
            peri.append(p)
        if s and s not in svc:
            svc.append(s)
    return zh, peri, svc


def match_menus(con, query):
    """菜单名/功能号→命中菜单行。
    P0#22 防望文生义：只做①功能号精确 ②菜单名整体互含（query⊆名称 或 名称⊆query）。
    【禁止】按 '-' 拆出「融资融券」等泛词逐片段匹配——会误命中一堆不相干菜单。"""
    q = query.strip()
    hits = {}
    # ① 功能号精确
    for row in con.execute("SELECT menu_no,menu_name FROM menus WHERE menu_no=?", (q,)):
        hits[row[0]] = row[1]
    # ② 菜单名整体互含（不做泛词拆分）
    if not hits:
        for row in con.execute("SELECT menu_no,menu_name FROM menus WHERE menu_name LIKE ? OR ? LIKE '%'||menu_name||'%'",
                               (f"%{q}%", q)):
            hits[row[0]] = row[1]
    return sorted(hits.items())


def extract_menus(text):
    """从需求原文抽取菜单线索：①【XXX】 ② 功能号 NNNNN ③ "【XXX】菜单" 中的名称"""
    names = set(re.findall(r'【([^】]{2,40})】', text))
    funcnos = set(re.findall(r'功能号\s*[:：]?\s*(\d{4,6})', text))
    # 抽取形如 "XX菜单" / "XX界面" 的短语（无【】时兜底）
    return sorted(names), sorted(funcnos)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--build', action='store_true')
    ap.add_argument('--code')
    ap.add_argument('--batch')
    ap.add_argument('--menu')
    ap.add_argument('--menu-extract', dest='menu_extract')
    ap.add_argument('--kw')
    ap.add_argument('--extract')
    ap.add_argument('--top', type=int, default=30)
    ap.add_argument('--stats', action='store_true')
    args = ap.parse_args()

    t0 = time.time()
    con = sqlite3.connect(DB)
    try:
        if not ensure(con, args.build):
            return 2
        cur = con.cursor()
        if args.build and not any([args.code, args.batch, args.menu, args.menu_extract, args.kw, args.extract, args.stats]):
            return 0
        if args.stats:
            nm = cur.execute("SELECT count(*) FROM menus").fetchone()[0]
            nc = cur.execute("SELECT count(*) FROM calls").fetchone()[0]
            nz = cur.execute("SELECT count(DISTINCT zh_code) FROM calls WHERE zh_code!=''").fetchone()[0]
            np_ = cur.execute("SELECT count(DISTINCT peripheral_code) FROM calls WHERE peripheral_code!=''").fetchone()[0]
            ns = cur.execute("SELECT count(DISTINCT service_id) FROM calls").fetchone()[0]
            print(f"菜单 {nm} / 调用行 {nc} / 综合理财接口号 {nz} / 外围接口号 {np_} / serviceId {ns}")
            return 0
        codes = []
        if args.code:
            codes.append(args.code.strip())
        if args.batch:
            codes += [c.strip() for c in args.batch.split(',') if c.strip()]
        if args.extract:
            nums, svcs = guess_codes(args.extract)
            codes += nums + svcs
            print(f"[extract] 从文本抽取候选接口号：{codes}", file=sys.stderr)
        codes = list(dict.fromkeys(codes))  # 去重保序

        total_hit = 0
        out = []
        if codes:
            for c in codes:
                txt, n = render_code(con, c, args.top)
                if txt:
                    out.append(txt)
                    total_hit += n
                else:
                    hint = ""
                    if NUM.match(c) and len(c) == 7:
                        hint = "（7 位号段多为低延时/集中交易内部功能号，通常**无前台菜单**，反查不到属正常——评审纪要第 4 项按业务判断即可；若确为综合理财接口请核对号是否准确）"
                    out.append(f"\n### 接口号 `{c}` → 未命中菜单{hint}")
        def render_menu_detail(no, name, full=False):
            """渲染单菜单的==完整去重接口号清单==（供后续 fwzl-mcp/interface_query 检索）"""
            zh, peri, svc = menu_to_codes(con, no)
            out.append(f"\n#### 【{name}】功能号 {no} — 调用接口号清单")
            out.append(f"- **综合理财接口号（{len(zh)}）**：{'、'.join(zh) if zh else '无'}")
            out.append(f"- **外围系统接口号（{len(peri)}）**：{'、'.join(peri) if peri else '无'}")
            if svc:
                out.append(f"- **serviceId（{len(svc)}）**：{'、'.join(svc[:20])}{'…' if len(svc)>20 else ''}")
            if full and zh:
                out.append(f"- **后续检索**：`--batch {','.join(zh[:20])}` 或 fwzl-mcp `functionQueryServiceByKeyWord`")

        if args.menu:
            hits = match_menus(con, args.menu)
            if hits:
                out.append(f"\n### 菜单 `{args.menu}` → 命中 {len(hits)} 个（菜单→接口号反向检索）")
                out.append("| 功能号 | 菜单名称 | ESB调用数 |")
                out.append("| --- | --- | --- |")
                for no, name in hits[:50]:
                    ec = con.execute("SELECT esb_count FROM menus WHERE menu_no=?", (no,)).fetchone()
                    out.append(f"| {no} | {name} | {ec[0] if ec else '-'} |")
                for no, name in hits[:10]:
                    render_menu_detail(no, name, full=(len(hits) <= 3))
                total_hit += len(hits)
            else:
                out.append(f"\n### 菜单 `{args.menu}` → 未命中")
                out.append("> ⚠️ 本库仅覆盖 **qyyx/Web 平台菜单**（5 位业务代码如 20000 联合开户）。")
                out.append("> 若你要查的是**集中清算/营运 C++ 柜台菜单**（如 504015 历史仓单资券变动）或**低延时功能号**（739xxxx），")
                out.append("> 这类菜单**无 ESB 接口号**，请改用 CBM 代码图谱 `search_code` 定位功能号对应函数（见 SKILL Step 2 代码域）。")

        if args.menu_extract:
            names, funcnos = extract_menus(args.menu_extract)
            print(f"[menu-extract] 从原文抽取菜单名 {len(names)} 个 / 功能号 {len(funcnos)} 个：{names} {funcnos}", file=sys.stderr)
            all_zh, all_peri = [], []
            out.append(f"\n### 需求原文→菜单→接口号 反向检索（菜单名 {len(names)} + 功能号 {len(funcnos)}）")
            found_any = False
            for q in names + funcnos:
                hits = match_menus(con, q)
                kind = "功能号" if q in funcnos else "菜单名"
                if len(hits) == 1:  # 唯一命中：展开接口号并汇总
                    found_any = True
                    no, name = hits[0]
                    zh, peri, svc = menu_to_codes(con, no)
                    for c in zh:
                        if c not in all_zh: all_zh.append(c)
                    for c in peri:
                        if c not in all_peri: all_peri.append(c)
                    out.append(f"- ✅ {kind} `{q}` → 【{name}】({no})：综合理财号 {len(zh)} / 外围号 {len(peri)} / serviceId {len(svc)}")
                    total_hit += 1
                elif len(hits) > 1:  # 多命中：列候选，不自动汇总（防泛词污染）
                    cand = '、'.join([f"{n}({no})" for no, n in hits[:8]])
                    out.append(f"- ⚠️ {kind} `{q}` 模糊命中 {len(hits)} 个菜单，请确认目标后用 `--menu <精确名>` 展开：{cand}")
                    total_hit += len(hits)
                else:
                    out.append(f"- ⚠️ {kind} `{q}` 本库未命中（多为集中清算/营运 6 位功能号或低延时功能号，**无 ESB 接口号**，请走 CBM 代码图谱）")
            if all_zh or all_peri:
                out.append(f"\n**📋 汇总接口号清单（唯一命中菜单，去重，供后续 fwzl-mcp / interface_query 检索）**：")
                out.append(f"- 综合理财接口号：{'、'.join(all_zh)}")
                out.append(f"- 外围系统接口号：{'、'.join(all_peri)}")
                out.append(f"- 直接批量反查：`--batch {','.join(all_zh[:20])}`")
            if not found_any:
                out.append("\n> 本次抽取的菜单/功能号无唯一命中：或属集中清算/营运 C++ 柜台菜单（另一体系，无 ESB 接口号，走 CBM 代码图谱），或为泛词需 `--menu <精确名>` 进一步确认。")
        if args.kw:
            kw = f"%{args.kw}%"
            rows = list(cur.execute(
                "SELECT DISTINCT menu_no,menu_name FROM calls WHERE menu_name LIKE ? OR service_id LIKE ? OR method LIKE ? ORDER BY menu_no", (kw, kw, kw)))
            if rows:
                out.append(f"\n### 关键字 `{args.kw}` → {len(rows)} 个菜单")
                out.append("| 菜单编号 | 菜单名称 |")
                out.append("| --- | --- |")
                for no, name in rows[:80]:
                    out.append(f"| {no} | {name} |")
                total_hit += len(rows)
            else:
                out.append(f"\n### 关键字 `{args.kw}` → 未命中")

        if not codes and not args.menu and not args.menu_extract and not args.kw:
            ap.print_help()
            return 0
        print("\n".join(out))
        print(f"\n[耗时] {(time.time()-t0)*1000:.1f} ms | 命中菜单合计 {total_hit}", file=sys.stderr)
        return 0 if total_hit else 10
    finally:
        con.close()


if __name__ == '__main__':
    sys.exit(main())
