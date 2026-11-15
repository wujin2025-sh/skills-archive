# -*- coding: utf-8 -*-
"""「本季度需求指标看板」季度通用生成器（02 模块第 1 页）。

与历史快照 gen_kpi_dashboard.py（Q4）/ gen_kpi_dashboard_q3.py（Q3）并列，
本脚本是**按季度驱动**的正式版本：所有数字来自 quarter_config.json 的季度基线，
季度 / 月份 / tag / 统计区间由 --quarter 自动推导，不在代码里写死任何季度数字。

用法：
  python gen_kpi_dashboard_q.py --quarter 2026Q3 [--out <目录>] [--config <json>]

产出（tag 如 Q3）：
  本季度需求指标看板_<tag>.svg      16:9 矢量，可直插 PPT
  本季度需求指标看板_<tag>.html     预览页
  kpi_slide_inner_<tag>.html        述职内页片段（markup + <style> 块），供 insert_quarter_pages.py 使用

铁律：受理月份之和、状态构成之和必须等于受理总数，否则拒绝生成；
      季度基线缺失字段（如 Q4 的 status / 时长 / 效率）一律报错，禁止估算补数。
"""
import os
import re
import json
import math
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(SCRIPT_DIR, "quarter_config.json")

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
STATUS_COLORS = [BLUE, SOFT, PALE]

REQUIRED = ["accept_total", "accept_months", "release_total", "e2e_days",
            "it_days", "flow_eff", "status", "proposed", "month_note", "foot1", "foot2"]


def quarter_meta(q):
    """2026Q3 -> (year, 3, [7,8,9], 'Q3', '07/01-09/30', start, end, '2026 Q3')"""
    m = re.fullmatch(r"(\d{4})Q([1-4])", q.strip(), re.I)
    if not m:
        raise ValueError("季度格式应为 YYYYQn，如 2026Q3；收到：%s" % q)
    year, n = int(m.group(1)), int(m.group(2))
    first = (n - 1) * 3 + 1
    months = [first, first + 1, first + 2]
    last = first + 2
    end_day = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
               7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}[last]
    return dict(
        quarter=q.upper(), year=year, n=n, months=months, tag="Q%d" % n,
        range="%02d/01-%02d/%02d" % (first, last, end_day),
        start="%d-%02d-01" % (year, first),
        end="%d-%02d-%02d" % (year, last, end_day),
        label="%d Q%d" % (year, n),
        period="%d-%02d ~ %d-%02d" % (year, first, year, last),
    )


def load_config(config_path, quarter):
    cfg = json.load(open(config_path, encoding="utf-8"))
    if quarter not in cfg["quarters"]:
        raise KeyError("配置中没有季度 %s（现有：%s）" % (quarter, ", ".join(cfg["quarters"])))
    c = cfg["quarters"][quarter]
    if not c.get("ready"):
        miss = [k for k in REQUIRED if c.get("kpi", {}).get(k) is None]
        raise ValueError("季度 %s 基线未就绪（ready=false）。缺失/待补字段：%s\n  %s"
                         % (quarter, ", ".join(miss) or "（字段齐全，请把 ready 置 true）",
                            c.get("_todo", "请补录效能度量看板季度截图数据后再生成")))
    k = c["kpi"]
    missing = [x for x in REQUIRED if k.get(x) is None]
    if missing:
        raise ValueError("季度 %s 基线缺字段：%s（禁止估算补数）" % (quarter, ", ".join(missing)))
    months_sum = sum(v for _, v in k["accept_months"])
    status_sum = sum(v for _, v in k["status"])
    if months_sum != k["accept_total"] or status_sum != k["accept_total"]:
        raise ValueError("数据一致性校验失败：受理月份合计 %d、状态构成合计 %d、受理总数 %d 不相等"
                         % (months_sum, status_sum, k["accept_total"]))
    return cfg, k


def _ticks(step):
    return [int(step * i / 4) for i in range(5)]


# ---------------------------------------------------------------- SVG
def build_svg(k, meta, finished=True):
    s = []
    a = s.append
    accept, release = k["accept_total"], k["release_total"]
    amonths = k["accept_months"]
    status = [(lab, val, STATUS_COLORS[i % len(STATUS_COLORS)])
              for i, (lab, val) in enumerate(k["status"])]
    step = max(10, int(math.ceil(max(v for _, v in amonths) / 10.0) * 10))
    smax = max(v for _, v, _ in status)
    state = "季度已完结" if finished else "季度进行中"

    a('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720" '
      'font-family="PingFang SC, Microsoft YaHei, Helvetica, Arial, sans-serif" role="img">')
    a(f'<title>本季度需求指标看板 · {meta["label"]}</title>')
    a(f'<desc>{meta["label"]} 吴进受理需求{accept}项、版本排期交付需求{release}项，附受理月份分布、需求状态构成与口径说明</desc>')
    a('<rect width="1280" height="720" fill="#FFFFFF"/>')
    a(f'<rect x="0" y="0" width="1280" height="88" fill="{DEEP}"/>')
    a('<text x="48" y="57" fill="#FFFFFF" font-size="34" font-weight="700">本季度需求指标看板</text>')
    a(f'<text x="1232" y="55" fill="#CFE2F5" font-size="16" text-anchor="end">{meta["label"]} · {meta["range"]} · {state}</text>')
    a('<text x="48" y="119" fill="%s" font-size="14">吴进（125360） · 数据来源：科技平台效能度量看板 / 需求集合大宽表</text>' % GRAY)

    def kpi(x, label, value, note, red=False):
        a(f'<rect x="{x}" y="145" width="282" height="116" rx="8" fill="{ICE}"/>')
        a(f'<rect x="{x}" y="145" width="4" height="116" rx="2" fill="{BLUE}"/>')
        a(f'<text x="{x + 20}" y="177" fill="{TITLE}" font-size="15">{label}</text>')
        a(f'<text x="{x + 20}" y="232" fill="{RED if red else DEEP}" font-size="46" font-weight="700">{value}</text>')
        a(f'<text x="{x + 20}" y="253" fill="{GRAY}" font-size="12">{note}</text>')

    kpi(48, "本季度受理需求", str(accept), "按最后受理时间 · 含主受理与共同受理")
    kpi(348, "本季度版本排期交付", str(release), "按版本排期", red=True)
    kpi(648, "端到端净交付", k["e2e_days"], f'天 · IT 交付 {k["it_days"]} 天')
    kpi(948, "全流程流动效率", k["flow_eff"], "各阶段无阻滞高效流转", red=True)

    # ---- 左：受理月份分布 ----
    a('<rect x="48" y="290" width="760" height="270" rx="8" fill="#FFFFFF" stroke="#E3E8EF" stroke-width="1"/>')
    a(f'<text x="72" y="324" fill="{TITLE}" font-size="18" font-weight="700">按最后受理时间分布</text>')
    a(f'<text x="784" y="324" fill="{LIGHT}" font-size="12" text-anchor="end">合计 {accept} · {"+".join(str(v) for _, v in amonths)}</text>')
    base_y = 500
    for tick in _ticks(step):
        y = base_y - tick / step * 140
        a(f'<line x1="110" y1="{y:.1f}" x2="780" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        a(f'<text x="102" y="{y:.1f}" fill="{LIGHT}" font-size="11" text-anchor="end" dominant-baseline="central">{tick}</text>')
    for i, (label, val) in enumerate(amonths):
        cx = 230 + i * 220
        h = val / step * 140
        y = base_y - h
        color = BLUE if i < 2 else SOFT
        a(f'<rect x="{cx - 48:.1f}" y="{y:.1f}" width="96" height="{h:.1f}" rx="4" fill="{color}"/>')
        a(f'<text x="{cx}" y="{y - 10:.1f}" fill="{DEEP}" font-size="20" font-weight="700" text-anchor="middle">{val}</text>')
        a(f'<text x="{cx}" y="522" fill="{GRAY}" font-size="13" text-anchor="middle">{meta["year"]}-{label.replace("月", "").zfill(2)}</text>')
    a(f'<line x1="110" y1="500" x2="780" y2="500" stroke="{LINE}" stroke-width="1"/>')
    a(f'<text x="72" y="546" fill="{LIGHT}" font-size="12">{k["month_note"]}</text>')

    # ---- 右：需求状态构成 ----
    a('<rect x="828" y="290" width="404" height="270" rx="8" fill="#FFFFFF" stroke="#E3E8EF" stroke-width="1"/>')
    a(f'<text x="852" y="324" fill="{TITLE}" font-size="18" font-weight="700">需求状态构成</text>')
    a(f'<text x="1208" y="324" fill="{LIGHT}" font-size="12" text-anchor="end">合计 {accept}</text>')
    for i, (label, val, color) in enumerate(status):
        y = 362 + i * 48
        a(f'<text x="852" y="{y + 16}" fill="{GRAY}" font-size="13">{label}</text>')
        bw = val / smax * 170
        a(f'<rect x="1000" y="{y}" width="{bw:.1f}" height="22" rx="3" fill="{color}"/>')
        a(f'<text x="{1000 + bw + 10:.1f}" y="{y + 17}" fill="{DEEP}" font-size="14" font-weight="700">{val}</text>')
    a(f'<line x1="852" y1="510" x2="1208" y2="510" stroke="{LINE}" stroke-width="1"/>')
    a(f'<text x="852" y="536" fill="{LIGHT}" font-size="12">{" + ".join(str(v) for _, v, _ in status)} = {accept}；我提出 {k["proposed"]} 项为其中子集，不重复计数</text>')

    # ---- 状态分布参考条 ----
    a(f'<text x="48" y="596" fill="{TITLE}" font-size="15" font-weight="700">需求状态分布（效能看板口径，仅参考 · 不参与上线数计数）</text>')
    a(f'<rect x="48" y="610" width="1184" height="22" rx="4" fill="{ICE}"/>')
    offset = 48
    for _, val, color in status:
        w = 1184 * val / accept
        a(f'<rect x="{offset:.1f}" y="610" width="{w:.1f}" height="22" rx="4" fill="{color}"/>')
        offset += w
    seg = " · ".join(f"{lab.replace('我受理', '')} {val}（{val / accept * 100:.1f}%）"
                     for lab, val, _ in status)
    a(f'<text x="48" y="646" fill="{GRAY}" font-size="12">{seg}　|　上线数 {release} 为版本排期口径，与此处状态分布不同源，不可相加</text>')

    a('<line x1="48" y1="661" x2="1232" y2="661" stroke="#E3E8EF" stroke-width="1"/>')
    a(f'<text x="48" y="681" fill="{LIGHT}" font-size="12">{k["foot1"]}</text>')
    a(f'<text x="48" y="701" fill="{LIGHT}" font-size="12">{k["foot2"]}</text>')
    a('</svg>')
    return "\n".join(s)


# ---------------------------------------------------------------- 内页片段
INNER_CSS = """.q3kpi-wrap{display:flex;flex-direction:column;gap:10px;height:100%;font-family:"Microsoft YaHei","PingFang SC",sans-serif;}
.q3kpi-sub{font-size:11.5px;color:#666;flex-shrink:0;}
.q3kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;flex-shrink:0;}
.q3k-card{background:#E6F1FB;border-left:4px solid #0C72BB;border-radius:6px;padding:10px 14px 9px;height:96px;box-sizing:border-box;}
.q3k-label{font-size:12.5px;color:#004E97;font-weight:600;}
.q3k-val{font-size:34px;font-weight:700;line-height:1.25;margin-top:2px;}
.q3k-note{font-size:10.5px;color:#666;}
.q3kpi-charts{display:grid;grid-template-columns:1.9fr 1fr;gap:14px;flex:1;min-height:0;}
.q3kpi-panel{border:1px solid #E3E8EF;border-radius:6px;padding:10px 14px;display:flex;flex-direction:column;background:#fff;}
.q3p-title{font-size:14px;font-weight:700;color:#004E97;display:flex;justify-content:space-between;align-items:baseline;}
.q3p-title span{font-size:10.5px;font-weight:400;color:#999;}
.q3bar-chart{flex:1;display:flex;align-items:flex-end;justify-content:space-around;gap:18px;padding:14px 20px 24px;position:relative;}
.q3bar-chart::after{content:"";position:absolute;left:20px;right:20px;bottom:24px;height:1px;background:#B4C6DA;}
.q3bar-col{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;position:relative;}
.q3bar-num{font-size:16px;font-weight:700;color:#1F497D;margin-bottom:4px;}
.q3bar{width:64%;max-width:74px;border-radius:4px 4px 0 0;}
.q3bar-lab{position:absolute;bottom:-22px;left:0;right:0;text-align:center;font-size:11px;color:#666;line-height:18px;}
.q3p-foot{font-size:10.5px;color:#999;margin-top:6px;}
.q3st-list{flex:1;display:flex;flex-direction:column;justify-content:center;gap:22px;padding:6px 2px;}
.q3st-row{display:flex;align-items:center;gap:8px;font-size:11.5px;color:#666;}
.q3st-lab{width:86px;flex-shrink:0;}
.q3st-track{flex:1;height:16px;background:#E6F1FB;border-radius:3px;overflow:hidden;}
.q3st-fill{height:100%;border-radius:3px;}
.q3st-val{width:24px;text-align:right;font-weight:700;color:#1F497D;font-size:13px;}
.q3kpi-ref{flex-shrink:0;}
.q3ref-title{font-size:12px;font-weight:700;color:#004E97;margin-bottom:5px;}
.q3ref-bar{display:flex;height:18px;border-radius:3px;overflow:hidden;background:#E6F1FB;}
.q3ref-bar span{display:block;height:100%;}
.q3ref-note{font-size:10.5px;color:#666;margin-top:5px;}
.q3kpi-foot{flex-shrink:0;border-top:1px solid #E3E8EF;padding-top:6px;font-size:10px;color:#999;line-height:1.55;}
"""


def build_inner(k, meta, finished=True):
    accept, release = k["accept_total"], k["release_total"]
    amonths = k["accept_months"]
    status = [(lab, val, STATUS_COLORS[i % len(STATUS_COLORS)])
              for i, (lab, val) in enumerate(k["status"])]
    step = max(10, int(math.ceil(max(v for _, v in amonths) / 10.0) * 10))
    smax = max(v for _, v, _ in status)
    state = "季度已完结" if finished else "季度进行中"

    cards = [
        ("本季度受理需求", str(accept), "按最后受理时间 · 含主受理与共同受理", False),
        ("本季度版本排期交付", str(release), "按版本排期", True),
        ("端到端净交付", k["e2e_days"], f'天 · IT 交付 {k["it_days"]} 天', False),
        ("全流程流动效率", k["flow_eff"], "各阶段无阻滞高效流转", True),
    ]
    kpi_html = "".join(
        f'<div class="q3k-card"><div class="q3k-label">{lab}</div>'
        f'<div class="q3k-val" style="color:{RED if hi else DEEP};">{val}</div>'
        f'<div class="q3k-note">{note}</div></div>'
        for lab, val, note, hi in cards)
    bars = "".join(
        f'<div class="q3bar-col"><div class="q3bar-num">{val}</div>'
        f'<div class="q3bar" style="height:{val / step * 185:.1f}px;background:{BLUE if i < 2 else SOFT};"></div>'
        f'<div class="q3bar-lab">{meta["year"]}-{lab.replace("月", "").zfill(2)}</div></div>'
        for i, (lab, val) in enumerate(amonths))
    rows = "".join(
        f'<div class="q3st-row"><span class="q3st-lab">{lab}</span>'
        f'<div class="q3st-track"><div class="q3st-fill" style="width:{val / smax * 100:.1f}%;background:{color};"></div></div>'
        f'<span class="q3st-val">{val}</span></div>'
        for lab, val, color in status)
    segs = "".join(f'<span style="width:{val / accept * 100:.1f}%;background:{color};"></span>'
                   for _, val, color in status)
    seg = " · ".join(f"{lab.replace('我受理', '')} {val}（{val / accept * 100:.1f}%）"
                     for lab, val, _ in status)
    sum_expr = " + ".join(str(v) for _, v, _ in status)

    markup = f"""<div class="q3kpi-wrap">
  <div class="q3kpi-sub">吴进（125360） · 数据来源：科技平台效能度量看板 / 需求集合大宽表　|　统计区间：{meta["period"]}　|　{state}</div>
  <div class="q3kpi-grid">{kpi_html}</div>
  <div class="q3kpi-charts">
    <div class="q3kpi-panel">
      <div class="q3p-title">按最后受理时间分布 <span>合计 {accept} · {"+".join(str(v) for _, v in amonths)}</span></div>
      <div class="q3bar-chart">{bars}</div>
      <div class="q3p-foot">{k["month_note"]}</div>
    </div>
    <div class="q3kpi-panel">
      <div class="q3p-title">需求状态构成 <span>合计 {accept}</span></div>
      <div class="q3st-list">{rows}</div>
      <div class="q3p-foot">{sum_expr} = {accept}；我提出 {k["proposed"]} 项为其中子集，不重复计数</div>
    </div>
  </div>
  <div class="q3kpi-ref">
    <div class="q3ref-title">需求状态分布（效能看板口径，仅参考 · 不参与上线数计数）</div>
    <div class="q3ref-bar">{segs}</div>
    <div class="q3ref-note">{seg}　|　上线数 {release} 为版本排期口径，与状态分布不同源，不可相加</div>
  </div>
  <div class="q3kpi-foot">{k["foot1"]}<br>{k["foot2"]}</div>
</div>"""
    return ("<!-- 使用时把下方样式块拆到主 HTML 的 head 中 -->\n"
            + markup + "\n<style>\n" + INNER_CSS + "</style>\n")


def build_html(svg, meta):
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>本季度需求指标看板 · {meta["label"]}</title>
<style>
body{{margin:0;background:#F4F6F9;font-family:"PingFang SC","Microsoft YaHei",Helvetica,Arial,sans-serif;color:#333;}}
.wrap{{max-width:1280px;margin:24px auto 40px;padding:0 16px;}}
.bar{{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:14px;font-size:13px;color:#666;}}
.bar strong{{color:#1F497D;font-weight:500;}}
.stage{{background:#fff;border:1px solid #E3E8EF;border-radius:8px;overflow:hidden;}}
svg{{display:block;width:100%;height:auto;}}
.tip{{margin-top:14px;font-size:12px;color:#999;line-height:1.7;}}
@media print{{body{{background:#fff}}.wrap{{margin:0;padding:0;max-width:none}}.bar,.tip{{display:none}}.stage{{border:0}}}}
</style></head><body><div class="wrap">
<div class="bar"><span><strong>本季度需求指标看板 · {meta["label"]}</strong> · 16:9 述职页图表（统计区间 {meta["range"]}）</span><span>同目录 .svg 为矢量文件</span></div>
<div class="stage">{svg}</div>
<div class="tip">同目录 .svg 为 1280×720 矢量文件，可无损插入 PPT；口径说明已随图内嵌，打印时本行自动隐藏。</div>
</div></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarter", required=True, help="YYYYQn，如 2026Q3")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--out", default=None, help="产物目录，缺省取配置 paths.out_dir")
    ap.add_argument("--ongoing", action="store_true", help="标记为季度进行中（默认已完结）")
    args = ap.parse_args()

    meta = quarter_meta(args.quarter)
    cfg, k = load_config(args.config, meta["quarter"])
    out = args.out or cfg["paths"]["out_dir"]
    os.makedirs(out, exist_ok=True)
    tag = meta["tag"]

    svg = build_svg(k, meta, not args.ongoing)
    svg_path = os.path.join(out, f"本季度需求指标看板_{tag}.svg")
    html_path = os.path.join(out, f"本季度需求指标看板_{tag}.html")
    inner_path = os.path.join(out, f"kpi_slide_inner_{tag}.html")
    open(svg_path, "w", encoding="utf-8").write(svg)
    open(html_path, "w", encoding="utf-8").write(build_html(svg, meta))
    open(inner_path, "w", encoding="utf-8").write(build_inner(k, meta, not args.ongoing))

    print(f"[{meta['quarter']}] 受理 {k['accept_total']} · 版本排期 {k['release_total']} · "
          f"月份 {meta['months']} · 一致性校验通过")
    for p in (svg_path, html_path, inner_path):
        print(" ", p, os.path.getsize(p), "bytes")


if __name__ == "__main__":
    main()
