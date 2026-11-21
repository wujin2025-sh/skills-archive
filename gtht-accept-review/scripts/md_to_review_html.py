#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md_to_review_html.py — 截取 ba-to-dev 需求 MD 的「评审纪要」小节并转换为
review_requirement / add_requirement_review_minutes 参数 mettingSummary 的 HTML。

用法:
    python md_to_review_html.py <需求MD路径>
    python md_to_review_html.py <需求MD路径> --out /tmp/review_summary.html   # 同时写文件

输出:
    stdout 打印 1 个 <p> 包裹的 HTML（<br> 换行、<strong> 加粗、&nbsp; 缩进），
    末尾必含「预计上线日期」行（「评审决策日志」可选小节会自动截断，不进入纪要正文），
    可直接复制填入 Step 4a / Step 6a 的 mettingSummary 参数。

转换规则（与 SKILL.md「mettingSummary HTML 转换规则」一致，2026-10-12 用户偏好固化）:
  1. 小节定位: 从「#### 评审纪要」/「## 评审纪要」标题行起，至「---」分隔线 / 下一章节标题 /
     「评审决策日志」标题（5 个 #） / 文件末尾止
     （「##### **评审决策日志**」为 5 个 #，属内部决策记录，命中即截断，不进入纪要正文）；
  2. 行类型与缩进（&nbsp; 半角空格，禁 &emsp;）:
     - 首行（沟通时间与人员）与标题行（`N. **小节名**：`）: 无缩进;
     - 内容行（标题下的正文行）与 `(N)` 子条目行: 3 个 &nbsp;（对齐标题首字）;
     - `①/②…` 行: 7 个 &nbsp;（对齐 `(1)` 后文字首字）;
     - `#####` / `>` 开头行（决策日志子标题/决策行）: 无缩进原样输出;
  3. **加粗** -> <strong></strong>; 行间 <br>; 全部合并进 1 个 <p>（严禁逐行 <p>）;
     首行（沟通时间与人员）后空一行（<br><br>）与下方内容分隔;
  4. 小节内必须含「预计上线日期」行, 缺失则 exit 1（供前置自检）。

退出码:
  0=成功; 1=小节缺失/缺预计上线日期（向 stderr 输出原因）。
"""

import argparse
import html
import re
import sys
from pathlib import Path

SECTION_RE = re.compile(r"^#{2,4}\s*\*?\*?评审纪要\*?\*?\s*$")
# 术语：下一章节标题（1-4 个 #）或分隔线
SECTION_END_RE = re.compile(r"^(?:\s*---+\s*$|#{1,4}\s)")
# 评审决策日志标题（5 个 #，位于「预计上线日期」之后）：属内部决策记录，不进入 mettingSummary
DECISION_LOG_RE = re.compile(r"^#{5}\s*\*?\*?评审决策日志\*?\*?\s*(?:：|:|$)")
TITLE_RE = re.compile(r"^\d+\.\s")          # 1. **需求补充说明**：
SUBITEM_RE = re.compile(r"^(?:\(\d+\)|（\d+）)\s")  # (1) 系统A：
CIRCLE_RE = re.compile(r"^[①-⑩]")           # ① 功能点一。


def md_line_to_html(line: str) -> str:
    """单行 Markdown -> HTML：先转义（保留 ** 供加粗标记），再把 **x** -> <strong>x</strong>。"""
    escaped = html.escape(line, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", lambda m: "<strong>%s</strong>" % m.group(1), escaped)
    return escaped


def extract_review_lines(md_text: str):
    """返回评审纪要小节的行列表（不含标题行），无小节返回 None。"""
    lines = md_text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if SECTION_RE.match(line.strip()):
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start, len(lines)):
        stripped = lines[j].strip()
        if not stripped:
            continue
        # 评审决策日志（内部决策记录）不进入评审纪要正文：命中即终止小节
        if DECISION_LOG_RE.match(stripped):
            end = j
            break
        if SECTION_END_RE.match(stripped) and not SECTION_RE.match(stripped):
            end = j
            break
    return lines[start:end]


def build_html(lines) -> str:
    html_lines = []
    first_content = True
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if first_content:
            # 首行（沟通时间与人员）无缩进；其后空一行（<br><br>）与下方内容分隔，观感更清晰
            html_lines.append(md_line_to_html(line))
            html_lines.append("")  # 空元素 -> join 时产生额外 <br>，实现首行后空行
            first_content = False
            continue
        if line.startswith("预计上线日期"):
            # 预计上线日期行：无缩进（与首行首字符左侧对齐），前空一行与上方内容分隔
            html_lines.append("")  # 空元素 -> join 时产生额外 <br>，实现空行
            html_lines.append(md_line_to_html(line))
            continue
        if line.startswith("#####") or line.startswith(">"):
            indent = ""  # 决策日志子标题 / 决策引用行（v17 位置在预计上线日期之后）
        elif CIRCLE_RE.match(line):
            indent = "&nbsp;" * 7  # ① 行：对齐 (1) 后文字首字
        elif TITLE_RE.match(line):
            indent = ""  # N. **小节名**：标题行
        else:
            indent = "&nbsp;" * 3  # 内容行 / (N) 子条目行：对齐标题首字
        html_lines.append(indent + md_line_to_html(line))
    return "<p>" + "<br>\n".join(html_lines) + "</p>"


def main():
    parser = argparse.ArgumentParser(description="评审纪要 MD -> mettingSummary HTML")
    parser.add_argument("md_path", help="ba-to-dev 需求分析 Markdown 文件路径")
    parser.add_argument("--out", help="可选：同时将 HTML 写入指定文件")
    args = parser.parse_args()

    md_path = Path(args.md_path)
    if not md_path.is_file():
        print(f"错误: 文件不存在: {md_path}", file=sys.stderr)
        sys.exit(1)

    md_text = md_path.read_text(encoding="utf-8")
    lines = extract_review_lines(md_text)
    if lines is None:
        print("错误: 未找到「#### 评审纪要」/「## 评审纪要」小节", file=sys.stderr)
        sys.exit(1)

    html_out = build_html(lines)
    if "预计上线日期" not in html_out:
        print("错误: 评审纪要小节内缺失「预计上线日期」行，禁止提交", file=sys.stderr)
        sys.exit(1)

    # 原样输出单行（便于复制）；--out 同时写文件
    print(html_out)
    if args.out:
        Path(args.out).write_text(html_out + "\n", encoding="utf-8")
        print(f"[已写入] {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
