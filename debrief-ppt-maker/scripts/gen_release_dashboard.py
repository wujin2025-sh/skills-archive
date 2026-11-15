# -*- coding: utf-8 -*-
"""「版本集成发布情况」季度看板：生成 16:9 SVG + 预览 HTML + 述职内页片段。

数据源：全连接文档中心在线表格《各系统发版汇总》
        https://www.gtht.com.cn/jswps/weboffice/l/spULaQnvVBFlD
取数口径（见 SKILL.md「版本集成发布情况」页）：
  - 按季度取 3 个工作表 `各系统{M}月版本`（如 Q3 = 7/8/9 月）
  - 筛选「发版负责人」含指定人（默认 吴进）
  - A 列系统名因合并单元格留空时向下继承
  - 版本数 = 有效行数；发版次数 = 「发版次数」列求和
  - 「是否有发版问题」仅作参考，空值不计入「已登记」

用法：
  python gen_release_dashboard.py --xlsx <下载表> --quarter 2026Q3 --months 7,8,9 \
      --owner 吴进 --out <产物目录>
"""
import os
import re
import json
import calendar
import argparse
import collections
import openpyxl

DOC_URL = "https://www.gtht.com.cn/jswps/weboffice/l/spULaQnvVBFlD"
DEFAULT_XLSX = "/Volumes/Macintosh HD_Data/Gemini/PPT/docs/各系统发版汇总.xlsx"
DEFAULT_OUT = "/Volumes/Macintosh HD_Data/Gemini/PPT/docs"

DEEP = "#1F497D"
BLUE = "#0C72BB"
TITLE = "#004E97"
RED = "#D9232E"
ICE = "#E6F1FB"
GRAY = "#666666"
LIGHT = "#999999"
GRID = "#DCE9F7"
LINE = "#B4C6DA"
SOFT = "#85B7EB"
PALE = "#B8C5D6"

quarter = "2026Q3"
STATE_TEXT = "季度已完结"


def load_rows(xlsx, months, owner):
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    name_map = {n.strip(): n for n in wb.sheetnames}
    allrows, mine = [], []
    for m in months:
        key = "各系统%d月版本" % m
        if key not in name_map:
            raise KeyError("缺少工作表：%s（现有：%s）" % (key, ", ".join(name_map)))
        ws = wb[name_map[key]]
        sysname = ""
        for r in range(2, ws.max_row + 1):
            v = [ws.cell(r, c).value for c in range(1, 10)]
            a = str(v[0]).strip() if v[0] else ""
            if a:
                sysname = a
            ver = str(v[1]).strip() if v[1] else ""
            who = str(v[3]).strip() if v[3] else ""
            if not ver and not who:
                continue
            times = v[5] if isinstance(v[5], (int, float)) else 0
            item = dict(month=m, system=sysname, ver=ver, owner=who, times=int(times),
                        problem=str(v[6] or "").strip())
            allrows.append(item)
            if owner in who:
                mine.append(item)
    return allrows, mine


def stat(allrows, mine, months, owner):
    by_month = {m: (sum(1 for x in mine if x["month"] == m),
                    sum(x["times"] for x in mine if x["month"] == m)) for m in months}
    by_system = collections.Counter(x["system"] for x in mine)
    registered = [x for x in mine if x["problem"] in ("否", "有", "是")]
    problems = [x for x in registered if x["problem"] in ("有", "是")]
    share = len(mine) / len(allrows) * 100 if allrows else 0
    return dict(
        total=len(mine), times=sum(x["times"] for x in mine),
        by_month=by_month, by_system=by_system,
        registered=len(registered), problems=len(problems),
        all_versions=len(allrows), share=share,
        systems=len(by_system), owner=owner,
    )


def sys_note(d):
    """系统名说明按当季原表动态生成：在线表被维护者改名时脚注不会残留旧系统名。"""
    names = [k for k, _ in d["by_system"].most_common(4)]
    return "系统名按原表保留，未做归并：%s" % (" / ".join(names) if names else "（无）")


def month_line(m, d):
    """月度明细卡的系统构成文案"""
    sysc = collections.Counter(x["system"] for x in d["mine"] if x["month"] == m)
    return " · ".join("%s %d" % (k, v) for k, v in sysc.most_common())


def build_svg(d, months, quarter, downloaded):
    s = []
    a = s.append
    a('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720" '
      'font-family="PingFang SC, Microsoft YaHei, Helvetica, Arial, sans-serif" role="img">')
    a('<title>版本集成发布情况 · %s</title>' % quarter)
    a('<desc>%s 发版负责人%s共负责%d个版本、累计发版%d次，附月度分布与系统分布</desc>'
      % (quarter, d["owner"], d["total"], d["times"]))
    a('<rect width="1280" height="720" fill="#FFFFFF"/>')
    a('<rect x="0" y="0" width="1280" height="88" fill="%s"/>' % DEEP)
    a('<text x="48" y="57" fill="#FFFFFF" font-size="34" font-weight="700">版本集成发布情况</text>')
    a('<text x="1232" y="55" fill="#CFE2F5" font-size="16" text-anchor="end">%s · 发布负责人 %s · %s</text>'
      % (quarter, d["owner"], STATE_TEXT))
    a('<text x="48" y="119" fill="%s" font-size="13">数据来源：全连接文档中心《各系统发版汇总》 %s</text>'
      % (GRAY, DOC_URL))

    def kpi(x, label, value, note, red=False):
        a('<rect x="%d" y="145" width="282" height="116" rx="8" fill="%s"/>' % (x, ICE))
        a('<rect x="%d" y="145" width="4" height="116" rx="2" fill="%s"/>' % (x, BLUE))
        a('<text x="%d" y="177" fill="%s" font-size="15">%s</text>' % (x + 20, TITLE, label))
        a('<text x="%d" y="232" fill="%s" font-size="46" font-weight="700">%s</text>'
          % (x + 20, RED if red else DEEP, value))
        a('<text x="%d" y="253" fill="%s" font-size="12">%s</text>' % (x + 20, GRAY, note))

    kpi(48, "本季度负责版本", str(d["total"]), "占全表 %d 个版本的 %.1f%%" % (d["all_versions"], d["share"]))
    kpi(348, "累计发版次数", str(d["times"]), "按「发版次数」列求和", red=True)
    kpi(648, "覆盖系统", str(d["systems"]), "类 · 按原表系统名")
    kpi(948, "已登记发版问题", str(d["problems"]), "起 · %d 版已登记，其余字段为空" % d["registered"], red=True)

    # ---- 左：月度版本数 / 发版次数 双系列柱状图 ----
    a('<rect x="48" y="290" width="760" height="270" rx="8" fill="#FFFFFF" stroke="#E3E8EF" stroke-width="1"/>')
    a('<text x="72" y="324" fill="%s" font-size="18" font-weight="700">月度版本发布分布</text>' % TITLE)
    a('<text x="784" y="324" fill="%s" font-size="12" text-anchor="end">双系列：版本数 / 发版次数</text>' % LIGHT)
    base_y = 500
    for tick in (0, 5, 10, 15, 20):
        y = base_y - tick / 20 * 140
        a('<line x1="110" y1="%.1f" x2="780" y2="%.1f" stroke="%s" stroke-width="1"/>' % (y, y, GRID))
        a('<text x="102" y="%.1f" fill="%s" font-size="11" text-anchor="end" dominant-baseline="central">%d</text>'
          % (y, LIGHT, tick))
    maxv = max([v for pair in d["by_month"].values() for v in pair] + [20])
    for i, m in enumerate(months):
        n, t = d["by_month"][m]
        cx = 230 + i * 220
        for j, (val, color) in enumerate(((n, BLUE), (t, SOFT))):
            bx = cx - 52 + j * 56
            h = val / maxv * 140
            y = base_y - h
            a('<rect x="%d" y="%.1f" width="44" height="%.1f" rx="3" fill="%s"/>' % (bx, y, h, color))
            a('<text x="%d" y="%.1f" fill="%s" font-size="15" font-weight="700" text-anchor="middle">%d</text>'
              % (bx + 22, y - 7, DEEP, val))
        a('<text x="%d" y="522" fill="%s" font-size="13" text-anchor="middle">%d 月</text>' % (cx, GRAY, m))
    a('<line x1="110" y1="500" x2="780" y2="500" stroke="%s" stroke-width="1"/>' % LINE)
    a('<rect x="72" y="538" width="10" height="10" rx="2" fill="%s"/>' % BLUE)
    a('<text x="88" y="547" fill="%s" font-size="11">版本数</text>' % GRAY)
    a('<rect x="160" y="538" width="10" height="10" rx="2" fill="%s"/>' % SOFT)
    a('<text x="176" y="547" fill="%s" font-size="11">发版次数</text>' % GRAY)

    # ---- 右：系统分布 ----
    a('<rect x="828" y="290" width="404" height="270" rx="8" fill="#FFFFFF" stroke="#E3E8EF" stroke-width="1"/>')
    a('<text x="852" y="324" fill="%s" font-size="18" font-weight="700">按系统分布</text>' % TITLE)
    a('<text x="1208" y="324" fill="%s" font-size="12" text-anchor="end">合计 %d</text>' % (LIGHT, d["total"]))
    sysitems = d["by_system"].most_common(4)
    mx = sysitems[0][1] if sysitems else 1
    for i, (name, val) in enumerate(sysitems):
        y = 360 + i * 40
        color = BLUE if i == 0 else (SOFT if i == 1 else PALE)
        a('<text x="852" y="%d" fill="%s" font-size="12">%s</text>' % (y + 15, GRAY, name))
        bw = val / mx * 150
        a('<rect x="1000" y="%d" width="%.1f" height="20" rx="3" fill="%s"/>' % (y, bw, color))
        a('<text x="%.1f" y="%d" fill="%s" font-size="14" font-weight="700">%d</text>'
          % (1000 + bw + 10, y + 16, DEEP, val))
    a('<line x1="852" y1="510" x2="1208" y2="510" stroke="%s" stroke-width="1"/>' % LINE)
    a('<text x="852" y="536" fill="%s" font-size="11">%s</text>' % (LIGHT, sys_note(d)))

    # ---- 月度明细卡 ----
    a('<text x="48" y="592" fill="%s" font-size="15" font-weight="700">月度明细（版本数 / 发版次数 / 系统构成）</text>' % TITLE)
    for i, m in enumerate(months):
        x = 48 + i * 400
        n, t = d["by_month"][m]
        a('<rect x="%d" y="602" width="384" height="50" rx="6" fill="%s"/>' % (x, ICE))
        a('<rect x="%d" y="602" width="3" height="50" rx="1" fill="%s"/>' % (x, BLUE))
        a('<text x="%d" y="623" fill="%s" font-size="14" font-weight="700">%d 月　%d 个版本 · %d 次发版</text>'
          % (x + 14, TITLE, m, n, t))
        a('<text x="%d" y="642" fill="%s" font-size="11">%s</text>' % (x + 14, GRAY, month_line(m, d)))

    a('<line x1="48" y1="663" x2="1232" y2="663" stroke="#E3E8EF" stroke-width="1"/>')
    a('<text x="48" y="682" fill="%s" font-size="11">口径：取《各系统发版汇总》%s 三个工作表，筛选「发版负责人」含%s；版本数按有效行计、发版次数按「发版次数」列求和；系统名因合并单元格留空时向下继承。</text>'
      % (LIGHT, " / ".join("各系统%d月版本" % m for m in months), d["owner"]))
    a('<text x="48" y="701" fill="%s" font-size="11">「是否有发版问题」仅参考、不参与计数：%d 版已登记「否」、%d 起问题，其余 %d 版该字段为空（%s 工作表未填）。数据下载于 %s。</text>'
      % (LIGHT, d["registered"] - d["problems"], d["problems"], d["total"] - d["registered"],
         "%d月" % months[-1], downloaded))
    a('</svg>')
    return "\n".join(s)


CSS = """
.rel-wrap{display:flex;flex-direction:column;gap:9px;height:100%;font-family:"Microsoft YaHei","PingFang SC",sans-serif;}
.rel-sub{font-size:11px;color:#666;flex-shrink:0;}
.rel-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;flex-shrink:0;}
.rel-card{background:#E6F1FB;border-left:4px solid #0C72BB;border-radius:6px;padding:9px 13px 8px;height:92px;box-sizing:border-box;}
.rel-label{font-size:12.5px;color:#004E97;font-weight:600;}
.rel-val{font-size:32px;font-weight:700;line-height:1.25;margin-top:2px;}
.rel-note{font-size:10px;color:#666;}
.rel-charts{display:grid;grid-template-columns:1.9fr 1fr;gap:14px;flex:1;min-height:0;}
.rel-panel{border:1px solid #E3E8EF;border-radius:6px;padding:9px 14px;display:flex;flex-direction:column;background:#fff;}
.rel-p-title{font-size:14px;font-weight:700;color:#004E97;display:flex;justify-content:space-between;align-items:baseline;}
.rel-p-title span{font-size:10.5px;font-weight:400;color:#999;}
.rel-bar-chart{flex:1;display:flex;align-items:flex-end;justify-content:space-around;gap:18px;padding:12px 20px 22px;position:relative;}
.rel-bar-chart::after{content:"";position:absolute;left:20px;right:20px;bottom:22px;height:1px;background:#B4C6DA;}
.rel-bar-group{display:flex;align-items:flex-end;gap:8px;position:relative;flex:1;justify-content:center;}
.rel-bar{width:44px;max-width:52px;border-radius:3px 3px 0 0;position:relative;}
.rel-bar b{position:absolute;top:-19px;left:0;right:0;text-align:center;font-size:13px;color:#1F497D;}
.rel-bar-lab{position:absolute;bottom:-21px;left:0;right:0;text-align:center;font-size:11px;color:#666;}
.rel-legend{display:flex;gap:16px;font-size:10.5px;color:#666;margin-top:2px;}
.rel-legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px;}
.rel-p-foot{font-size:10.5px;color:#999;margin-top:4px;}
.rel-sys-list{flex:1;display:flex;flex-direction:column;justify-content:center;gap:16px;padding:6px 2px;}
.rel-sys-row{display:flex;align-items:center;gap:8px;font-size:11.5px;color:#666;}
.rel-sys-lab{width:76px;flex-shrink:0;}
.rel-sys-track{flex:1;height:16px;background:#E6F1FB;border-radius:3px;overflow:hidden;}
.rel-sys-fill{height:100%;border-radius:3px;}
.rel-sys-val{width:22px;text-align:right;font-weight:700;color:#1F497D;font-size:13px;}
.rel-months{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;flex-shrink:0;}
.rel-month{background:#E6F1FB;border-left:3px solid #0C72BB;border-radius:5px;padding:6px 11px;}
.rel-month b{font-size:12px;color:#004E97;}
.rel-month div{font-size:10px;color:#666;margin-top:2px;}
.rel-foot{flex-shrink:0;border-top:1px solid #E3E8EF;padding-top:5px;font-size:9.5px;color:#999;line-height:1.5;}
"""


def build_inner(d, months, downloaded):
    kpis = [
        ("本季度负责版本", str(d["total"]), "占全表 %d 个版本的 %.1f%%" % (d["all_versions"], d["share"]), False),
        ("累计发版次数", str(d["times"]), "按「发版次数」列求和", True),
        ("覆盖系统", str(d["systems"]), "类 · 按原表系统名", False),
        ("已登记发版问题", str(d["problems"]), "起 · %d 版已登记，其余字段为空" % d["registered"], True),
    ]
    kpi_html = "".join(
        '<div class="rel-card"><div class="rel-label">%s</div>'
        '<div class="rel-val" style="color:%s;">%s</div><div class="rel-note">%s</div></div>'
        % (lab, RED if hi else DEEP, val, note) for lab, val, note, hi in kpis
    )
    maxv = max([v for pair in d["by_month"].values() for v in pair] + [20])
    groups = ""
    for m in months:
        n, t = d["by_month"][m]
        groups += ('<div class="rel-bar-group">'
                   '<div class="rel-bar" style="height:%.1fpx;background:%s;"><b>%d</b></div>'
                   '<div class="rel-bar" style="height:%.1fpx;background:%s;"><b>%d</b></div>'
                   '<div class="rel-bar-lab">%d 月</div></div>'
                   % (max(3, n / maxv * 205), BLUE, n, max(3, t / maxv * 205), SOFT, t, m))
    sysitems = d["by_system"].most_common(4)
    mx = sysitems[0][1] if sysitems else 1
    rows = ""
    for i, (name, val) in enumerate(sysitems):
        color = BLUE if i == 0 else (SOFT if i == 1 else PALE)
        rows += ('<div class="rel-sys-row"><span class="rel-sys-lab">%s</span>'
                 '<div class="rel-sys-track"><div class="rel-sys-fill" style="width:%.1f%%;background:%s;"></div></div>'
                 '<span class="rel-sys-val">%d</span></div>' % (name, val / mx * 100, color, val))
    months_html = "".join(
        '<div class="rel-month"><b>%d 月　%d 个版本 · %d 次发版</b><div>%s</div></div>'
        % (m, d["by_month"][m][0], d["by_month"][m][1], month_line(m, d)) for m in months
    )
    foot = ("口径：取《各系统发版汇总》%s 三个工作表，筛选「发版负责人」含%s；版本数按有效行计、发版次数按「发版次数」列求和；系统名因合并单元格留空时向下继承。<br>"
            "「是否有发版问题」仅参考、不参与计数：%d 版登记「否」、%d 起问题，其余 %d 版字段为空（%d 月工作表未填）。数据源：%s；下载于 %s。"
            % (" / ".join("各系统%d月版本" % m for m in months), d["owner"],
               d["registered"] - d["problems"], d["problems"], d["total"] - d["registered"],
               months[-1], DOC_URL, downloaded))

    tpl = """<div class="rel-wrap">
  <div class="rel-sub">吴进（125360） · 数据来源：全连接文档中心《各系统发版汇总》在线表格 · 统计区间：__QSTART__ ~ __QEND__ · 发布负责人：__OWNER__</div>
  <div class="rel-grid">__KPIS__</div>
  <div class="rel-charts">
    <div class="rel-panel">
      <div class="rel-p-title">月度版本发布分布 <span>双系列：版本数 / 发版次数</span></div>
      <div class="rel-bar-chart">__GROUPS__</div>
      <div class="rel-legend"><span><i style="background:__BLUE__;"></i>版本数</span><span><i style="background:__SOFT__;"></i>发版次数</span></div>
    </div>
    <div class="rel-panel">
      <div class="rel-p-title">按系统分布 <span>合计 __TOTAL__</span></div>
      <div class="rel-sys-list">__SYSROWS__</div>
      <div class="rel-p-foot">__SYSNOTE__</div>
    </div>
  </div>
  <div class="rel-months">__MONTHS__</div>
  <div class="rel-foot">__FOOT__</div>
</div>"""
    year = int(quarter[:4])
    qstart = "%d-%02d-01" % (year, months[0])
    qend = "%d-%02d-%02d" % (year, months[-1], calendar.monthrange(year, months[-1])[1])
    rep = {
        "__QSTART__": qstart, "__QEND__": qend,
        "__OWNER__": d["owner"], "__KPIS__": kpi_html, "__GROUPS__": groups,
        "__BLUE__": BLUE, "__SOFT__": SOFT, "__TOTAL__": str(d["total"]),
        "__SYSROWS__": rows, "__MONTHS__": months_html, "__FOOT__": foot,
        "__SYSNOTE__": sys_note(d),
    }
    for k, v in rep.items():
        tpl = tpl.replace(k, v)
    return tpl, CSS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default=DEFAULT_XLSX)
    ap.add_argument("--quarter", default="2026Q3")
    ap.add_argument("--months", default="7,8,9")
    ap.add_argument("--owner", default="吴进")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--downloaded", default="2026-11-11")
    ap.add_argument("--tag", default="Q3")
    ap.add_argument("--ongoing", action="store_true", help="季度进行中（默认已完结）")
    args = ap.parse_args()

    global quarter, STATE_TEXT
    quarter = args.quarter
    STATE_TEXT = "季度进行中" if args.ongoing else "季度已完结"
    months = [int(x) for x in args.months.split(",")]
    allrows, mine = load_rows(args.xlsx, months, args.owner)
    d = stat(allrows, mine, months, args.owner)
    d["mine"] = mine
    print("统计：%s 负责人=%s 版本=%d 发版次数=%d 系统=%d 已登记=%d 问题=%d 全表=%d 占比=%.1f%%"
          % (args.quarter, args.owner, d["total"], d["times"], d["systems"],
             d["registered"], d["problems"], d["all_versions"], d["share"]))
    for m in months:
        print("  %d月: %d 版 / %d 次 | %s" % (m, d["by_month"][m][0], d["by_month"][m][1], month_line(m, d)))

    os.makedirs(args.out, exist_ok=True)
    svg = build_svg(d, months, args.quarter, args.downloaded)
    svg_path = os.path.join(args.out, "版本集成发布情况_%s.svg" % args.tag)
    open(svg_path, "w", encoding="utf-8").write(svg)

    html_doc = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>版本集成发布情况 · %s</title>
<style>
body{margin:0;background:#F4F6F9;font-family:"PingFang SC","Microsoft YaHei",Helvetica,Arial,sans-serif;color:#333;}
.wrap{max-width:1280px;margin:24px auto 40px;padding:0 16px;}
.bar{display:flex;justify-content:space-between;gap:16px;margin-bottom:14px;font-size:13px;color:#666;}
.bar strong{color:#1F497D;font-weight:500;}
.stage{background:#fff;border:1px solid #E3E8EF;border-radius:8px;overflow:hidden;}
svg{display:block;width:100%%;height:auto;}
.tip{margin-top:14px;font-size:12px;color:#999;}
@media print{body{background:#fff}.wrap{margin:0;padding:0;max-width:none}.bar,.tip{display:none}.stage{border:0}}
</style></head><body><div class="wrap">
<div class="bar"><span><strong>版本集成发布情况 · %s</strong> · 16:9 述职页图表</span><span>同目录 .svg 为矢量文件，可直接插入 PPT</span></div>
<div class="stage">%s</div>
<div class="tip">数据源：%s</div>
</div></body></html>
""" % (args.quarter, args.quarter, svg, DOC_URL)
    html_path = os.path.join(args.out, "版本集成发布情况_%s.html" % args.tag)
    open(html_path, "w", encoding="utf-8").write(html_doc)

    inner, css = build_inner(d, months, args.downloaded)
    inner_path = os.path.join(args.out, "release_slide_inner_%s.html" % args.tag)
    open(inner_path, "w", encoding="utf-8").write(
        '<!-- 使用时把下方样式块拆到主 HTML 的 head 中 -->\n' + inner + '\n<style>\n' + css + '</style>\n')
    # 统计快照：供 build_quarter_pages.py 检测在线数据源是否被维护者改动
    snap = dict(quarter=args.quarter, tag=args.tag, owner=args.owner,
                downloaded=args.downloaded, total=d["total"], times=d["times"],
                systems=d["systems"], by_system=dict(d["by_system"]),
                by_month={str(k): list(v) for k, v in d["by_month"].items()},
                registered=d["registered"], problems=d["problems"],
                all_versions=d["all_versions"], share=round(d["share"], 1))
    snap_path = os.path.join(args.out, "release_stats_%s.json" % args.tag)
    json.dump(snap, open(snap_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    for p in (svg_path, html_path, inner_path, snap_path):
        print(p, os.path.getsize(p), "bytes")


if __name__ == "__main__":
    main()
