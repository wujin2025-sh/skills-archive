# -*- coding: utf-8 -*-
"""
业务逻辑智能问答 + 证据链工具 (Biz-Logic Query with Evidence Chain)
==================================================================
业务问题 → 五域并行检索（需求反查 / 接口库 / 代码图谱 / 数据库 / 业务规则）
         → 一句话结论 + 证据出处表 + 可信度分级 + 影响范围 + 澄清建议

v2 (2026-11-13) 性能与交互改造：
  * 五域 ThreadPoolExecutor 并行（旧版串行，耗时 ≈ 各域之和）
  * 文件缓存（代码图谱/数据库结构 24h、需求反查 1h、业务规则 6h），--refresh 失效
  * 中文概念 → 英文标识符映射，避免 CBM BM25 中文噪声 / dbq 中文表名恒 0 命中
  * 默认关闭 trace_path（旧版对中文词必然 0 命中），需要时 --trace
  * 单域超时保护，慢域不拖垮整体
  * --fast / --verbose / --timings / --projects / --no-clarify
  * 输出 clarification：仅在歧义/未命中时给出「向用户确认」建议，答案可回灌为关键词/参数

复用权威源（不重造检索核心）：
  L0 需求依赖反查   ba-to-dev/scripts/demand_dep_find.py
  L1 接口知识库     WorkBuddy/需求分析/rules-raw/.interface_store.db
  L2 代码知识图谱   codebase-memory-mcp cli (search_code grep / search_graph / trace_path)
  L3 数据库实证     dbq <profile>
  L4 业务规则       openviking_mcp.py find/glob/read

证据链可信度分级：
  [已实证] 接口库 / dbq / 需求原文 / 源码+行号
  [可追溯] 图谱索引 / openviking 检索
  [待确认] 未命中，需人工或研发确认 —— 严禁臆断补全

退出码: 0=有证据结论  2=熔断未命中  10=本地资源不可用
"""

import argparse
import hashlib
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------- 路径配置
OBSIDIAN_DEMAND = Path("/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析")
INTERFACE_DB = Path("/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/rules-raw/.interface_store.db")
SUBSCRIPTION_DB = Path("/Volumes/Macintosh HD_Data/WorkBuddy/需求分析/rules-raw/.subscription_matrix.db")
BA_SCRIPTS = Path("/Users/wujin/.chat/skills/ba-to-dev/scripts")
CBM_BIN = Path.home() / ".local/bin/codebase-memory-mcp"
OPENVIKING_SCRIPT = Path("/Users/wujin/.workbuddy/skills/openviking-query/openviking_mcp.py")
DBQ_BIN = Path("/usr/local/bin/dbq")
SKILL_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = SKILL_DIR / ".cache"

PROJECTS = {
    "jzjy": "Volumes-Macintosh-HD_Data-Project-jzjy-spbsrc",
    "dys": "Volumes-Macintosh-HD_Data-Project-dys-branches-master-tree",
    "jzqs": "Volumes-Macintosh-HD_Data-Project-jzqs-src-src",
    "cszx": "jygl_sys_cszx",
    "grc": "Volumes-Macintosh-HD_Data-Project-grc",
}
DBQ_PROFILES = {"jzjy": "jzjy_sit", "dys": "dys95", "jzqs": "jzqs_sit", "cszx": "cszx_sit"}

# 默认自动多域并行（用户 2026-11-13 确认）
DEFAULT_PROJECTS = ["jzjy", "dys", "jzqs"]
CACHE_TTL = {"demand": 3600, "cbm": 86400, "db": 86400, "rule": 21600}
TIMEOUTS = {"demand": 20, "cbm": 12, "db": 20, "rule": 25}
MAX_WORKERS = 10
DETAIL_LIMIT = 600          # 证据摘要默认上限（旧版 120/240 会丢关键信息）

CONF_EMPIRICAL = "已实证"
CONF_TRACEABLE = "可追溯"
CONF_PENDING = "待确认"

# 中文业务概念 → 英文标识符（中文在 C++ 图谱 BM25 全是 makefile 噪声、dbq 中文表名恒 0 命中）
# 长短语优先；只登记已实证过的映射，未实证的一律走通用映射并在澄清里请用户补充
KEYWORD_MAP = [
    # 2026-11-17「融资规模设置菜单」实证：参数/菜单类概念必须优先于「融资」，
    # 否则退化成 loan → 185 条「融资」同族噪声，且代码图谱完全跑偏
    ("单一客户所有证券融资规模占净资本比例", ["creditscale", "stkChkCreditSingleScale"]),
    ("全体客户所有证券融资规模占净资本比例", ["creditscale", "stkChkCreditTotalScale"]),
    ("融资规模设置", ["creditscale", "creditmixparam"]),
    ("信用交易规模", ["creditscale"]),
    ("单一证券融资规模", ["creditscale"]),
    ("净资本", ["creditscale", "creditmixparam"]),
    ("规模参数", ["creditscale"]),
    ("系统节点", ["systemcfg"]),
    ("指定合约还款", ["contract_sno", "direct_repay_appoint"]),
    ("直接还款", ["direct_repay"]),
    ("指定合约", ["contract_sno"]),
    ("卖券还款", ["repay", "sellstock"]),
    ("担保品", ["guaranty"]),
    ("合约展期", ["contract", "delay"]),
    ("多合约", ["contract"]),
    ("合约", ["contract"]),
    ("负债", ["debt"]),
    ("还款", ["repay"]),
    ("融资", ["loan"]),
    ("融券", ["short"]),
    ("委托", ["order"]),
    ("清算", ["clear"]),
    ("展期", ["delay"]),
    ("试算", ["calc"]),
    ("成交", ["exec"]),
    ("划转", ["transfer"]),
    ("回购", ["repo"]),
    ("质押", ["pledge"]),
    ("利息", ["interest"]),
    ("息费", ["fee"]),
    ("查询", ["query"]),
]
# 表名级关键词（字段名如 contract_sno 不能拿来搜表名，否则恒 0 命中）
DB_KEYWORD_MAP = [
    ("规模", "scale"), ("净资本", "creditmixparam"), ("节点", "systemcfg"),
    ("还款", "repay"), ("负债", "debt"), ("合约", "contract"),
    ("融资", "loan"), ("融券", "short"), ("清算", "clear"),
    ("展期", "delay"), ("委托", "order"), ("担保品", "guaranty"),
    ("回购", "repo"), ("质押", "pledge"), ("息费", "fee"),
]
# 参数/菜单类概念 → 接口库 table_name 精确回查（2026-11-17 实证，缺陷 #11）
# 这类概念在 name/code/description 里往往完全不出现，只以「文件接口的表名」登记
PARAM_TABLE_HINT = [
    ("融资规模", "creditscale"),
    ("信用交易规模", "creditscale"),
    ("净资本", "creditscale"),
    ("规模设置", "creditscale"),
    ("规模参数", "creditscale"),
    ("系统节点", "systemcfg"),
    ("节点配置", "systemcfg"),
]
# 按系统域覆盖代码检索词（2026-11-13「直接还款」实证：
# 低延时模块名 direct_repay 在 jzjy 全库 grep 必然 0 命中且耗时 10.28s，是冷启动最大瓶颈）
PROJECT_KW_OVERRIDE = {
    ("直接还款", "jzjy"): "perCRReturnFund",
    ("指定合约还款", "jzjy"): "perCRReturnFundAppointed",
    ("卖券还款", "jzjy"): "stkReturnFundcomLoan",
    ("直接还款", "dys"): "direct_repay",
    ("指定合约还款", "dys"): "direct_repay_appoint",
}
# 主域 grep 限定业务代码目录，避免扫 bin/config 噪声并显著提速
PROJECT_PATH_FILTER = {"jzjy": "lbmdll/", "dys": "biz_impl/", "jzqs": "lbm/"}
# 同族接口自动扩展：概念 → 最泛的核心业务词（缺陷 #4 修复）
FAMILY_CORE_MAP = [
    "还款", "合约", "负债", "展期", "担保品", "回购", "质押",
    "委托", "清算", "划转", "试算", "成交", "融资", "融券",
]
FAMILY_CLARIFY_THRESHOLD = 12       # 同族接口 ≥12 条视为概念多义，触发澄清
# 「编号 + 名称」组合查询里的文件号/功能号 token：A37 / Q49 / S140 / 124370 / 7300780
FILE_CODE_TOKEN = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{1,2}\d{1,4}|\d{5,9})(?![A-Za-z0-9])")
NOISE_CBM = re.compile(r"(makefile|RWSemaphore|kcpd_sync)", re.I)
ASCII_IDENT = re.compile(r"^[A-Za-z0-9_.:-]+$")


# ---------------------------------------------------------------- 缓存
def _cache_path(key):
    return CACHE_DIR / (hashlib.md5(key.encode("utf-8")).hexdigest() + ".json")


def cache_get(key, ttl):
    if not key or ttl <= 0:
        return None
    try:
        p = _cache_path(key)
        if p.exists() and (time.time() - p.stat().st_mtime) < ttl:
            d = json.loads(p.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) and "v" in d else None
    except Exception:                                            # noqa: BLE001
        pass
    return None


def cache_put(key, value):
    if not key:
        return
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(key).write_text(json.dumps({"v": value}, ensure_ascii=False), encoding="utf-8")
    except Exception:                                            # noqa: BLE001
        pass


def clear_cache():
    n = 0
    try:
        for p in CACHE_DIR.glob("*.json"):
            p.unlink()
            n += 1
    except Exception:                                            # noqa: BLE001
        pass
    return n


def run_jobs(jobs, refresh=False):
    """并行执行检索任务。job: {name, fn, key, ttl} -> {name: (value, elapsed, from_cache)}"""
    out, pending = {}, []
    for j in jobs:
        hit = None if refresh else cache_get(j.get("key"), j.get("ttl", 0))
        if hit is not None:
            out[j["name"]] = (hit["v"], 0.0, True)
        else:
            pending.append(j)

    def timed(job):
        t = time.perf_counter()
        try:
            v = job["fn"]()
        except Exception as e:                                    # noqa: BLE001
            v = f"(调用失败: {e})"
        return v, time.perf_counter() - t

    if pending:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(pending))) as ex:
            futs = {ex.submit(timed, j): j for j in pending}
            for f in as_completed(futs):
                j = futs[f]
                v, d = f.result()
                out[j["name"]] = (v, d, False)
                # 超时/0 命中也是确定性结果，一并缓存（--refresh 可强制重查），
                # 否则慢域每次都要重新等待，热启动提速失效。
                if v and not str(v).startswith("(调用失败"):
                    cache_put(j.get("key"), v)
    return out


# ---------------------------------------------------------------- 关键词推导
def derive_keywords(q, iface_fields=None):
    """中文概念 -> 精准英文检索词。返回 (primary, alternatives, reason)"""
    if ASCII_IDENT.match(q):
        return q, [], "功能号/英文标识符，直接检索"
    for phrase, words in KEYWORD_MAP:
        if phrase in q:
            return words[0], words[1:], f"命中实测短语映射「{phrase}」"
    words = []
    for phrase, mapped in KEYWORD_MAP:
        if phrase in q and mapped[0] not in words:
            words.append(mapped[0])
        if len(words) >= 2:
            break
    if iface_fields:
        for f in iface_fields:
            if len(f) >= 8 and f not in words and not re.search(
                r"(custid|fundid|orgid|brhid|serverid|sysdate|moneytype|client_seq)", f, re.I
            ):
                words.append(f)
            if len(words) >= 3:
                break
    return (words[0] if words else ""), words[1:], "通用中英映射"


def project_keyword(q, project):
    """按系统域覆盖主检索词：中文概念用实测符号，英文标识符不覆盖"""
    if ASCII_IDENT.match(q):
        return None
    for (phrase, pr), word in PROJECT_KW_OVERRIDE.items():
        if pr == project and phrase in q:
            return word
    return None


def derive_db_keyword(q, kw):
    """表名级检索词：中文概念优先映射，字段名样式（*_sno/_date/_id）不用于搜表"""
    for phrase, word in DB_KEYWORD_MAP:
        if phrase in q:
            return f"%{word}%", f"中文短语「{phrase}」→ 表名词 {word}"
    if ASCII_IDENT.match(q) and not re.search(r"(_sno|_date|_id|_value|_no)$", q):
        return f"%{q}%", "英文标识符直接搜表"
    return f"%{kw or q}%", "兜底：使用推导词"


# ---------------------------------------------------------------- 各检索域
def query_interface(db_path, keyword, limit=10):
    """L1 接口知识库（毫秒级）。返回 (rows, err)，兼容旧签名"""
    res = []
    if not db_path.exists():
        return res, "接口库不存在"
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        exact = cur.execute(
            "SELECT * FROM interfaces WHERE code=? OR name=? LIMIT ?", (keyword, keyword, limit)
        ).fetchall()
        if exact:
            res = exact
        else:
            like = f"%{keyword}%"
            res = cur.execute(
                "SELECT * FROM interfaces WHERE code LIKE ? OR name LIKE ? "
                "OR description LIKE ? OR system_name LIKE ? LIMIT ?",
                (like, like, like, like, limit),
            ).fetchall()
            if not res:
                # 缺陷 #9：「A37 大宗交易预委托记录信息」「Q49 xxx」这类
                # 「文件号/功能号 + 名称」组合，整词 LIKE 必然 0 命中。
                # 提取编号 token 再按 code 精确回查（字母开头编号或 5-9 位纯数字）。
                m = FILE_CODE_TOKEN.search(keyword)
                if m:
                    res = cur.execute(
                        "SELECT * FROM interfaces WHERE code=? LIMIT ?",
                        (m.group(1), limit),
                    ).fetchall()
            if not res:
                # 缺陷 #11：参数/菜单类概念在 name/code/description 里可能完全不出现，
                # 只登记为文件接口的 table_name（S24 信用交易规模参数 → creditscale）
                for phrase, table in PARAM_TABLE_HINT:
                    if phrase in keyword:
                        res = cur.execute(
                            "SELECT * FROM interfaces WHERE table_name=? LIMIT ?",
                            (table, limit),
                        ).fetchall()
                        if res:
                            break
        conn.close()
    except Exception as e:                                        # noqa: BLE001
        return [], f"接口库查询失败: {e}"
    return res, None


def query_subscription(code):
    """L1.5 订阅矩阵：查某文件编号的消费者（只读，毫秒级；库不存在时静默跳过）"""
    if not SUBSCRIPTION_DB.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{SUBSCRIPTION_DB}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT s.consumer, f.producer_system, s.evidence_status "
            "FROM subscriptions s JOIN files f ON f.file_code=s.file_code "
            "WHERE s.file_code=? ORDER BY s.consumer", (code,)).fetchall()
        conn.close()
        if not rows:
            return None
        cons = "、".join(r["consumer"] for r in rows)
        return (f"输出系统:{rows[0]['producer_system']}｜消费者({len(rows)}): {cons}"
                f"｜{rows[0]['evidence_status']}｜详见 subscription_matrix.py query {code}")
    except Exception:                                             # noqa: BLE001
        return None


def query_interface_fields(db_path, interface_ids):
    """取接口英文字段名，用于推导更精准的代码检索词"""
    fields = []
    if not interface_ids or not db_path.exists():
        return fields
    try:
        conn = sqlite3.connect(str(db_path))
        ph = ",".join("?" * len(interface_ids))
        fields = [x[0] for x in conn.execute(
            f"SELECT DISTINCT field_name FROM interface_fields WHERE interface_id IN ({ph})",
            interface_ids,
        ).fetchall() if x[0]]
        conn.close()
    except Exception:                                            # noqa: BLE001
        pass
    return fields


def query_interface_family(db_path, q, ifaces):
    """同族接口自动扩展（缺陷 #4）：用最泛的核心业务词 LIKE 全库，返回分组概览。
    旧版只取 query_interface 前 5 条 + 完整中文词 LIKE，实测「直接还款」41 条只返回 2 条。"""
    # 缺陷 #10：用户已明确给出文件号/功能号时，不再用「委托」这类泛词做同族扩展
    # （实测「A37 大宗交易预委托记录信息」被扩成 350 条噪声）。
    if FILE_CODE_TOKEN.search(q) and ifaces:
        return None
    core = next((w for w in FAMILY_CORE_MAP if w in q), None)
    if not core or not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        like = f"%{core}%"
        rows = conn.execute(
            "SELECT code,name,system_name FROM interfaces "
            "WHERE name LIKE ? OR description LIKE ? ORDER BY code", (like, like),
        ).fetchall()
        conn.close()
    except Exception:                                            # noqa: BLE001
        return None
    by_system = {}
    for r in rows:
        by_system[r["system_name"]] = by_system.get(r["system_name"], 0) + 1
    seen = {r["code"] for r in ifaces}
    return {
        "core": core, "total": len(rows),
        "by_system": by_system,
        "extras": [dict(r) for r in rows if r["code"] not in seen],
    }


def query_demand_ref(concept, req_dir=None):
    """L0 需求依赖反查"""
    if not (BA_SCRIPTS / "demand_dep_find.py").exists():
        return None
    req_dir = req_dir or str(OBSIDIAN_DEMAND)
    try:
        p = subprocess.run(
            [sys.executable, str(BA_SCRIPTS / "demand_dep_find.py"),
             "--concept", concept, "--req-dir", req_dir],
            capture_output=True, text=True, timeout=TIMEOUTS["demand"],
        )
        return (p.stdout or p.stderr).strip()[:1500] if p.returncode == 0 else p.stderr.strip()[:800]
    except subprocess.TimeoutExpired:
        return f"(需求反查超时 {TIMEOUTS['demand']}s，已跳过)"
    except Exception as e:                                       # noqa: BLE001
        return f"(demand 反查失败: {e})"


def _cbm_run(args, timeout):
    try:
        p = subprocess.run([str(CBM_BIN), "cli"] + args,
                           capture_output=True, text=True, timeout=timeout)
        out = "\n".join(ln for ln in (p.stdout or "").splitlines() if "level=" not in ln).strip()
        return out or "(CBM 0 命中)"
    except subprocess.TimeoutExpired:
        return f"(CBM 超时 {timeout}s，已跳过；可 --cbm-timeout 调大或 --project 单域重试)"
    except Exception as e:                                       # noqa: BLE001
        return f"(CBM 调用失败: {e})"


def query_cbm(project, query, mode="search", direction=None, depth=2, timeout=None):
    """L2 代码图谱：search_graph (BM25) / trace_path，兼容旧调用"""
    if not CBM_BIN.exists():
        return None
    timeout = timeout or TIMEOUTS["cbm"]
    project_name = PROJECTS.get(project) or project
    if mode == "trace":
        if direction not in ("inbound", "outbound", "both"):
            direction = "inbound"
        args = ["trace_path", "--project", project_name, "--function-name", query,
                "--direction", direction, "--depth", str(depth),
                "--limit", "15", "--format", "tree"]
    else:
        args = ["search_graph", "--project", project_name, "--query", query,
                "--limit", "15", "--format", "tree"]
    return _cbm_run(args, timeout)


def query_cbm_code(project, pattern, timeout=None, limit=8, path_filter=None):
    """L2 精准模式：search_code (grep) —— 中文概念映射成英文标识符后必用此模式"""
    if not CBM_BIN.exists():
        return None
    timeout = timeout or TIMEOUTS["cbm"]
    project_name = PROJECTS.get(project) or project
    args = ["search_code", "--project", project_name, "--pattern", pattern,
            "--mode", "compact", "--limit", str(limit)]
    if path_filter:
        args += ["--path-filter", path_filter]
    return _cbm_run(args, timeout)


def query_db(project, table=None, search_table=None, sql=None, timeout=None):
    """L3 数据库实证（dbq 直连）"""
    timeout = timeout or TIMEOUTS["db"]
    profile = DBQ_PROFILES.get(project)
    if not profile:
        return f"(grc/{project} 无 DB 直连，跳过 dbq)"
    if not DBQ_BIN.exists():
        return "(dbq 不可用)"
    cmd = [str(DBQ_BIN), profile]
    if sql:
        cmd += ["--sql", sql]
    elif search_table:
        cmd += ["--search-table", search_table]
    elif table:
        cmd += ["--table", table]
    else:
        return "(query_db 需指定 table/search_table/sql 之一)"
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "").strip() or (p.stderr or "").strip()
        return out[:1500] if out else "(dbq 无输出)"
    except subprocess.TimeoutExpired:
        return f"(dbq 超时 {timeout}s，已跳过)"
    except Exception as e:                                       # noqa: BLE001
        return f"(dbq 调用失败: {e})"


def query_openviking(concept, subcmd="find", uri=None, timeout=None):
    """L4 业务规则/既有需求检索"""
    if not OPENVIKING_SCRIPT.exists():
        return "(openviking 脚本不可用)"
    timeout = timeout or TIMEOUTS["rule"]
    env = dict(os.environ)
    env.setdefault("NO_PROXY", "")
    env["NO_PROXY"] = ",".join(
        x for x in (env["NO_PROXY"].split(",") + ["csgl.gtht.com.cn", "fintech.gtht.com.cn"]) if x.strip()
    )
    env.setdefault("no_proxy", env["NO_PROXY"])
    cmd = [sys.executable, str(OPENVIKING_SCRIPT), subcmd, concept]
    if uri:
        cmd.append(uri)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "").strip() or (p.stderr or "").strip()
        return out[:4000] if out else "(openviking 无输出)"
    except subprocess.TimeoutExpired:
        return f"(openviking 超时 {timeout}s，已跳过)"
    except Exception as e:                                       # noqa: BLE001
        return f"(openviking 调用失败: {e})"


# ---------------------------------------------------------------- 澄清建议（仅歧义/未命中时）
def build_clarification(q, ifaces, cbm_values, dep, projects, kw, code_mode, family=None):
    items = []
    if not ifaces:
        items.append({
            "why": "接口库 0 命中，当前关键词可能不是系统内正式名称",
            "question": "请确认该功能的功能号、接口名或所属系统域？",
            "options": ["补充功能号/接口名", "换系统域重查", "提供业务原文描述"],
            "refine": "把答案作为 question 重跑，或 --project 指定系统域",
        })
    if len(ifaces) >= 4:
        items.append({
            "why": f"命中 {len(ifaces)} 个同族接口（请求/应答/试算/委托等），存在多义",
            "question": "本次要定位的是哪一类？",
            "options": [r["name"] for r in ifaces[:4]],
            "refine": "用确认后的接口名/功能号作为 question 重跑",
        })
    # ≥5 字且已实测登记的精确概念（如「指定合约还款」）视为明确，不再因同族扩展打扰用户
    precise = any(ph == q and len(ph) >= 5 for ph, _ in KEYWORD_MAP)
    if family and family["total"] >= FAMILY_CLARIFY_THRESHOLD and not precise:
        opts = [f"{s}({n}条)" for s, n in
                sorted(family["by_system"].items(), key=lambda x: -x[1])[:3]]
        opts.append("仅主命中接口，不展开同族")
        items.append({
            "why": (f"按核心词 '%{family['core']}%' 自动扩展出 {family['total']} 条同族接口，"
                    "概念存在多义（普通/指定合约/卖券/小贷等子类）"),
            "question": "本次要定位的是哪一类 / 哪个系统域？",
            "options": opts,
            "refine": "用确认后的接口名或功能号作为 question 重跑；只要主命中可 --no-clarify",
        })
    if not kw and not ASCII_IDENT.match(q):
        items.append({
            "why": "中文概念未能映射出英文标识符（功能号/函数名/字段名均可），代码层关键词无法精准化",
            "question": "能否补充该功能的英文函数名、报文结构名或字段标识？",
            "options": ["提供英文函数名", "提供报文字段名", "跳过代码层"],
            "refine": "把英文标识符作为 question 重跑，或补进 KEYWORD_MAP 实测字典",
        })
    cbm_text = "\n".join(str(v) for v in cbm_values if v)
    if cbm_text and ("超时" in cbm_text or "0 命中" in cbm_text):
        items.append({
            "why": "代码图谱多域未命中或超时",
            "question": "是否只需关注某一个系统域？",
            "options": projects + ["保持多域"],
            "refine": "--project <域> 单域重跑（更快更准）",
        })
    # 注意：dep 开头固定带「（无本地 MD）」占位，只有同时没有 ▶ 命中行才是真未命中
    if dep and "（无本地 MD）" in str(dep) and "▶" not in str(dep):
        items.append({
            "why": "本地需求库未命中该概念（或仅命中占位模板）",
            "question": "是否有明确需求号需要一并核对？",
            "options": ["提供需求号", "不需要，仅看已有命中"],
            "refine": "用需求号作为 question 重跑",
        })
    return items


# ---------------------------------------------------------------- 渲染
def render(conclusion, evidence_rows, impact_rows, mode="text", extra=None):
    extra = extra or {}
    if mode == "json":
        return json.dumps({
            "conclusion": conclusion,
            "evidence": [dict(zip(("source", "confidence", "detail"), r)) for r in evidence_rows],
            "impact": impact_rows,
            **extra,
        }, ensure_ascii=False, indent=2)

    lines = ["📌 结论", f"  {conclusion}", "", "🔎 证据链"]
    if evidence_rows:
        lines += ["| 出处 | 可信度 | 说明 |", "|------|:-----:|------|"]
        for src, conf, det in evidence_rows:
            cell = str(det).replace(chr(10), " ").replace("|", "\\|")
            lines.append(f"| {src} | {conf} | {cell} |")
    else:
        lines.append("  未检索到可实证证据（熔断）—— ↑ 以下为待确认事项，需研发/业务确认")
    if impact_rows:
        lines += ["", "⚠️ 影响范围提示"] + [f"  · {i}" for i in impact_rows]
    if extra.get("clarification"):
        lines += ["", "❓ 建议向用户确认（仅在歧义/未命中时）"]
        for c in extra["clarification"]:
            lines.append(f"  · {c['question']}  [{c['why']}]")
            lines.append(f"    选项: {' / '.join(c['options'])}")
            lines.append(f"    回灌: {c['refine']}")
    if not extra.get("quiet"):
        lines += ["", f"⏱ 总耗时 {extra.get('total', 0):.2f}s｜"
                  f"并行 {extra.get('job_count', 0)} 任务｜缓存命中 {extra.get('cache_hits', 0)}｜"
                  f"域 {','.join(extra.get('projects', []))}"]
        if extra.get("show_timings"):
            for k, v in sorted(extra.get("timings", {}).items(), key=lambda x: -x[1]):
                lines.append(f"    {k:40s} {v:6.2f}s")
    return "\n".join(lines)


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(description="业务逻辑智能问答 + 证据链工具 (并行加速版)")
    ap.add_argument("question", help="业务问题 / 业务概念 / 功能号 / 英文函数名")
    ap.add_argument("--all", action="store_true", help="全域检索（默认亦为全域；保留兼容）")
    ap.add_argument("--json", action="store_true", help="结构化 JSON 输出")
    ap.add_argument("--code", action="store_true", help="按功能号/文件号查询接口")
    ap.add_argument("--project", default=None, help="单域检索，覆盖默认多域（jzjy/dys/jzqs/cszx/grc）")
    ap.add_argument("--projects", default=None, help="自定义多域，逗号分隔，如 jzjy,dys")
    ap.add_argument("--db-table", default=None, help="[L3] 指定 库.表 查结构")
    ap.add_argument("--db-search-table", default=None, help="[L3] 按表名关键字搜表")
    ap.add_argument("--db-sql", default=None, help="[L3] 直查 SQL（值实证，不缓存）")
    ap.add_argument("--no-db", action="store_true", help="关闭 L3 数据库检索")
    ap.add_argument("--no-rule", action="store_true", help="关闭 L4 业务规则检索")
    ap.add_argument("--fast", action="store_true", help="快速模式：仅 L1 接口库 + L4 业务规则")
    ap.add_argument("--trace", action="store_true", help="额外跑 trace_path 影响范围（默认关闭以提速）")
    ap.add_argument("--verbose", action="store_true", help="证据摘要不截断（默认上限 600 字符）")
    ap.add_argument("--timings", action="store_true", help="打印各检索域耗时明细")
    ap.add_argument("--quiet", action="store_true", help="不打印耗时信息")
    ap.add_argument("--refresh", action="store_true", help="忽略缓存，强制重查")
    ap.add_argument("--clear-cache", action="store_true", help="清空缓存后继续本次查询")
    ap.add_argument("--cbm-timeout", type=int, default=None, help="单域代码图谱超时秒数（默认 12）")
    ap.add_argument("--no-clarify", action="store_true", help="不生成澄清建议")
    args = ap.parse_args()

    if args.clear_cache:
        print(f"🧹 已清空 {clear_cache()} 个缓存文件")
    if args.cbm_timeout:
        TIMEOUTS["cbm"] = args.cbm_timeout

    q = args.question.strip()
    t_start = time.perf_counter()
    projects = ([args.project] if args.project else
                [x.strip() for x in args.projects.split(",") if x.strip()] if args.projects else
                DEFAULT_PROJECTS[:])
    main_project = projects[0] if projects else "jzjy"

    # ---------- L1 接口库：同步跑（0.01s），字段用于推导更精准的代码检索词
    ifaces, if_err = query_interface(INTERFACE_DB, q)
    iface_fields = query_interface_fields(INTERFACE_DB, [r["id"] for r in ifaces[:3]])
    evidence, impact, conclusion = [], [], ""
    if ifaces:
        for r in ifaces[:5]:
            evidence.append((
                "接口库 .interface_store.db", CONF_EMPIRICAL,
                f"{r['system_name']}｜{r['code']}｜{r['name']}｜方向:{r['direction']}｜"
                f"版本:{r['version']}｜备注:{str(r['description'] or '')[:80]}"))
        # L1.5 订阅矩阵联动：文件编号命中时自动带出「谁订阅了它」
        for r in ifaces[:3]:
            sub = query_subscription(r["code"])
            if sub:
                evidence.append((f"订阅矩阵 .subscription_matrix.db [{r['code']}]",
                                 CONF_EMPIRICAL, sub))
        conclusion = (f"功能号/文件号「{q}」匹配到接口：{ifaces[0]['code']} {ifaces[0]['name']}"
                      if args.code else
                      f"「{q}」命中共 {len(ifaces)} 个接口记录："
                      + "；".join(f"{r['code']} {r['name']}" for r in ifaces[:3]))
    elif if_err:
        conclusion = f"接口库不可用：{if_err}"
    else:
        conclusion = f"「{q}」在接口库未命中（0 结果），转其他域或需人工确认"

    # 同族接口自动扩展：只补一条分组概览证据，不把几十条接口塞进主结论
    # 参数/菜单类概念已按 table_name 精确定位，跳过「融资」等泛词同族扩展（185 条噪声）
    param_query = any(ph in q for ph, _ in PARAM_TABLE_HINT)
    family = (None if (args.code or args.fast or param_query)
              else query_interface_family(INTERFACE_DB, q, ifaces))
    if family and family["total"] > len(ifaces):
        core = family["core"]
        fs = "｜".join(f"{k} {v}条" for k, v in sorted(family["by_system"].items()))
        cap = None if args.verbose else 12
        ex = family["extras"][:cap] if cap else family["extras"]
        samples = "；".join(f"{r['code']} {r['name']}" for r in ex)
        more = ("" if (cap is None or len(family["extras"]) <= cap)
                else f"…(余 {len(family['extras']) - cap} 条，--verbose 看全)")
        evidence.append((
            "接口库 同族自动扩展", CONF_EMPIRICAL,
            f"LIKE '%{core}%' 全库 {family['total']} 条（主命中 {len(ifaces)} + 同族 {len(family['extras'])}）"
            f"｜{fs}｜同族样例: {samples}{more}"))
        conclusion += f"；另有同族接口 {len(family['extras'])} 条（按 %{core}% 自动扩展，见证据链）"

    kw, kw_alt, kw_reason = derive_keywords(q, iface_fields)
    kw_main = project_keyword(q, main_project) or kw
    main_path_filter = PROJECT_PATH_FILTER.get(main_project)
    code_mode = (not args.fast) and bool(kw_main)
    db_kw, db_reason = derive_db_keyword(q, kw)

    # ---------- 构造并行任务
    jobs = []

    def add(name, fn, key=None, ttl=0):
        jobs.append({"name": name, "fn": fn, "key": key, "ttl": ttl})

    if not args.fast:
        add("L0 需求反查", lambda: query_demand_ref(q),
            f"demand|{q}|{OBSIDIAN_DEMAND}", CACHE_TTL["demand"])

    if not args.no_rule:
        add("L4 业务规则 openviking find", lambda: query_openviking(q, "find"),
            f"rule|find|{q}", CACHE_TTL["rule"])

    if code_mode:
        kw_query = kw.replace("_", " ")
        tt = TIMEOUTS["cbm"]
        # 主域用 grep 精准命中真实符号；辅域改 BM25 快查
        # （大项目 grep 全库约 12-22s，会拖垮并行关键路径）
        add(f"L2 代码图谱 CBM[{main_project}] search_code({kw_main})",
            lambda: query_cbm_code(main_project, kw_main, path_filter=main_path_filter),
            f"cbm|code|{main_project}|{kw_main}|pf{main_path_filter}|t{tt}", CACHE_TTL["cbm"])
        # 备选词默认不跑（已实证在主域 0 命中，多一个全库 grep 会争抢 IO 拖慢关键路径）
        if kw_alt and args.verbose:
            add(f"L2 代码图谱 CBM[{main_project}] 备选({kw_alt[0]})",
                lambda: query_cbm_code(main_project, kw_alt[0], path_filter=main_path_filter),
                f"cbm|code|{main_project}|{kw_alt[0]}|pf{main_path_filter}|t{tt}", CACHE_TTL["cbm"])
        for pr in projects[1:]:
            add(f"L2 代码图谱 CBM[{pr}] search_graph({kw_query})",
                lambda pr=pr: query_cbm(pr, kw_query, "search", timeout=min(tt, 8)),
                f"cbm|graph|{pr}|{kw_query}|t{tt}", CACHE_TTL["cbm"])
        if args.trace and ASCII_IDENT.match(q):
            add("L2 影响范围 trace_path inbound",
                lambda: query_cbm(main_project, q, "trace", "inbound"),
                f"cbm|trace|{main_project}|{q}|t{tt}", CACHE_TTL["cbm"])

    if not args.no_db and not args.fast:
        if args.db_table:
            add(f"L3 数据库实证 dbq[{main_project}:{args.db_table}]",
                lambda: query_db(main_project, table=args.db_table),
                f"db|table|{main_project}|{args.db_table}", CACHE_TTL["db"])
        elif args.db_sql:
            add(f"L3 数据库实证 dbq[{main_project} SQL]",
                lambda: query_db(main_project, sql=args.db_sql), None, 0)
        elif args.db_search_table:
            add(f"L3 数据库实证 dbq[{main_project} 搜表 {args.db_search_table}]",
                lambda: query_db(main_project, search_table=args.db_search_table),
                f"db|search|{main_project}|{args.db_search_table}", CACHE_TTL["db"])
        else:
            for pr in projects:
                if pr in DBQ_PROFILES:
                    add(f"L3 数据库实证 dbq[{pr}] 搜表 {db_kw}",
                        lambda pr=pr: query_db(pr, search_table=db_kw),
                        f"db|search|{pr}|{db_kw}", CACHE_TTL["db"])

    if args.code and not code_mode:
        add(f"L2 代码图谱 CBM[{main_project}] search_graph",
            lambda: query_cbm(main_project, q, "search"),
            f"cbm|graph|{main_project}|{q}", CACHE_TTL["cbm"])

    # ---------- 并行执行 + 归集证据
    results = run_jobs(jobs, refresh=args.refresh)
    limit = None if args.verbose else DETAIL_LIMIT

    def clip(s):
        return s if (limit is None or s is None) else str(s)[:limit]

    def val(name):
        r = results.get(name)
        return r[0] if r else None

    dep = val("L0 需求反查")
    if dep and not str(dep).startswith(("(demand", "(D", "(需求反查超时")):
        dep_txt = str(dep)
        if "### 业务概念" in dep_txt:          # 去掉脚本固定模板头，只留反查命中
            dep_txt = "### 业务概念" + dep_txt.split("### 业务概念", 1)[1]
        evidence.append(("需求依赖反查 demand_dep_find.py", CONF_TRACEABLE, clip(dep_txt)))

    cbm_values = []
    for name, (v, _, _) in sorted(results.items()):
        if name.startswith("L2"):
            cbm_values.append(v)
        if name.startswith("L2") and v and not str(v).startswith("(CBM"):
            txt = str(v)
            noise = NOISE_CBM.search(txt) and ".cpp" not in txt
            detail = ("(命中均为 makefile/锁字段等噪声，已过滤；建议用英文函数名重查)"
                      if noise else clip(v))
            if "search_graph" in name and not noise:
                detail = "【辅域 BM25 快查，符号级弱相关，需英文函数名精查】" + str(detail)
            evidence.append((name, CONF_TRACEABLE, detail))
            if "(CBM 0 命中)" in txt:
                impact.append(f"{name}：0 命中，代码层待确认")
        elif name.startswith("L2") and v and "超时" in str(v):
            impact.append(f"{name}：{v}")
        elif name.startswith("L3") and v and not str(v).startswith("(dbq"):
            evidence.append((name, CONF_EMPIRICAL, clip(v)))
        elif name.startswith("L4") and v and not str(v).startswith("(openviking"):
            evidence.append((name, CONF_TRACEABLE, clip(v)))

    clarification = [] if args.no_clarify else build_clarification(
        q, ifaces, cbm_values, dep, projects, kw, code_mode, family,
    )

    total = time.perf_counter() - t_start
    extra = {
        "total": round(total, 3),
        "timings": {k: round(v[1], 3) for k, v in results.items()},
        "cache_hits": sum(1 for v in results.values() if v[2]),
        "job_count": len(jobs), "projects": projects,
        "quiet": args.quiet, "show_timings": args.timings,
        "clarification": clarification,
        "keywords": {"primary": kw, "main": kw_main, "alternatives": kw_alt,
                      "reason": kw_reason, "path_filter": main_path_filter,
                      "db": db_kw, "db_reason": db_reason},
        "family": ({"core": family["core"], "total": family["total"],
                    "by_system": family["by_system"]} if family else None),
    }
    print(render(conclusion, evidence, impact, "json" if args.json else "text", extra))
    if args.json:
        sys.exit(0)


if __name__ == "__main__":
    main()
