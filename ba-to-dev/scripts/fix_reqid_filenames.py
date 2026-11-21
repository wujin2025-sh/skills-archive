#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ba-to-dev 文件名需求号补全工具：把 9 位残缺号批量修回 R + 10 位。

背景（2026-11-19）：
  validate_ba_md.py 的 FN_RE 曾允许 R\\d{9,11}，extract_demand.py 入参曾允许 R\\d{6,}，
  两处口径都过松，导致库内累积了一批文件名写 9 位、正文/Front Matter 写 10 位的文档。
  这类文档对 R\\d{10} 检索永久不可见（既不进命中分子，也不进分母），
  更有 2 对因截断撞成同一文件名，实为 4 个不同需求，存在互相覆盖风险。

判定规则（按可信度从高到低，命中即停）：
  1) Front Matter 的 req_id 为合法 R + 10 位
  2) 正文内合法需求号中，唯一一个「以残缺号开头」（截断只丢了末位，故必为前缀）
  3) 正文内合法需求号全库唯一
  三者都不成立 → 列入「需人工」，不动文件。

安全约束：
  - 默认 dry-run，只打印对照表；加 --apply 才真正改名
  - 目标文件名已存在 → 拒绝改名（防覆盖），列入「撞名」单独列出
  - 只改文件名，不读改文件内容
  - --apply 时把旧名→新名对照追加写入 --log 指定的 Markdown（便于反向还原）

用法:
    python3 fix_reqid_filenames.py /path/to/需求分析                 # 预览
    python3 fix_reqid_filenames.py /path/to/需求分析 --apply         # 执行
    python3 fix_reqid_filenames.py . --apply --log 999_Meta/log.md   # 执行并留痕
"""
import argparse
import glob
import os
import re
import sys
from datetime import datetime

REQ10 = re.compile(r"R\d{10}")
FM_REQ = re.compile(r'^req_id:\s*"?([^"\n]+)"?\s*$', re.M)


def read(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()


def resolve_new_id(name, text):
    """返回 (new_id, 依据)；new_id 为 None 表示需人工。"""
    old_ids = re.findall(r"R\d+", name)
    old = old_ids[0]

    m = FM_REQ.search(text)
    if m:
        fm = m.group(1).strip()
        if REQ10.fullmatch(fm):
            return fm, "Front Matter req_id"

    body = set(REQ10.findall(text))
    prefix = sorted(c for c in body if c.startswith(old))
    if len(prefix) == 1:
        return prefix[0], "前缀补位"
    if len(body) == 1:
        return next(iter(body)), "正文唯一号"
    if len(prefix) > 1:
        return None, f"前缀有 {len(prefix)} 个候选：{', '.join(prefix)}"
    return None, f"正文有 {len(body)} 个候选：{', '.join(sorted(body))}"


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("root", nargs="?", default=".", help="扫描根目录（递归）")
    ap.add_argument("--apply", action="store_true", help="真正改名（默认只预览）")
    ap.add_argument("--log", default="", help="把对照表追加写入该 Markdown 文件")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        sys.exit(f"✗ 不是目录：{root}")

    todo, manual, collide, clean = [], [], [], 0
    for path in sorted(glob.glob(os.path.join(root, "**", "*.md"), recursive=True)):
        name = os.path.basename(path)
        ids = re.findall(r"R\d+", name)
        if not ids:
            continue
        if any(len(i) == 11 for i in ids):
            clean += 1
            continue
        old = ids[0]
        new, why = resolve_new_id(name, read(path))
        if not new:
            manual.append((name, why))
            continue
        target = name.replace(old, new, 1)
        if os.path.exists(os.path.join(os.path.dirname(path), target)):
            collide.append((name, target))
            continue
        todo.append((path, name, target, why))

    print(f"扫描：{root}")
    print(f"  已合规（文件名含 R+10 位）: {clean}")
    print(f"  待修复                    : {len(todo)}")
    print(f"  需人工判定                : {len(manual)}")
    print(f"  撞名（拒绝改名）          : {len(collide)}")
    print()

    if todo:
        print("待修复对照表：")
        for path, name, target, why in todo:
            rel = os.path.relpath(path, root)
            print(f"  [{why}] {rel}")
            print(f"      → {target}")
        print()

    if manual:
        print("需人工判定（未改动）：")
        for name, why in manual:
            print(f"  {name}")
            print(f"      原因：{why}")
        print()

    if collide:
        print("撞名（目标已存在，未改动）：")
        for name, target in collide:
            print(f"  {name}\n      → {target}")
        print()

    if not args.apply:
        print("以上为预览。加 --apply 执行改名。")
        return 1 if (manual or collide) else 0

    if not todo:
        print("无待修复文件，跳过。")
        return 0

    lines = []
    for path, name, target, why in todo:
        d = os.path.dirname(path)
        os.rename(path, os.path.join(d, target))
        lines.append(f"- `{name}` → `{target}`（{why}）")
    print(f"✓ 已改名 {len(todo)} 个文件。")

    if args.log:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        block = [f"\n### {stamp} 需求号补全（fix_reqid_filenames.py --apply）",
                 f"- 根目录：`{root}`",
                 f"- 改名 {len(todo)} 个；需人工 {len(manual)}；撞名 {len(collide)}", ""]
        with open(args.log, "a", encoding="utf-8") as f:
            f.write("\n".join(block + lines) + "\n")
        print(f"✓ 对照表已追加至 {args.log}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
