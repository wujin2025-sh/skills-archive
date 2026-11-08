#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""需求依赖发现工具（ba-to-dev P0 第 15 条落地，v2 提速版）。

对需求「标题 + 原始需求正文」中的核心业务概念做本地全库反查，
列出所有提及同一业务概念的需求，供 BA 人工确认跨需求依赖（口径定义方/修改方、上下游关系）。

v2 改进（2026-11-01）：
1. 标题提取三级回退：Front Matter `title:` → 文档第一个 `# ` H1（自动剥离 YYYYMMDD-R26xxxxxxx- 前缀）→
   basename（同样剥离前缀）。修掉 v1 直接把完整文件名当标题、导致提取整个文件名当概念的缺陷
   （R2610270069 实战反查零命中）。
2. `search_concept` 优先用 `rg --iglob '*.md' -l -F` 定位命中文件，再逐行提取行号，
   避免全库 Python 逐行扫描（数百 MD 时显著提速）。
3. 无本地 MD 时不再直接退出：支持 `--summary "标题"` 传入平台标题自动提取概念，或纯概念反查（不依赖需求号）。
   --req-dir 可指定其他扫描目录（默认全库）。

用法:
    python3 demand_dep_find.py R2609160118                        # 自动从标题提取业务概念反查
    python3 demand_dep_find.py R2609160118 指定合约还款            # 指定单个业务概念反查
    python3 demand_dep_find.py R2609160118 指定合约还款 中签可用资金  # 指定多个业务概念反查
    python3 demand_dep_find.py R2610270069 --summary "【顶点两融柜台】99_10交易节点下线"  # 无 MD 时用平台标题
    python3 demand_dep_find.py --concept 顶点两融柜台 99_10        # 纯概念反查（不带需求号）

⚠️ 反查词必须是「业务概念」（业务对象/行为/场景词），严禁用特化字段名（ipoavl/day_total_repay_amt/表名字段）。
   实测教训：R2609160118 与 R2607240079 共享「指定合约还款」概念，原始正文均含；但 R2609160118 原始正文
   不含 ipoavl/day_total_repay_amt 特化字段，若用字段名反查会漏判依赖。
"""
import os
import re
import sys
import glob
import shutil
import subprocess

DEMAND_DIR = "/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析"
STOPWORDS = {"关于", "需求", "优化", "改造", "的", "和", "与", "及", "支持", "增加",
             "调整", "相关", "系统", "业务", "功能", "实现", "进行", "一个", "对此",
             "本次", "目前", "针对", "为了", "拟", "将", "该", "此", "其",
             "公告", "客户", "交易", "市场", "账户", "公司", "数据", "自动",
             "引入", "涉及", "内容", "背景", "操作", "提供"}
# 常见业务修饰词：剥离后生成更通用的业务概念（如「指定合约直接还款」→「指定合约还款」，
# 否则过细概念（带「直接」）无法与其他需求（用「指定合约还款」）匹配）
MODIFIERS = ["直接", "普通", "批量", "单笔", "自动", "手动", "实时", "指定", "个微",
             "两融", "专项", "首次", "顶点", "平台", "在线"]
# 标准文件名前缀，如 20261027-R2610270069- / 20260904-R2609040027-
NAME_PREFIX = re.compile(r"^\d{8}(-R\d{6,})?-+")


def find_demand_file(req_id, root=DEMAND_DIR):
    """按需求号定位本地文档（优先精确 basename，其次包含匹配）。"""
    exact = None
    for f in glob.glob(os.path.join(root, "**", "*.md"), recursive=True):
        if req_id in os.path.basename(f):
            if os.path.basename(f).startswith(req_id + "-"):
                return f
            if exact is None:
                exact = f
    return exact


def extract_title(content, f):
    """三级回退提取标题：Front Matter title: → 首个 H1（剥离日期/需求号前缀）→ basename 剥离前缀。"""
    m = re.search(r"^title:\s*(.+?)\s*$", content, re.M)
    if m:
        return m.group(1).strip()
    m = re.search(r"^#\s+(.+?)\s*$", content, re.M)
    if m:
        t = m.group(1).strip()
        return NAME_PREFIX.sub("", t) or t
    b = os.path.basename(f)
    stripped = NAME_PREFIX.sub("", b)
    return stripped[:-3] if stripped.endswith(".md") else stripped


def extract_concepts(title):
    """从标题自动提取核心业务概念（去掉「关于/需求/优化/改造」等前后缀与停用词）。

    v2.1：支持「【】」内部独立成概念（如 【顶点两融柜台】99_10交易节点下线
    → 顶点两融柜台 + 99_10交易节点下线，避免整句作单一概念导致全库零命中）。
    """
    t = re.sub(r"^关于", "", title)
    t = re.sub(r"需求$", "", t)
    concepts = []

    def push(p):
        p = p.strip("关于需求优化改造。 【】")
        if p and p not in STOPWORDS and len(p) >= 2:
            concepts.append(p)
            # 剥离修饰词生成通用子概念
            for mod in MODIFIERS:
                if mod in p:
                    sub = p.replace(mod, "")
                    sub = sub.strip("的、和与及 【】")
                    if sub and sub not in STOPWORDS and len(sub) >= 2:
                        concepts.append(sub)

    # 【】内部单独成概念
    for b in re.findall(r"【([^】]+)】", t):
        push(b)
    # 去掉【】块后按连接词切分
    t2 = re.sub(r"【[^】]+】", "", t)
    for part in re.split(r"[的、和与及,，;；]", t2):
        push(part)
    # 去重保序（保留原文概念在前，修饰变体在后）
    seen = set()
    out = []
    for c in concepts:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _rg_available():
    return shutil.which("rg") is not None


def search_concept(concept, exclude_file, root=DEMAND_DIR):
    """全库反查业务概念，返回 [(文件名, [(行号, 文本截断)...])...]。

    优先 rg -F 定位命中文件，再只对命中文件逐行取行号；无 rg 时回退 Python 全量扫描。
    """
    excl = os.path.abspath(exclude_file) if exclude_file else None
    hits = []
    if _rg_available():
        try:
            p = subprocess.run(["rg", "--iglob", "*.md", "-l", "-F", "--", concept, root],
                               capture_output=True, text=True, timeout=60)
            files = [l for l in p.stdout.splitlines() if l.strip()]
        except (subprocess.OSError, subprocess.TimeoutExpired):
            files = None
    else:
        files = None

    if files is None:  # rg 失败/无 rg → 全量 glob 扫描（兼容旧逻辑）
        files = []
        for f in glob.glob(os.path.join(root, "**", "*.md"), recursive=True):
            if excl and os.path.abspath(f) == excl:
                continue
            try:
                with open(f, encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
            except OSError:
                continue
            if concept in content:
                files.append(f)

    for f in files:
        if excl and os.path.abspath(f) == excl:
            continue
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
        except OSError:
            continue
        matched = []
        for i, line in enumerate(content.splitlines(), 1):
            if concept in line:
                matched.append((i, line.strip()[:90]))
        if matched:
            hits.append((os.path.basename(f), matched[:6]))
    return hits


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1

    # 纯概念反查模式：--concept c1 c2 ...
    if "--concept" in args:
        i = args.index("--concept")
        concepts = [a for a in args[i + 1:] if not a.startswith("--")]
        req_id, extra, f, content, title = None, concepts, None, "", ""
    else:
        req_id = args[0]
        extra = [a for a in args[1:] if not a.startswith("--")]
        f = find_demand_file(req_id)
        if not f:
            if "--summary" in args:
                j = args.index("--summary")
                summary = args[j + 1] if j + 1 < len(args) else ""
                concepts = extract_concepts(summary) or [summary]
                print(f"✗ 本地无 {req_id} 的 MD，已用 --summary 标题提取概念反查：{concepts}")
                req_id, f, content, title = req_id, None, "", summary
                extra = concepts
            elif extra:
                print(f"✗ 本地无 {req_id} 的 MD，使用指定概念 {extra} 反查。")
            else:
                print(f"✗ 未找到需求 {req_id} 的本地文档（{DEMAND_DIR}）")
                print("  可用 --summary \"平台标题\" 提取概念，或直接 --concept 概念1 概念2 反查。")
                return 2
        else:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
            title = extract_title(content, f)

    if f is None:
        concepts = extra
    else:
        concepts = extra or extract_concepts(title)
    if not concepts:
        print("✗ 未能自动提取业务概念，请手动指定关键词，如：demand_dep_find.py R2609160118 指定合约还款")
        return 3

    doc_name = os.path.basename(f) if f else "（无本地 MD）"
    print(f"需求   : {req_id or '-'}")
    print(f"文档   : {doc_name}")
    print(f"标题   : {title or '-'}")
    print(f"反查概念: {concepts}\n" + "=" * 60)

    for c in concepts:
        hits = search_concept(c, f)
        print(f"\n### 业务概念「{c}」反查结果")
        if not hits:
            print("   （无其他需求命中）")
            continue
        for fn, lines in hits:
            print(f"  ▶ {fn}")
            for ln, txt in lines:
                print(f"      L{ln}: {txt}")

    print("\n" + "=" * 60)
    print("提示：命中多个需求时，重点甄别「口径定义方 vs 口径修改方 / 上下游数据依赖」类关系，")
    print("确认后写入文档「相关链接」小节，避免口径变更/共享业务对象类依赖漏判。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
