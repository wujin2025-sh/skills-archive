# -*- coding: utf-8 -*-
"""把 02 模块双页（本季度需求指标看板 + 版本集成发布情况）一次性落入述职 HTML。

取代旧版手工分两步的做法（先替换 P7、再 insert_release_slide.py 插 P8）：
本脚本从**原始母版** --base 重建，同时完成：
  1. 注入两段内页 CSS
  2. 替换 P7 页眉标题 / tag / .bp 内容
  3. 在 SLIDE 8 前插入 P8
  4. 目录 02 模块改写为双页导航，03/04 模块页码与 pill 序号顺延
  5. 全篇页脚页码 / ht-num / 压轴讨论页序号 / 注释编号统一重排
幂等：永远从 --base 读取，重复执行不会重复插页或重复注入 CSS。

目录文案中的数字（版本数、发版次数、问题数）从 Excel 现场统计，不写死季度。

用法：
  python insert_quarter_pages.py --quarter 2026Q3 \
      [--main <输出HTML>] [--base <母版>] [--out <inner片段目录>]
"""
import os
import re
import sys
import json
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(SCRIPT_DIR, "quarter_config.json")
sys.path.insert(0, SCRIPT_DIR)
from gen_kpi_dashboard_q import quarter_meta, load_config  # noqa: E402
import gen_release_dashboard as rel  # noqa: E402

BASE_SLIDE7 = {
    "comment": "SLIDE 7: 06 科技平台效能度量实证",
    "title": "科技平台交付效能度量实证",
    "tag": "客观数据直证 · 高效流动归因",
}

SLIDE_TPL = """<!-- ==================== 新增页：版本集成发布情况（P7 之后） ==================== -->
<div class="slide">
  <div class="hdr">
    <div class="logo-box"><span>国泰海通</span></div>
    <span class="ht-num">__NUM__</span>
    <span class="ht">版本集成发布情况</span>
    <span class="ht-tag">02 模块 · 集成发布实证</span>
    <span class="hn">GUOTAIHAITONG | 吴进</span>
  </div>
  <div class="bp">
__INNER__
  </div>
  <div class="ftr">
    <span class="fo">国泰海通证券 交易结算业务创新组</span>
    <span class="fp">__PAGE__ / __TOTAL__</span>
  </div>
</div>

"""


def parse_inner(path):
    raw = open(path, encoding="utf-8").read()
    if "\n<style>\n" in raw:
        markup, rest = raw.split("\n<style>\n", 1)
    else:
        markup, rest = raw.split("<style>", 1)
    css = rest.split("</style>", 1)[0]
    markup = re.sub(r"^\s*<!--.*?-->\s*", "", markup, flags=re.S).strip()
    return markup, css


def release_stats(cfg, meta):
    xlsx = cfg["paths"]["xlsx"]
    if not os.path.exists(xlsx):
        raise FileNotFoundError("缺少版本发布 Excel：%s（可先跑 fetch_release_workbook.py）" % xlsx)
    allrows, mine = rel.load_rows(xlsx, meta["months"], cfg["release_doc"]["owner"])
    return rel.stat(allrows, mine, meta["months"], cfg["release_doc"]["owner"])


def pills_html(items):
    return ('<div class="agenda-pills">\n' +
            "\n".join('          <span class="agenda-pill">%s</span>' % x for x in items) +
            "\n        </div>")


def bump_pill(src, old_text):
    """把 '07 产品经理个人驾驶舱' 的章节号 +1"""
    m = re.match(r"^(\d+)\s+(.*)$", old_text)
    if not m:
        return
    new_text = "%02d %s" % (int(m.group(1)) + 1, m.group(2))
    old = '<span class="agenda-pill">%s</span>' % old_text
    new = '<span class="agenda-pill">%s</span>' % new_text
    if old not in src:
        print("  [warn] 目录 pill 未匹配：", old_text)
        return src
    return src.replace(old, new, 1)


def rewrite_agenda(src, cfg, meta, k, stats):
    base, tpl = cfg["base_agenda"], cfg["agenda_tpl"]
    fmt = dict(accept=k["accept_total"], release=k["release_total"], tag=meta["tag"],
               versions=stats["total"], times=stats["times"], problems=stats["problems"])

    # 02 模块标题 / 描述
    assert base["m02_title"] in src, "母版 02 模块标题锚点未匹配"
    assert base["m02_desc"] in src, "母版 02 模块描述锚点未匹配"
    src = src.replace(base["m02_title"],
                      '<div class="agenda-title">%s</div>' % tpl["m02_title"].format(**fmt), 1)
    src = src.replace(base["m02_desc"],
                      '<div class="agenda-desc">%s</div>' % tpl["desc"].format(**fmt), 1)

    # 02 模块 pills：定位该卡片内的 pills 块（母版第 2 个 agenda-pills）
    anchor = src.index('<div class="agenda-title">%s</div>' % tpl["m02_title"])
    ps = src.index('<div class="agenda-pills">', anchor)
    pe = src.index("</div>", ps) + len("</div>")
    src = src[:ps] + pills_html([x.format(**fmt) for x in tpl["pills"]]) + src[pe:]

    # 03 / 04 模块页码区间与 pill 序号顺延
    for key in ("m03_range", "m04_range"):
        if base[key] in src:
            src = src.replace(base[key], tpl[key], 1)
        else:
            print("  [warn] 目录页码区间未匹配：", base[key])
    for key in ("m03_pills", "m04_pills"):
        for text in base[key]:
            src = bump_pill(src, text)
    return src


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarter", required=True)
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--main", default=None)
    ap.add_argument("--base", default=None)
    ap.add_argument("--out", default=None, help="inner 片段所在目录，缺省取 paths.out_dir")
    ap.add_argument("--kpi-inner", default=None)
    ap.add_argument("--release-inner", default=None)
    ap.add_argument("--skip-agenda", action="store_true")
    args = ap.parse_args()

    meta = quarter_meta(args.quarter)
    cfg, k = load_config(args.config, meta["quarter"])
    paths, layout = cfg["paths"], cfg["layout"]
    main_html = args.main or paths["main_html"]
    base = args.base or paths["base_html"]
    out = args.out or paths["out_dir"]
    tag = meta["tag"]
    kpi_inner = args.kpi_inner or os.path.join(out, "kpi_slide_inner_%s.html" % tag)
    rel_inner = args.release_inner or os.path.join(out, "release_slide_inner_%s.html" % tag)
    for p in (base, kpi_inner, rel_inner):
        if not os.path.exists(p):
            raise FileNotFoundError(p)

    src = open(base, encoding="utf-8").read()
    kpi_markup, kpi_css = parse_inner(kpi_inner)
    rel_markup, rel_css = parse_inner(rel_inner)

    # 1) 两段 CSS 注入 head（母版只有一处 </style>，避免污染其它样式块）
    he = src.index("</style>")
    src = (src[:he] + "\n/* ===== 02 模块双页：需求指标看板 + 版本集成发布（%s） ===== */\n"
           % meta["quarter"] + kpi_css + "\n" + rel_css + "\n" + src[he:])

    # 2) P7：标题 / tag / .bp 内容
    s = src.index("<!-- ==================== SLIDE 7:")
    e = src.index(layout["insert_before"])
    block = src[s:e]
    assert '<span class="ht">%s</span>' % BASE_SLIDE7["title"] in block, "母版 P7 标题未匹配"
    block = block.replace('<span class="ht">%s</span>' % BASE_SLIDE7["title"],
                          '<span class="ht">本季度需求指标看板</span>', 1)
    block = block.replace('<span class="ht-tag">%s</span>' % BASE_SLIDE7["tag"],
                          '<span class="ht-tag">受理 + 版本排期双口径</span>', 1)
    block = block.replace(BASE_SLIDE7["comment"], "SLIDE 7: 06 本季度需求指标看板", 1)
    i = block.index('<div class="bp">') + len('<div class="bp">')
    j = block.index('<div class="ftr">')
    block = block[:i] + "\n" + kpi_markup + "\n  </div>\n  " + block[j:]
    src = src[:s] + block + src[e:]

    # 3) 插入 P8
    slide = (SLIDE_TPL.replace("__NUM__", layout["release_num"])
             .replace("__INNER__", rel_markup)
             .replace("__PAGE__", "%02d" % layout["release_page"])
             .replace("__TOTAL__", str(layout["total_pages"])))
    assert layout["insert_before"] in src
    src = src.replace(layout["insert_before"], slide + layout["insert_before"], 1)

    # 4) 目录
    if not args.skip_agenda:
        src = rewrite_agenda(src, cfg, meta, k, release_stats(cfg, meta))

    # 5) 页码 / 章节号 / 压轴讨论页 / 注释编号
    total = layout["total_pages"]
    fp = iter(range(2, total))
    src, nfp = re.subn(r'(<span class="fp">)\s*\d+\s*/\s*\d+',
                       lambda m: m.group(1) + ("%02d / %d" % (next(fp), total)), src)
    hn = iter(range(1, total - 2))
    src, nhn = re.subn(r'(<span class="ht-num">)\s*\d+',
                       lambda m: m.group(1) + ("%02d" % next(hn)), src)
    m = re.search(r'(font-size:22px;font-family:Arial,sans-serif;font-weight:800;">)(\d+)(</span>)', src)
    if m:
        src = src[:m.start(2)] + str(int(m.group(2)) + 1) + src[m.end(2):]
    src = re.sub(r"SLIDE (\d+):",
                 lambda x: "SLIDE %d:" % (int(x.group(1)) + 1
                                          if int(x.group(1)) >= layout["release_page"]
                                          else int(x.group(1))), src)

    open(main_html, "w", encoding="utf-8").write(src)
    slides = src.count('<div class="slide">')
    print("完成：%s | slides=%d | 页脚重排 %d | 章节号重排 %d | 旧标题残留 %d"
          % (main_html, slides, nfp, nhn, src.count(BASE_SLIDE7["title"])))
    if slides != total:
        raise RuntimeError("页数 %d ≠ 配置 total_pages %d，请检查母版或插入锚点" % (slides, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
