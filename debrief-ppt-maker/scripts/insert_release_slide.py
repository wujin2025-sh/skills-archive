# -*- coding: utf-8 -*-
"""把「版本集成发布情况」页插入述职 HTML（默认插在原 SLIDE 8 之前，即需求指标看板之后），
并同步 02 模块目录、全篇页码与章节序号。

幂等设计：始终从 `--backup`（12 页母版）读取重建，重复执行不会重复插页或重复注入 CSS。
换季度时：更新 AGENDA_REPL 中的目录文案，必要时调整页脚总数 --total 与新页序号。

依赖产物：gen_release_dashboard.py 生成的 `release_slide_inner_<TAG>.html`（含 markup + <style> 块）。
"""
import os
import re
import argparse
import shutil

# 2026Q3 目录页替换表（换季度需同步更新）
AGENDA_REPL = [
    ("<div class=\"agenda-title\">本季度需求指标看板（P07）</div>",
     "<div class=\"agenda-title\">需求指标与版本集成发布（P07 ~ P08）</div>"),
    ("<div class=\"agenda-desc\">受理 75 项、版本排期交付 85 项；端到端净交付 26.95 天、流动效率 35.04%</div>",
     "<div class=\"agenda-desc\">受理 75 项、版本排期交付 85 项；Q3 负责 10 个版本、27 次发版，已登记 0 起发版问题</div>"),
    ("<span class=\"agenda-pill\">受理 75 项 · 排期交付 85 项</span>",
     "<span class=\"agenda-pill\">06 本季度需求指标看板</span>"),
    ("<span class=\"agenda-pill\">端到端 26.95 天</span>",
     "<span class=\"agenda-pill\">07 版本集成发布情况</span>"),
    ("<span class=\"agenda-pill\">流动效率 35.04%</span>",
     "<span class=\"agenda-pill\">受理 75 · 排期 85 · 发版 27 次</span>"),
    ("数字化驾驶舱与 AI 智能体建设（P08 ~ P09）", "数字化驾驶舱与 AI 智能体建设（P09 ~ P10）"),
    ("<span class=\"agenda-pill\">07 产品经理个人驾驶舱</span>", "<span class=\"agenda-pill\">08 产品经理个人驾驶舱</span>"),
    ("<span class=\"agenda-pill\">08 需求分析 SKILL 流水线</span>", "<span class=\"agenda-pill\">09 需求分析 SKILL 流水线</span>"),
    ("后续工作规划与难点创新点讨论（P10 ~ P11）", "后续工作规划与难点创新点讨论（P11 ~ P12）"),
    ("<span class=\"agenda-pill\">09 后续工作规划（五阶蓝）</span>", "<span class=\"agenda-pill\">10 后续工作规划（五阶蓝）</span>"),
    ("<span class=\"agenda-pill\">10 难点创新点讨论（难点与建议）</span>", "<span class=\"agenda-pill\">11 难点创新点讨论（难点与建议）</span>"),
]

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--main", required=True, help="述职主 HTML 路径（就地更新）")
    ap.add_argument("--inner", required=True, help="gen_release_dashboard.py 产出的内页片段")
    ap.add_argument("--backup", required=True, help="插页前的母版备份路径；不存在则自动创建")
    ap.add_argument("--total", type=int, default=13)
    ap.add_argument("--new-page", type=int, default=8, help="新页在整份 PPT 中的物理页码")
    ap.add_argument("--new-num", default="07", help="新页 ht-num 章节序号")
    ap.add_argument("--insert-before", default="<!-- ==================== SLIDE 8:")
    ap.add_argument("--skip-agenda", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.backup):
        shutil.copy2(args.main, args.backup)
        print("母版备份已创建：", args.backup)
    src = open(args.backup, encoding="utf-8").read()

    raw = open(args.inner, encoding="utf-8").read()
    markup, rest = raw.split("\n<style>\n", 1)
    css = rest.split("</style>", 1)[0]
    markup = re.sub(r"<!--.*?-->", "", markup, count=1).strip()

    # 1) 样式注入 head
    he = src.index("</style>")
    src = src[:he] + "\n/* ===== 版本集成发布情况（P%d） ===== */\n" % args.new_page + css + "\n" + src[he:]

    # 2) 插入新页
    slide = (SLIDE_TPL.replace("__NUM__", args.new_num)
             .replace("__INNER__", markup)
             .replace("__PAGE__", "%02d" % args.new_page)
             .replace("__TOTAL__", str(args.total)))
    assert args.insert_before in src, "未找到插入锚点：" + args.insert_before
    src = src.replace(args.insert_before, slide + args.insert_before, 1)

    # 3) 目录页 02 模块纳入双页，03/04 顺延
    if not args.skip_agenda:
        for a, b in AGENDA_REPL:
            if a not in src:
                print("  [warn] 目录未匹配，跳过：", a[:60])
                continue
            src = src.replace(a, b, 1)

    # 4) 全篇页码 / 章节序号重排（按文档出现顺序）
    fp = iter(range(2, args.total))
    src, nfp = re.subn(r'(<span class="fp">)\s*\d+\s*/\s*\d+',
                       lambda m: m.group(1) + ("%02d / %d" % (next(fp), args.total)), src)
    hn = iter(range(1, args.total - 2))   # 13 页时 -> 01..10（目录页 + 9 个正文页）
    src, nhn = re.subn(r'(<span class="ht-num">)\s*\d+',
                       lambda m: m.group(1) + ("%02d" % next(hn)), src)
    # 压轴讨论页的序号放在 logo-box 内，单独顺延
    old = 'font-size:22px;font-family:Arial,sans-serif;font-weight:800;">10</span>'
    if old in src:
        src = src.replace(old, old.replace(">10<", ">11<"), 1)
    # 注释编号顺延，保持与物理页一致
    src = re.sub(r"SLIDE (\d+):",
                 lambda m: "SLIDE %d:" % (int(m.group(1)) + 1 if int(m.group(1)) >= args.new_page else int(m.group(1))),
                 src)

    open(args.main, "w", encoding="utf-8").write(src)
    print("完成：slides=%d | 页脚重排 %d | 章节号重排 %d | 输出 %s"
          % (src.count('<div class="slide">'), nfp, nhn, args.main))


if __name__ == "__main__":
    main()
