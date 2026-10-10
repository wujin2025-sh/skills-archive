#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epic_stats.py — 史诗统计脚本
=============================================
按史诗编号（PG202204-xxxx / E 开头）统计该史诗下的需求数量、涉及系统、状态分布等指标。

数据源：复用车宽表 wide-table-query 技能的导出能力（浏览器物理导出 Excel 至
    wide-table-query/scripts/downloads/exported_<史诗编号>.xlsx），
直接读取导出的 Excel 做统计（规避 wide_table_query.py 自身"有效匹配 0 行"的判定缺陷）。

依赖: openpyxl（系统 python3 已装）；wide_table_query.py 运行期间需要 playwright
用法:
    python3 epic_stats.py PG202204-0236
    python3 epic_stats.py PG202204-0236 --fresh      # 强制重新从大宽表导出
    python3 epic_stats.py PG202204-0236 --system 集中清算系统   # 仅统计指定系统
    python3 epic_stats.py PG202204-0236 --status 结束           # 仅统计指定 Story 状态
    python3 epic_stats.py PG202204-0236 --json                  # JSON 输出（机器可读）
    python3 epic_stats.py PG202204-0236 --output epic.md        # 同时写入 Markdown 文件
    python3 epic_stats.py PG202204-0236 --narrative  # 生成季度述职内容稿（对齐示例格式）
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from openpyxl import load_workbook

BASE_DIR = Path(__file__).resolve().parent
CANDIDATE_WIDE_DIRS = [
    Path.home() / ".chat/skills/wide-table-query/scripts",
    Path.home() / ".workbuddy/skills/wide-table-query/scripts",
]

EPIC_COL = "史诗编号"
REQ_COL = "需求编号"
TITLE_COL = "Story标题"
SYSTEM_COL = "Story系统"
STATUS_COL = "Story状态"

CACHE_TTL = 3600  # 缓存 Excel 有效期（秒），1 小时内直接复用


def find_wide_scripts():
    for p in CANDIDATE_WIDE_DIRS:
        if (p / "wide_table_query.py").exists():
            return p
    return None


def ensure_xlsx(epic_no, fresh=False):
    """优先复用缓存 Excel，必要时调用 wide_table_query.py 重新导出。返回 xlsx 路径。"""
    wide = find_wide_scripts()
    if wide is None:
        raise RuntimeError("未找到 wide-table-query 技能（wide_table_query.py），请先安装该技能")
    download_dir = wide / "downloads"
    download_dir.mkdir(exist_ok=True)
    xlsx = download_dir / f"exported_{epic_no}.xlsx"
    if not fresh and xlsx.exists():
        age = time.time() - xlsx.stat().st_mtime
        if age < CACHE_TTL:
            print(f"[缓存] 复用 {xlsx.name}（{age:.0f}s 前导出）", flush=True, file=sys.stderr)
            return xlsx
    print(f"[导出] 调用 wide_table_query.py 拉取史诗 {epic_no} 数据...", flush=True, file=sys.stderr)
    r = subprocess.run(
        [sys.executable, "wide_table_query.py", epic_no],
        cwd=str(wide), capture_output=True, text=True, timeout=420,
    )
    tail = (r.stdout or "").strip()[-800:]
    if tail:
        print(f"[导出] {tail.splitlines()[-1]}", flush=True, file=sys.stderr)
    if r.returncode != 0:
        print(r.stderr[-800:], file=sys.stderr)
    if not xlsx.exists():
        raise RuntimeError(f"导出失败：未生成 {xlsx}")
    return xlsx


def load_rows(xlsx_path):
    """读取 Excel 全部行，返回 (表头索引字典, 数据行列表)。"""
    wb = load_workbook(xlsx_path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return {}, []
    header = rows[0]
    idx = {name: i for i, name in enumerate(header)}
    return idx, rows[1:]


def collect(epic_no, fresh=False):
    """拉取并解析史诗数据，返回去重后的需求字典与全部记录数。"""
    xlsx = ensure_xlsx(epic_no, fresh)
    idx, rows = load_rows(xlsx)
    if not idx:
        raise RuntimeError(f"{xlsx.name} 为空或表头缺失")
    reqs = {}
    total_records = 0
    for r in rows:
        if r[idx.get(EPIC_COL)] != epic_no:
            continue
        rid = r[idx.get(REQ_COL)]
        if not rid:
            continue
        total_records += 1
        req = reqs.setdefault(
            rid,
            {"title": r[idx.get(TITLE_COL)], "systems": set(), "status": set(), "records": 0},
        )
        req["records"] += 1
        sys_name = r[idx.get(SYSTEM_COL)]
        st = r[idx.get(STATUS_COL)]
        if sys_name:
            req["systems"].add(sys_name)
        if st:
            req["status"].add(st)
    return reqs, total_records


def filter_reqs(reqs, system=None, status=None):
    out = {}
    for rid, req in reqs.items():
        if system and system not in req["systems"]:
            continue
        if status and status not in req["status"]:
            continue
        out[rid] = req
    return out


def build_report(epic_no, reqs, total_records):
    """生成结构化统计报告。"""
    n_req = len(reqs)
    # 过滤后按需求重新统计 Story 记录数（避免 --system/--status 后口径失真）
    total_records = sum(req.get("records", 0) for req in reqs.values())
    # 系统维度：系统 -> 涉及需求数
    sys_counter = {}
    for req in reqs.values():
        for s in req["systems"]:
            sys_counter[s] = sys_counter.get(s, 0) + 1
    # 状态分布：状态名 -> 出现需求数
    status_counter = {}
    for req in reqs.values():
        for st in req["status"]:
            status_counter[st] = status_counter.get(st, 0) + 1
    # 明细
    details = []
    for rid in sorted(reqs):
        req = reqs[rid]
        details.append({
            "需求编号": rid,
            "标题": req["title"],
            "涉及系统数": len(req["systems"]),
            "涉及系统": sorted(req["systems"]),
            "Story状态": sorted(req["status"]),
        })
    return {
        "史诗编号": epic_no,
        "需求数量": n_req,
        "记录数量": total_records,
        "涉及系统数量": len(sys_counter),
        "系统分布": dict(sorted(sys_counter.items(), key=lambda kv: (-kv[1], kv[0]))),
        "状态分布": dict(sorted(status_counter.items(), key=lambda kv: (-kv[1], kv[0]))),
        "需求明细": details,
    }


def render_markdown(report):
    epic = report["史诗编号"]
    lines = []
    lines.append(f"# 史诗 {epic} 统计")
    lines.append("")
    lines.append(f"- **需求数量**：{report['需求数量']} 个（Story 记录 {report['记录数量']} 条）")
    lines.append(f"- **涉及系统**：{report['涉及系统数量']} 个")
    lines.append("")
    lines.append("## 涉及系统分布")
    lines.append("")
    lines.append("| 系统 | 涉及需求数 |")
    lines.append("|------|-----------|")
    for s, c in report["系统分布"].items():
        lines.append(f"| {s} | {c} |")
    lines.append("")
    lines.append("## Story 状态分布")
    lines.append("")
    lines.append("| Story状态 | 涉及需求数 |")
    lines.append("|----------|-----------|")
    for st, c in report["状态分布"].items():
        lines.append(f"| {st} | {c} |")
    lines.append("")
    lines.append("## 需求明细")
    lines.append("")
    lines.append("| # | 需求编号 | 需求标题 | 涉及系统 | Story状态 |")
    lines.append("|---|----------|----------|----------|-----------|")
    for i, d in enumerate(report["需求明细"], 1):
        systems = "、".join(d["涉及系统"])
        status = "、".join(d["Story状态"])
        lines.append(f"| {i} | {d['需求编号']} | {d['标题'] or '（标题为空）'} | {systems} | {status} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------
# 述职内容生成模式（--narrative）
# ---------------------------------------------------------------

# 已结束/上线类 Story 状态（其余视为推进中）
DONE_STATUS = {"结束", "终止", "已上线", "完成", "上线", "结束/上线"}

# 史诗业务高频词词表（用于从需求标题提炼主线关键词）
BUSINESS_KEYWORDS = [
    "历史", "迁移", "查询", "文件", "接口", "切换", "订阅", "基线",
    "清算", "交易", "委托", "银证", "担保", "标的证券", "征信", "流水",
    "数据", "指标", "报送", "监控", "上线", "割接", "导出",
]


def normalize_epic_no(no):
    """史诗编号容错：G202204-0236 → PG202204-0236（补 P），并去空白。"""
    no = no.strip()
    if re.match(r"^G20\d{4}-\d{3,4}$", no):
        return "P" + no
    return no


def collect_keywords(reqs, top=6):
    """从需求标题统计业务高频关键词。"""
    cnt = Counter()
    for req in reqs.values():
        t = req["title"] or ""
        for kw in BUSINESS_KEYWORDS:
            if kw in t:
                cnt[kw] += 1
    return [w for w, c in cnt.most_common(top) if c >= 2]


def progress_stats(reqs):
    """按需求统计 已结束/上线 与 推进中 数量，返回 (done, ongoing, ongoing_list)。"""
    done, ongoing = 0, 0
    ongoing_list = []
    for rid in sorted(reqs):
        req = reqs[rid]
        sts = set(req["status"])
        if sts and sts <= DONE_STATUS:
            done += 1
        else:
            ongoing += 1
            ongoing_list.append(f"{rid} {req['title'] or ''}".strip())
    return done, ongoing, ongoing_list


# 史诗业务场景定义（--narrative 场景识别用）：按需求标题关键词加权评分取最高分场景
# 字段说明：intro=引言目的句（以「为」开头、逗号结尾）；bg=动作分解+升华（结尾带句号）；
#   p1_head/p2_head/p3_head=（一）（二）（三）正文首句；p2_mode=（二）三方协同主体；
#   th2/th3=（二）（三）小节标题量化亮点；outro1=（一）尾句零中断表述（缺省用通用句）
SCENARIOS = [
    {
        "name": "历史数据迁移",
        "kws": ["历史", "迁移", "割接", "不再归档", "切换采集", "历史数据"],
        "main": "集中交易历史查询与历史数据迁移出集中交易",
        "intro": "为规范历史查询管理、减轻集中交易上场压力，并为后续信创改造预留干净基线，",
        "bg": "将分散的历史数据服务统一收口至清算侧，老集中交易历史数据不再归档、日终资金股份流水不再上场，同时推动大数据等下游系统由集中交易总控采集切换至集中清算采集，从根上卸下主系统冗余负荷、理清外围依赖，为集中交易未来信创切换清理外围耦合。",
        "p1_head": "牵头完成外围历史查询接口、委托/沪港通委托、银证转账、担保费率、标的证券等历史数据迁移对接与方案设计，形成外围接口迁移完整基线，历史文件分批落地。",
        "outro1": "迁移期间查询响应无缝衔接、业务零中断",
        "p2_head": "针对历史数据迁移涉及下游系统多、数据表数量大（300余张）、各系统排期与联调响应滞后等困难，主动牵头打破部门壁垒，建立「跟踪邮件 + 在线文档 + 逐系统提醒」机制，",
        "p2_mode": "主系统、清算侧、周边系统",
        "th2": "300余张表打破壁垒建三方协同",
        "p3_head": "牵头推进300余张历史数据表梳理与接口/文件订阅矩阵基线，夯实切换基线工程。BCP 文件迁移已实现下游 6大系统表级适配与分批上线，覆盖资金流水、委托表、信用客户融资融券明细表、担保费率表、标的证券等核心表，统一「切清算/切三方/切参数后台」口径，按 7/8/9 月多批次有序上线。",
        "th3": "6大下游系统表级适配上线率近100%",
        "closing_ok": "集中交易逐步暂停历史数据服务，集中清算不再上场集中交易历史数据。",
    },
    {
        "name": "融资融券优化",
        "kws": ["两融", "融资融券", "信用账户", "担保", "维保", "卖券还款", "货基", "债基", "融资负债", "融券"],
        "main": "融资融券交易与还款链路专项优化",
        "intro": "为优化两融交易与还款资金链路、提升信用业务处理效率，并为后续业务扩展预留统一口径，",
        "bg": "围绕信用账户交易、还款与资金使用等环节开展专项优化，将货基债基卖券还款、大宗/盘后定价交易、融券卖出资金使用等场景逐步纳入「交易-还款-清算」全链路统一口径，完善卖券还款、融券资金使用、大宗/盘后定价交易等业务逻辑，从根上消除跨柜台口径差异、理清资金占用边界，为两融业务规模化运行夯实一致性基线。",
        "p1_head": "牵头承接两融交易与还款链路优化需求，覆盖货基债基卖券还款、大宗/盘后定价交易、融券卖出资金使用等场景，形成完整的业务逻辑闭环。",
        "outro1": "交付期间业务平稳、业务零中断",
        "p2_head": "针对两融业务涉及集中交易、集中清算、低延时柜台等多系统联动、口径一致性要求高等困难，主动牵头打破跨系统边界，建立「跨系统口径对齐 + 逐场景责任人确认」机制，统一竞价与大宗交易等场景处理口径，",
        "p2_mode": "集中交易、集中清算、低延时柜台",
        "th2": "多系统联动统一口径建三方协同",
        "p3_head": "牵头推进两融业务逻辑梳理与跨系统口径对齐，夯实「交易-还款-清算」全链路基线，实现同标被转还款、货基债基资金使用等场景的跨柜台/跨清算一致性，按多批次有序交付。",
        "th3": "交易-还款-清算全链路夯实基线",
        "closing_ok": None,
    },
    {
        "name": "清算结算改造",
        "kws": ["清算", "结算", "交收", "日终", "流水", "对账"],
        "main": "清算结算链路改造与数据贯通",
        "intro": "为贯通清算结算链路数据流转、提升日终处理效率，并为上下游数据衔接预留一致口径，",
        "bg": "围绕清算结算链路开展改造，贯通交易、清算、结算各环节数据流转，将流水、对账、日终处理等环节纳入统一处理基线，提升日终处理效率与数据一致性，从根上减少跨系统数据搬运、理清数据流向，为清算效率整体提升夯实基线。",
        "p1_head": "牵头承接清算结算链路改造需求，覆盖流水、对账、日终处理等环节，夯实数据贯通基线。",
        "outro1": "交付期间业务平稳、业务零中断",
        "p2_head": "针对清算改造涉及上下游系统多、口径调整影响面大等困难，主动牵头多方协同，建立「口径清单 + 逐环节确认」机制，明确各环节处理口径，",
        "p2_mode": "集中交易、集中清算、下游接收系统",
        "th2": "多环节口径统一建跨系统协同",
        "p3_head": "牵头推进清算链路口径梳理与数据贯通验证，覆盖核心环节，按多批次有序交付。",
        "th3": "清算链路数据贯通夯实基线",
        "closing_ok": None,
    },
    {
        "name": "接口文件服务",
        "kws": ["接口", "文件", "报送", "订阅", "导出", "行情"],
        "main": "接口与文件服务能力升级",
        "intro": "为保障外围接口与文件数据流转的稳定及时合规，并为业务高峰期数据交互预留可靠通道，",
        "bg": "围绕外围接口与文件服务开展升级，将报送、订阅、导出、行情等场景统一纳入服务基线管理，保障数据流转的稳定、及时与合规，从根上减少手工干预、理清对端依赖，为外围数据服务持续稳定运行夯实基线。",
        "p1_head": "牵头承接接口/文件类需求，覆盖报送、订阅、导出、行情等场景，完成对接与方案设计，形成交付基线。",
        "outro1": "交付期间数据流转稳定、业务无感",
        "p2_head": "针对接口改造涉及对端系统多、排期协调难等困难，主动牵头建立「联调计划 + 逐系统责任人」机制，",
        "p2_mode": "主服务端、对端系统、监管报送侧",
        "th2": "接口文件基线统一建多方协同",
        "p3_head": "牵头推进接口/文件服务基线梳理与多批次上线，保障数据流转稳定。",
        "th3": "数据流转稳定有序夯实基线",
        "closing_ok": None,
    },
]
GENERIC_SCENARIO = {
    "name": "专项能力建设",
    "main": "【主线（需求标题关键词提示，人工提炼）】",
    "intro": "为保障相关业务能力、支撑核心链路稳定运行，",
    "bg": "围绕【业务主线】开展专项建设，将【关键场景】逐步纳入统一基线管理，保障业务平稳有序，从根上理清依赖、夯实基础，为后续扩展演进清理铺垫。",
    "p1_head": "牵头完成需求承接与方案设计，形成交付基线，分批落地。",
    "outro1": "交付期间业务平稳、业务零中断",
    "p2_head": "针对涉及系统多、跨部门协同复杂等困难，主动牵头建立进度跟踪与逐系统责任人机制，",
    "p2_mode": "主系统、配合系统、下游接收侧",
    "th2": "跨系统协同建长效交付机制",
    "p3_head": "牵头推进工作项梳理与交付基线建设，按多批次有序交付。",
    "th3": "交付基线夯实有序推进",
    "closing_ok": None,
}

# 业务主题词表（--narrative 需求主题互斥归组用）：每个需求按首个命中主题归组，未命中进「其他」
THEME_GROUPS = [
    ("货基/债基资金使用", ("货基", "债基", "货基卖券", "卖出货基", "买入货基")),
    ("大宗/盘后定价交易", ("大宗", "盘后定价")),
    ("卖券还款与负债偿还", ("还款", "偿还", "融资负债", "卖券还款")),
    ("融券卖出与资金占用", ("融券", "融券卖出")),
    ("历史数据迁移", ("历史", "迁移", "割接", "不再归档")),
    ("接口/文件/查询服务", ("接口", "文件", "查询", "报送", "订阅", "导出", "行情")),
    ("风控与担保管理", ("风控", "担保", "维保", "冻结", "占比", "保证金", "标的证券")),
]

# 主题归组 → 具名场景映射（THEME_GROUPS 为互斥首命中，比词频更抗泛化词污染）
THEME_SCENARIO = {
    "货基/债基资金使用": "融资融券优化",
    "大宗/盘后定价交易": "融资融券优化",
    "卖券还款与负债偿还": "融资融券优化",
    "融券卖出与资金占用": "融资融券优化",
    "历史数据迁移": "历史数据迁移",
    "接口/文件/查询服务": "接口文件服务",
    "风控与担保管理": "融资融券优化",
}


def detect_scenario(reqs, themes=None):
    """识别史诗业务场景：优先取主题互斥归组的最大组映射场景；无映射/平局时按标题关键词加权评分兜底（无命中回落 GENERIC_SCENARIO）。"""
    if themes:
        for name, num, _, _ in sorted(themes, key=lambda x: -x[1]):
            if name in THEME_SCENARIO:
                for sc in SCENARIOS:
                    if sc["name"] == THEME_SCENARIO[name]:
                        return sc
                break
    text = "".join((req["title"] or "") for req in reqs.values())
    best, best_score = None, 0
    for sc in SCENARIOS:
        score = sum(text.count(k) for k in sc["kws"])
        if score > best_score:
            best, best_score = sc, score
    return best or GENERIC_SCENARIO


def theme_summary(reqs):
    """按主题词表对需求做互斥归组（首个命中），返回 [(主题名, 数量, [需求编号], 代表标题)]，未归组进「其他」。"""
    groups, used = [], set()
    for name, kws in THEME_GROUPS:
        hits = []
        for rid, req in sorted(reqs.items()):
            if rid in used:
                continue
            t = req["title"] or ""
            if any(k in t for k in kws):
                hits.append((rid, t))
                used.add(rid)
        if hits:
            groups.append((name, len(hits), [r for r, _ in hits], hits[0][1]))
    rest = [(rid, req["title"] or "") for rid, req in sorted(reqs.items()) if rid not in used]
    if rest:
        groups.append(("其他", len(rest), [r for r, _ in rest], rest[0][1]))
    return groups


def _short(t, n=22):
    """长标题截断显示（PPT 素材用）。"""
    t = (t or "").replace("【", "").replace("】", "")
    return t if len(t) <= n else t[:n] + "…"


def render_ppt_material(epic_no, reqs, total_records, sc, themes, sys_list, done, ongoing, done_rate, main_line, ongoing_list):
    """核心专项 PPT 素材版：要点式、可拆页，每块可独立作为一页素材。"""
    n_req, n_sys = len(reqs), len(sys_list)
    lines = []
    lines.append(f"【核心专项 · PPT 素材】（史诗 {epic_no}）")
    lines.append("━" * 30)
    lines.append(f"▍专项主线｜{main_line}")
    lines.append(f"▍一句背景｜{sc['bg']}")
    lines.append("")
    lines.append("▍亮点数据")
    lines.append(f"　承接需求 {n_req} 个 ｜ 覆盖系统 {n_sys} 个 ｜ Story {total_records} 条")
    lines.append(f"　已结束/上线 {done} 个（{done_rate}%） ｜ 推进中 {ongoing} 个")
    lines.append("")
    lines.append("▍承接需求（按主题归纳）")
    for name, num, rids, rep in themes[:6]:
        lines.append(f"　▸ {name}（{num} 项）：{_short(rep)}（{'、'.join(rids[:4])}{'…' if len(rids) > 4 else ''}）")
    lines.append("")
    lines.append(f"▍覆盖系统（{n_sys} 个）")
    lines.append("　" + "、".join(_clean_sys(s) for s in sys_list))
    lines.append("")
    lines.append("▍推进状态")
    lines.append(f"　{done} 个已结束/上线；{ongoing} 个推进中")
    lines.append("")
    lines.append("▍后续")
    if ongoing_list:
        lines.append("　" + "；".join(_short(t, 18) for t in ongoing_list[:3]) + " 等推进中")
    else:
        lines.append("　已全部结束，进入稳定运行与持续优化阶段")
    lines.append("━" * 30)
    lines.append("（数据为自动提取，业务叙述请按专项实际复核后使用）")
    return "\n".join(lines)


def _current_quarter():
    """按当前月份返回中文季度（述职场景固定季度口径）。"""
    month = datetime.now().month
    return {1: "一季度", 2: "二季度", 3: "三季度", 4: "四季度"}[(month - 1) // 3 + 1]


def _clean_sys(name):
    """清洗系统名中的临时/环境标注脏后缀（述职正文展示用，附注区保留全量原始名）。"""
    for pat in ("(虚拟)", "（虚拟）", "(Y公司)", "（Y公司）", "(临时)", "（临时）", "(新)", "（新）"):
        name = name.replace(pat, "")
    return name


def _display_systems(sys_list, max_n=8):
    """述职正文系统清单：清洗后缀 + 按涉及需求数降序取前 N + 「等」，附注区保留全量。"""
    shown = [_clean_sys(s) for s in sys_list[:max_n]]
    s = "、".join(shown)
    return s + ("等" if len(sys_list) > max_n else "")


def render_narrative(epic_no, reqs, total_records):
    """生成季度述职内容稿（完整叙述版 + 核心专项 PPT 素材版，两段输出）。

    - 基于史诗真实需求总结：场景加权识别 + 需求主题互斥归组，杜绝千篇一律模板；
    - 统计数字自动填充；无法从史诗统计推导的业务细节以【…】占位供人工校准；
    - 完整叙述版供述职讲稿使用；PPT 素材版要点式、可拆页，直接作为核心专项素材。
    """
    n_req = len(reqs)
    n_sys = len({s for req in reqs.values() for s in req["systems"]})
    sys_counter = Counter()
    for req in reqs.values():
        for s in req["systems"]:
            sys_counter[s] += 1
    sys_list = [s for s, _ in sys_counter.most_common()]  # 按涉及需求数降序
    done, ongoing, ongoing_list = progress_stats(reqs)
    done_rate = round(done / n_req * 100, 1) if n_req else 0
    kws = collect_keywords(reqs)
    themes = theme_summary(reqs)
    sc = detect_scenario(reqs, themes)
    top_sys_names = "、".join(sys_list[:4])

    # 主线：场景自带主线优先；GENERIC 场景用需求标题高频关键词提示
    if sc.get("main", "").startswith("【"):
        main_line = "、".join(kws) if kws else sc["main"]
    else:
        main_line = sc["main"]

    # —— 完整叙述版（基于真实主题归纳） ——
    theme_phrase = "、".join(f"{name}（{num} 项）" for name, num, _, _ in themes[:5])
    if ongoing_list:
        if sc.get("closing_ok"):
            closing = f"后续 {sc['closing_ok']}\n另有 {len(ongoing_list)} 个需求推进中（明细见附注）。"
        else:
            closing = "后续 " + "；".join(_short(t, 18) for t in ongoing_list[:3]) + " 等推进中。"
    else:
        closing = f"后续 {sc['closing_ok']}" if sc.get("closing_ok") else "后续 相关需求均已结束，进入稳定运行与持续优化阶段。"

    lines = []
    lines.append(f"【季度述职内容】（史诗 {epic_no} 自动生成稿：数据自动填充，【…】处按史诗实际校准）")
    lines.append("")
    lines.append(f"{sc.get('intro', '为保障相关业务能力、支撑核心链路稳定运行，')}{_current_quarter()}我们重点推进了{main_line}：{sc['bg']}")
    lines.append("")
    lines.append(f"（一）需求承接无缝衔接，{n_req}个需求覆盖{n_sys}个系统业务无感")
    lines.append(f"　{sc['p1_head']} 累计承接 {n_req} 个需求，覆盖 {n_sys} 个系统（{_display_systems(sys_list)}），{sc.get('outro1', '交付期间业务平稳、业务零中断')}。")
    lines.append("")
    lines.append(f"（二）主动破局协同提效，{sc.get('th2', '跨系统协同建长效交付机制')}")
    lines.append(f"　{sc['p2_head']} 推动各系统明确排期配合联调，形成{sc.get('p2_mode', '主系统、配合系统、下游接收侧')}三方协同的跨团队模式，交付能力有效提升。")
    lines.append("")
    lines.append(f"（三）统筹协调全局梳理，{sc.get('th3', '交付基线夯实有序推进')}")
    lines.append(f"　{sc['p3_head']} 已实现下游 {n_sys} 大系统适配，{done} 个需求已结束/上线（{done_rate}%），{ongoing} 个推进中。")
    lines.append("")
    lines.append(closing)
    lines.append("")
    lines.append("—— 自动提取数据附注（供核对，勿写入正文） ——")
    lines.append(f"- 需求 {n_req} 个（Story 记录 {total_records} 条），已结束/上线 {done} 个（{done_rate}%），推进中 {ongoing} 个")
    lines.append(f"- 涉及系统 {n_sys} 个（按涉及需求数降序）：{'、'.join(sys_list)}")
    lines.append(f"- 场景识别：{sc['name']}；主线关键词：{main_line}")
    if ongoing_list:
        lines.append("- 推进中需求：")
        lines.extend(f"  - {t}" for t in ongoing_list)
    narrative = "\n".join(lines)

    ppt = render_ppt_material(epic_no, reqs, total_records, sc, themes, sys_list, done, ongoing, done_rate, main_line, ongoing_list)
    return narrative + "\n\n" + ppt


def main():
    ap = argparse.ArgumentParser(description="史诗需求统计")
    ap.add_argument("epic_no", help="史诗编号，如 PG202204-0236（G 开头自动补 P 容错）")
    ap.add_argument("--fresh", action="store_true", help="强制重新从大宽表导出（忽略缓存）")
    ap.add_argument("--system", help="仅统计指定系统")
    ap.add_argument("--status", help="仅统计指定 Story 状态")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--output", "-o", help="同时写入 Markdown 文件")
    ap.add_argument("--narrative", action="store_true", help="生成季度述职内容稿（对齐示例格式，自动填充统计数据，业务叙述以【…】占位）")
    args = ap.parse_args()
    args.epic_no = normalize_epic_no(args.epic_no)

    try:
        reqs, total_records = collect(args.epic_no, fresh=args.fresh)
        reqs = filter_reqs(reqs, system=args.system, status=args.status)
        if args.narrative:
            print(render_narrative(args.epic_no, reqs, total_records))
            return
        report = build_report(args.epic_no, reqs, total_records)
    except Exception as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        md = render_markdown(report)
        print(md)
        if args.output:
            Path(args.output).write_text(md, encoding="utf-8")
            print(f"\n[写入] {args.output}")


if __name__ == "__main__":
    main()
