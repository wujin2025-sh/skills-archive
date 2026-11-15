# -*- coding: utf-8 -*-
"""本季度需求指标看板：生成 16:9 自包含 SVG + 预览 HTML（数据源：科技平台实时宽表 / 效能度量看板）"""
import os

OUT = "/Users/wujin/WorkBuddy/2026-11-11-08-45-37/docs"
os.makedirs(OUT, exist_ok=True)

DEEP = "#1F497D"
BLUE = "#0C72BB"
TITLE = "#004E97"
ICE = "#E6F1FB"
GRAY = "#666666"
LIGHT = "#999999"
GRID = "#DCE9F7"
LINE = "#B4C6DA"
SOFT = "#85B7EB"

s = []
a = s.append

a('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720" '
  'font-family="PingFang SC, Microsoft YaHei, Helvetica, Arial, sans-serif" role="img">')
a('<title>本季度需求指标看板</title>')
a('<desc>2026年第四季度吴进受理需求13项、版本排期交付需求54项，按版本排期与受理月份分布的图表看板</desc>')
a('<rect width="1280" height="720" fill="#FFFFFF"/>')
a('<rect x="0" y="0" width="1280" height="88" fill="%s"/>' % DEEP)
a('<text x="48" y="57" fill="#FFFFFF" font-size="34" font-weight="700">本季度需求指标看板</text>')
a('<text x="1232" y="55" fill="#CFE2F5" font-size="16" text-anchor="end">2026 Q4 · 10/01–12/31 · 截至 2026-11-11</text>')
a('<text x="48" y="119" fill="%s" font-size="14">吴进（125360） · 数据来源：科技平台效能度量看板 / 需求集合大宽表</text>' % GRAY)


def kpi(x, label, value, note):
    a('<rect x="%d" y="145" width="282" height="116" rx="8" fill="%s"/>' % (x, ICE))
    a('<rect x="%d" y="145" width="4" height="116" rx="2" fill="%s"/>' % (x, BLUE))
    a('<text x="%d" y="177" fill="%s" font-size="15">%s</text>' % (x + 20, TITLE, label))
    a('<text x="%d" y="232" fill="%s" font-size="46" font-weight="700">%s</text>' % (x + 20, DEEP, value))
    a('<text x="%d" y="253" fill="%s" font-size="12">%s</text>' % (x + 20, GRAY, note))


kpi(48, "本季度受理需求", "13", "按最后受理时间 · 含主受理与共同受理")
kpi(348, "本季度版本排期交付", "54", "按版本排期")
kpi(648, "覆盖版本排期", "7", "4 个主版本 + 3 个小版本")
kpi(948, "Q3 全季参照", "85", "同口径（版本排期）· Q4 未完结")

# ---- 左：按版本排期柱状图 ----
a('<rect x="48" y="290" width="760" height="270" rx="8" fill="#FFFFFF" stroke="#E3E8EF" stroke-width="1"/>')
a('<text x="72" y="324" fill="%s" font-size="18" font-weight="700">按版本排期分布</text>' % TITLE)
a('<text x="784" y="324" fill="%s" font-size="12" text-anchor="end">合计 54 · 分组求和 56，跨版本重复 2</text>' % LIGHT)

base_y = 500
for tick in (0, 4, 8, 12, 16):
    y = base_y - tick / 16 * 140
    a('<line x1="90" y1="%.1f" x2="780" y2="%.1f" stroke="%s" stroke-width="1"/>' % (y, y, GRID))
    a('<text x="82" y="%.1f" fill="%s" font-size="11" text-anchor="end" dominant-baseline="central">%d</text>'
      % (y, LIGHT, tick))

versions = [("20261009", "10/09", 16), ("20261023", "10/23", 15),
            ("20261106", "11/06", 12), ("20261120", "11/20", 10),
            ("其他版本", "其他", 3)]
for i, (name, label, val) in enumerate(versions):
    cx = 150 + i * 140
    h = val / 16 * 140
    y = base_y - h
    color = SOFT if name == "其他版本" else BLUE
    a('<rect x="%.1f" y="%.1f" width="84" height="%.1f" rx="4" fill="%s"/>' % (cx - 42, y, h, color))
    a('<text x="%d" y="%.1f" fill="%s" font-size="20" font-weight="700" text-anchor="middle">%d</text>'
      % (cx, y - 10, DEEP, val))
    a('<text x="%d" y="522" fill="%s" font-size="13" text-anchor="middle">%s</text>' % (cx, GRAY, label))
a('<line x1="90" y1="500" x2="780" y2="500" stroke="%s" stroke-width="1"/>' % LINE)
a('<text x="72" y="546" fill="%s" font-size="12">11/20 版本 10 项排期未到，Q4 为进行时数字</text>' % LIGHT)

# ---- 右：受理月份柱状图 ----
a('<rect x="828" y="290" width="404" height="270" rx="8" fill="#FFFFFF" stroke="#E3E8EF" stroke-width="1"/>')
a('<text x="852" y="324" fill="%s" font-size="18" font-weight="700">受理月份分布</text>' % TITLE)
a('<text x="1208" y="324" fill="%s" font-size="12" text-anchor="end">合计 13</text>' % LIGHT)
for tick in (0, 4, 8, 12, 16):
    y = base_y - tick / 16 * 140
    a('<line x1="870" y1="%.1f" x2="1190" y2="%.1f" stroke="%s" stroke-width="1"/>' % (y, y, GRID))
for cx, label, val in [(950, "2026-10", 11), (1090, "2026-11", 2)]:
    h = val / 16 * 140
    y = base_y - h
    a('<rect x="%d" y="%.1f" width="76" height="%.1f" rx="4" fill="%s"/>' % (cx - 38, y, h, BLUE))
    a('<text x="%d" y="%.1f" fill="%s" font-size="20" font-weight="700" text-anchor="middle">%d</text>'
      % (cx, y - 10, DEEP, val))
    a('<text x="%d" y="522" fill="%s" font-size="13" text-anchor="middle">%s</text>' % (cx, GRAY, label))
a('<line x1="870" y1="500" x2="1190" y2="500" stroke="%s" stroke-width="1"/>' % LINE)
a('<text x="852" y="546" fill="%s" font-size="12">口径：最后一次需求受理时间</text>' % LIGHT)

# ---- 状态分布参考条 ----
a('<text x="48" y="596" fill="%s" font-size="15" font-weight="700">需求状态分布（Story 行，仅参考 · 不参与上线数计数）</text>' % TITLE)
a('<rect x="48" y="610" width="1184" height="22" rx="4" fill="%s"/>' % ICE)
w_on = 1184 * 63 / 87
a('<rect x="48" y="610" width="%.1f" height="22" rx="4" fill="%s"/>' % (w_on, BLUE))
a('<rect x="%.1f" y="610" width="%.1f" height="22" rx="4" fill="%s"/>' % (48 + w_on, 1184 - w_on, SOFT))
a('<text x="48" y="646" fill="%s" font-size="12">已上线 63 行（72%%） · 在途 24 行（28%%）：SIT 测试待排期 12、SIT 生产测试待排期 4、待 SIT 生产测试 4、待开发集成 2、待 OA 审核 1、Story 待处理 1</text>' % GRAY)

# ---- 脚注 ----
a('<line x1="48" y1="661" x2="1232" y2="661" stroke="#E3E8EF" stroke-width="1"/>')
a('<text x="48" y="681" fill="%s" font-size="12">口径：受理数按最后一次需求受理时间，含主受理与共同受理；上线数按版本排期日期落在 2026Q4，按需求编号去重，不按需求状态筛选；已排除 2099-12-31 与年末 12-31 占位值。</text>' % LIGHT)
a('<text x="48" y="701" fill="%s" font-size="12">数据来源：科技平台效能度量看板 / 需求集合大宽表（实时全量 13,072 行，2026-11-11 09:20 拉取）。Q4 未完结，措辞用「平稳推进」。</text>' % LIGHT)
a('</svg>')

svg = "\n".join(s)
svg_path = os.path.join(OUT, "本季度需求指标看板.svg")
with open(svg_path, "w", encoding="utf-8") as f:
    f.write(svg)

html_doc = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>本季度需求指标看板</title>
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
  <div class="bar"><span><strong>本季度需求指标看板</strong> · 16:9 述职页图表（数据截至 2026-11-11）</span><span>浏览器打印或截图即可插入 PPT；同目录另有 .svg 矢量文件</span></div>
  <div class="stage">
""" + svg + """
  </div>
  <div class="tip">口径说明：受理数来自科技平台「效能度量」看板（按最后一次需求受理时间）；上线数来自需求集合大宽表 storyPlanLineDate（版本排期日期），按 demandId 去重，不按需求状态筛选，已排除 2099-12-31 与年末 12-31 占位值。Q4 未完结，为进行时态数字。</div>
</div>
</body>
</html>
"""
html_path = os.path.join(OUT, "本季度需求指标看板.html")
with open(html_path, "w", encoding="utf-8") as f:
    f.write(html_doc)

print("SVG:", svg_path, os.path.getsize(svg_path), "bytes")
print("HTML:", html_path, os.path.getsize(html_path), "bytes")
