# -*- coding: utf-8 -*-
"""2026 Q3「本季度需求指标看板」：生成 16:9 自包含 SVG + 预览 HTML + 述职内页片段。

与 gen_kpi_dashboard.py（Q4 快照）并列，供历史季度复用。
数据口径依据 SKILL.md「效能度量页（S7）取数字典 · 2026-11-11 实测校准」：
  - 受理总数：科技平台效能度量看板（最后一次需求受理时间，含主受理与共同受理）
  - 上线数：版本排期日期落在季度内，按需求编号去重，不看需求状态，排除 2099-12-31 / 年末 12-31 占位
  - Q3 已完结，不写「进行时态」，但总量含在途时措辞仍用「平稳推进」
"""
import os
import argparse

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

# ---- Q3 数据（全部可回溯到效能度量看板原生截图 / SKILL 校准基线）----
Q_LABEL = "2026 Q3"
Q_RANGE = "07/01-09/30"
Q_END = "2026-09-30"
ACCEPT_TOTAL = 75
ACCEPT_MONTHS = [("7月", 33), ("8月", 24), ("9月", 18)]
RELEASE_TOTAL = 85
E2E_DAYS = "26.95"
IT_DAYS = "19.55"
FLOW_EFF = "35.04%"
STATUS = [("我受理进行中", 60, BLUE), ("待受理", 7, SOFT), ("已上线", 8, PALE)]
PROPOSED = 15

FOOT1 = ("口径：受理数按最后一次需求受理时间，含主受理与共同受理；上线数按版本排期日期落在 2026Q3、"
         "按需求编号去重、不按需求状态筛选，已排除 2099-12-31 与年末 12-31 占位值。")
FOOT2 = ("数据来源：科技平台效能度量看板（2026-07~09 原生截图）/ 需求集合大宽表；"
         "上线数沿用 2026-11-11 校准基线（实时全量 13,072 行）。Q3 已完结。")


def build_svg():
    s = []
    a = s.append
    a('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720" '
      'font-family="PingFang SC, Microsoft YaHei, Helvetica, Arial, sans-serif" role="img">')
    a('<title>本季度需求指标看板 · 2026 Q3</title>')
    a('<desc>2026年第三季度吴进受理需求75项、版本排期交付需求85项，附受理月份分布、需求状态构成与口径说明</desc>')
    a('<rect width="1280" height="720" fill="#FFFFFF"/>')
    a('<rect x="0" y="0" width="1280" height="88" fill="%s"/>' % DEEP)
    a('<text x="48" y="57" fill="#FFFFFF" font-size="34" font-weight="700">本季度需求指标看板</text>')
    a('<text x="1232" y="55" fill="#CFE2F5" font-size="16" text-anchor="end">%s · %s · 季度已完结</text>'
      % (Q_LABEL, Q_RANGE))
    a('<text x="48" y="119" fill="%s" font-size="14">吴进（125360） · 数据来源：科技平台效能度量看板 / 需求集合大宽表</text>' % GRAY)

    def kpi(x, label, value, note, red=False):
        a('<rect x="%d" y="145" width="282" height="116" rx="8" fill="%s"/>' % (x, ICE))
        a('<rect x="%d" y="145" width="4" height="116" rx="2" fill="%s"/>' % (x, BLUE))
        a('<text x="%d" y="177" fill="%s" font-size="15">%s</text>' % (x + 20, TITLE, label))
        a('<text x="%d" y="232" fill="%s" font-size="46" font-weight="700">%s</text>'
          % (x + 20, RED if red else DEEP, value))
        a('<text x="%d" y="253" fill="%s" font-size="12">%s</text>' % (x + 20, GRAY, note))

    kpi(48, "本季度受理需求", str(ACCEPT_TOTAL), "按最后受理时间 · 含主受理与共同受理")
    kpi(348, "本季度版本排期交付", str(RELEASE_TOTAL), "按版本排期", red=True)
    kpi(648, "端到端净交付", E2E_DAYS, "天 · IT 交付 %s 天" % IT_DAYS)
    kpi(948, "全流程流动效率", FLOW_EFF, "各阶段无阻滞高效流转", red=True)

    # ---- 左：受理月份分布 ----
    a('<rect x="48" y="290" width="760" height="270" rx="8" fill="#FFFFFF" stroke="#E3E8EF" stroke-width="1"/>')
    a('<text x="72" y="324" fill="%s" font-size="18" font-weight="700">按最后受理时间分布</text>' % TITLE)
    a('<text x="784" y="324" fill="%s" font-size="12" text-anchor="end">合计 %d · 33+24+18</text>'
      % (LIGHT, ACCEPT_TOTAL))
    base_y = 500
    for tick in (0, 10, 20, 30, 40):
        y = base_y - tick / 40 * 140
        a('<line x1="110" y1="%.1f" x2="780" y2="%.1f" stroke="%s" stroke-width="1"/>' % (y, y, GRID))
        a('<text x="102" y="%.1f" fill="%s" font-size="11" text-anchor="end" dominant-baseline="central">%d</text>'
          % (y, LIGHT, tick))
    for i, (label, val) in enumerate(ACCEPT_MONTHS):
        cx = 230 + i * 220
        h = val / 40 * 140
        y = base_y - h
        a('<rect x="%.1f" y="%.1f" width="96" height="%.1f" rx="4" fill="%s"/>'
          % (cx - 48, y, h, BLUE if i < 2 else SOFT))
        a('<text x="%d" y="%.1f" fill="%s" font-size="20" font-weight="700" text-anchor="middle">%d</text>'
          % (cx, y - 10, DEEP, val))
        a('<text x="%d" y="522" fill="%s" font-size="13" text-anchor="middle">2026-%s</text>'
          % (cx, GRAY, label.replace("月", "").zfill(2)))
    a('<line x1="110" y1="500" x2="780" y2="500" stroke="%s" stroke-width="1"/>' % LINE)
    a('<text x="72" y="546" fill="%s" font-size="12">月度推进节奏：7 月承接 33 项 → 8 月联调 24 项 → 9 月收尾 18 项</text>' % LIGHT)

    # ---- 右：需求状态构成 ----
    a('<rect x="828" y="290" width="404" height="270" rx="8" fill="#FFFFFF" stroke="#E3E8EF" stroke-width="1"/>')
    a('<text x="852" y="324" fill="%s" font-size="18" font-weight="700">需求状态构成</text>' % TITLE)
    a('<text x="1208" y="324" fill="%s" font-size="12" text-anchor="end">合计 %d</text>' % (LIGHT, ACCEPT_TOTAL))
    for i, (label, val, color) in enumerate(STATUS):
        y = 362 + i * 48
        a('<text x="852" y="%d" fill="%s" font-size="13">%s</text>' % (y + 16, GRAY, label))
        bw = val / 60 * 170
        a('<rect x="1000" y="%d" width="%.1f" height="22" rx="3" fill="%s"/>' % (y, bw, color))
        a('<text x="%.1f" y="%d" fill="%s" font-size="14" font-weight="700">%d</text>'
          % (1000 + bw + 10, y + 17, DEEP, val))
    a('<line x1="852" y1="510" x2="1208" y2="510" stroke="%s" stroke-width="1"/>' % LINE)
    a('<text x="852" y="536" fill="%s" font-size="12">60 + 7 + 8 = 75；我提出 15 项为其中子集，不重复计数</text>' % LIGHT)

    # ---- 状态分布参考条 ----
    a('<text x="48" y="596" fill="%s" font-size="15" font-weight="700">'
      '需求状态分布（效能看板口径，仅参考 · 不参与上线数计数）</text>' % TITLE)
    a('<rect x="48" y="610" width="1184" height="22" rx="4" fill="%s"/>' % ICE)
    offset = 48
    for _, val, color in STATUS:
        w = 1184 * val / ACCEPT_TOTAL
        a('<rect x="%.1f" y="610" width="%.1f" height="22" rx="4" fill="%s"/>' % (offset, w, color))
        offset += w
    a('<text x="48" y="646" fill="%s" font-size="12">'
      '进行中 60（80.0%%） · 待受理 7（9.3%%） · 已上线 8（10.7%%）　|　'
      '上线数 85 为版本排期口径，与此处状态分布不同源，不可相加</text>' % GRAY)

    # ---- 脚注 ----
    a('<line x1="48" y1="661" x2="1232" y2="661" stroke="#E3E8EF" stroke-width="1"/>')
    a('<text x="48" y="681" fill="%s" font-size="12">%s</text>' % (LIGHT, FOOT1))
    a('<text x="48" y="701" fill="%s" font-size="12">%s</text>' % (LIGHT, FOOT2))
    a('</svg>')
    return "\n".join(s)


def build_slide_inner():
    """述职 PPT P7 内页片段：复用主 HTML 的 hdr/ftr，只替换 .bp 内容。"""
    kpis = [
        ("本季度受理需求", "75", "按最后受理时间 · 含主受理与共同受理", False),
        ("本季度版本排期交付", "85", "按版本排期", True),
        ("端到端净交付", "26.95", "天 · IT 交付 19.55 天", False),
        ("全流程流动效率", "35.04%", "各阶段无阻滞高效流转", True),
    ]
    kpi_html = "".join(
        '<div class="q3k-card"><div class="q3k-label">%s</div>'
        '<div class="q3k-val" style="color:%s;">%s</div><div class="q3k-note">%s</div></div>'
        % (lab, RED if hi else DEEP, val, note) for lab, val, note, hi in kpis
    )
    bars = "".join(
        '<div class="q3bar-col"><div class="q3bar-num">%d</div>'
        '<div class="q3bar" style="height:%.1fpx;background:%s;"></div>'
        '<div class="q3bar-lab">2026-%s</div></div>'
        % (val, val / 40 * 185, BLUE if i < 2 else SOFT, lab.replace("月", "").zfill(2))
        for i, (lab, val) in enumerate(ACCEPT_MONTHS)
    )
    rows = "".join(
        '<div class="q3st-row"><span class="q3st-lab">%s</span>'
        '<div class="q3st-track"><div class="q3st-fill" style="width:%.1f%%;background:%s;"></div></div>'
        '<span class="q3st-val">%d</span></div>'
        % (lab, val / 60 * 100, color, val) for lab, val, color in STATUS
    )
    return """<div class="q3kpi-wrap">
  <div class="q3kpi-sub">吴进（125360） · 数据来源：科技平台效能度量看板 / 需求集合大宽表　|　统计区间：2026-07 ~ 2026-09　|　季度已完结</div>
  <div class="q3kpi-grid">%s</div>
  <div class="q3kpi-charts">
    <div class="q3kpi-panel">
      <div class="q3p-title">按最后受理时间分布 <span>合计 75 · 33+24+18</span></div>
      <div class="q3bar-chart">%s</div>
      <div class="q3p-foot">月度推进节奏：7 月承接 33 项 → 8 月联调 24 项 → 9 月收尾 18 项</div>
    </div>
    <div class="q3kpi-panel">
      <div class="q3p-title">需求状态构成 <span>合计 75</span></div>
      <div class="q3st-list">%s</div>
      <div class="q3p-foot">60 + 7 + 8 = 75；我提出 15 项为其中子集，不重复计数</div>
    </div>
  </div>
  <div class="q3kpi-ref">
    <div class="q3ref-title">需求状态分布（效能看板口径，仅参考 · 不参与上线数计数）</div>
    <div class="q3ref-bar"><span style="width:80.0%%;background:%s;"></span><span style="width:9.3%%;background:%s;"></span><span style="width:10.7%%;background:%s;"></span></div>
    <div class="q3ref-note">进行中 60（80.0%%） · 待受理 7（9.3%%） · 已上线 8（10.7%%）　|　上线数 85 为版本排期口径，与状态分布不同源，不可相加</div>
  </div>
  <div class="q3kpi-foot">%s<br>%s</div>
</div>
<style>
.q3kpi-wrap{display:flex;flex-direction:column;gap:10px;height:100%%;font-family:"Microsoft YaHei","PingFang SC",sans-serif;}
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
.q3bar{width:64%%;max-width:74px;border-radius:4px 4px 0 0;}
.q3bar-lab{position:absolute;bottom:-22px;left:0;right:0;text-align:center;font-size:11px;color:#666;line-height:18px;}
.q3p-foot{font-size:10.5px;color:#999;margin-top:6px;}
.q3st-list{flex:1;display:flex;flex-direction:column;justify-content:center;gap:22px;padding:6px 2px;}
.q3st-row{display:flex;align-items:center;gap:8px;font-size:11.5px;color:#666;}
.q3st-lab{width:86px;flex-shrink:0;}
.q3st-track{flex:1;height:16px;background:#E6F1FB;border-radius:3px;overflow:hidden;}
.q3st-fill{height:100%%;border-radius:3px;}
.q3st-val{width:24px;text-align:right;font-weight:700;color:#1F497D;font-size:13px;}
.q3kpi-ref{flex-shrink:0;}
.q3ref-title{font-size:12px;font-weight:700;color:#004E97;margin-bottom:5px;}
.q3ref-bar{display:flex;height:18px;border-radius:3px;overflow:hidden;background:#E6F1FB;}
.q3ref-bar span{display:block;height:100%%;}
.q3ref-note{font-size:10.5px;color:#666;margin-top:5px;}
.q3kpi-foot{flex-shrink:0;border-top:1px solid #E3E8EF;padding-top:6px;font-size:10px;color:#999;line-height:1.55;}
</style>
""" % (kpi_html, bars, rows, BLUE, SOFT, PALE, FOOT1, FOOT2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()
    out = args.out
    os.makedirs(out, exist_ok=True)

    svg = build_svg()
    svg_path = os.path.join(out, "本季度需求指标看板_Q3.svg")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)

    html_doc = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>本季度需求指标看板 · 2026 Q3</title>
<style>
  body{margin:0;background:#F4F6F9;font-family:"PingFang SC","Microsoft YaHei",Helvetica,Arial,sans-serif;color:#333;}
  .wrap{max-width:1280px;margin:24px auto 40px;padding:0 16px;}
  .bar{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:14px;font-size:13px;color:#666;}
  .bar strong{color:#1F497D;font-weight:500;}
  .stage{background:#FFFFFF;border:1px solid #E3E8EF;border-radius:8px;overflow:hidden;}
  svg{display:block;width:100%;height:auto;}
  .tip{margin-top:14px;font-size:12px;color:#999;line-height:1.7;}
  @media print{body{background:#fff}.wrap{margin:0;padding:0;max-width:none}.bar,.tip{display:none}.stage{border:0}}
</style>
</head>
<body>
<div class="wrap">
  <div class="bar"><span><strong>本季度需求指标看板 · 2026 Q3</strong> · 16:9 述职页图表（统计区间 07/01-09/30）</span><span>浏览器打印或截图即可插入 PPT；同目录另有 .svg 矢量文件</span></div>
  <div class="stage">
""" + svg + """
  </div>
  <div class="tip">同目录 .svg 为 1280×720 矢量文件，可无损插入 PPT；口径说明已随图内嵌，打印时本行自动隐藏。</div>
</div>
</body>
</html>
"""
    html_path = os.path.join(out, "本季度需求指标看板_Q3.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_doc)

    inner_path = os.path.join(out, "q3_slide7_inner.html")
    with open(inner_path, "w", encoding="utf-8") as f:
        f.write(build_slide_inner())

    for p in (svg_path, html_path, inner_path):
        print(p, os.path.getsize(p), "bytes")


if __name__ == "__main__":
    main()
