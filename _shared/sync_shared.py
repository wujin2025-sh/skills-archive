#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ba-to-dev × biz-logic-query 共性规范同步器。

单一事实源：_shared/SHARED.md（带 <!-- SHARED:<id> START/END --> 标记）
目标文档：两份 SKILL.md（内嵌同样的块，保证技能加载即生效，无外链依赖）

用法：
  python3 sync_shared.py list                列出共性块与目标文档
  python3 sync_shared.py check              校验漂移（退出码 1 = 有漂移）
  python3 sync_shared.py apply              推送全部共性块到两份 SKILL.md（自动备份）
  python3 sync_shared.py apply --init       只补齐缺失的块，不覆盖已有内容
  python3 sync_shared.py diff              显示漂移明细
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

REG_PATH = Path(__file__).with_name("shared_registry.json")


def load_reg() -> dict:
    if not REG_PATH.exists():
        sys.exit(f"[FATAL] 缺少注册表：{REG_PATH}")
    return json.loads(REG_PATH.read_text(encoding="utf-8"))


def marker(bid: str, kind: str) -> str:
    return f"<!-- SHARED:{bid} {kind} -->"


def block_re(bid: str) -> re.Pattern:
    return re.compile(
        r"(" + re.escape(marker(bid, "START")) + r")(.*?)(" + re.escape(marker(bid, "END")) + r")",
        re.S,
    )


def extract(text: str, bid: str) -> str | None:
    m = block_re(bid).search(text)
    return m.group(2).strip("\n") if m else None


def norm(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip("\n").split("\n")).strip()


def digest(text: str) -> str:
    return hashlib.sha256(norm(text).encode("utf-8")).hexdigest()[:10]


def source_blocks(reg: dict) -> dict[str, str]:
    src = Path(reg["source"])
    if not src.exists():
        sys.exit(f"[FATAL] 缺少单一事实源：{src}")
    text = src.read_text(encoding="utf-8")
    out = {}
    for bid in reg["blocks"]:
        body = extract(text, bid)
        if body is None:
            sys.exit(f"[FATAL] SHARED.md 缺少块 {bid} 的 START/END 标记")
        out[bid] = body
    return out


def render_blocks(blocks: dict[str, str], order: list[str]) -> str:
    parts = []
    for bid in order:
        parts.append(f"{marker(bid, 'START')}\n{blocks[bid]}\n{marker(bid, 'END')}")
    return "\n\n".join(parts)


def build_section(reg: dict, blocks: dict[str, str]) -> str:
    return (
        "\n\n---\n\n"
        + reg["section_title"]
        + "\n\n"
        + reg["section_intro"]
        + "\n\n"
        + render_blocks(blocks, reg["blocks"])
        + "\n"
    )


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".sync_tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def do_check(reg: dict, verbose: bool = False) -> tuple[bool, list[str]]:
    blocks = source_blocks(reg)
    problems: list[str] = []
    ok_lines: list[str] = []

    for t in reg["targets"]:
        p = Path(t)
        label = p.parent.name
        if not p.exists():
            problems.append(f"{label}: 目标文档不存在 {p}")
            continue
        text = p.read_text(encoding="utf-8")

        # 1) 块存在性与一致性
        for bid in reg["blocks"]:
            body = extract(text, bid)
            if body is None:
                problems.append(f"{label}: 缺少共性块 `{bid}`（执行 apply --init 补齐）")
            elif digest(body) != digest(blocks[bid]):
                problems.append(
                    f"{label}: 共性块 `{bid}` 与单一事实源不一致 "
                    f"(doc={digest(body)} / src={digest(blocks[bid])})"
                )
            elif verbose:
                ok_lines.append(f"  {label} | {bid:22s} ✅ {digest(body)}")

        # 2) 代码围栏配对
        fences = sum(1 for line in text.split("\n") if line.strip().startswith("```"))
        if fences % 2:
            problems.append(f"{label}: 代码围栏奇数 {fences}，存在未闭合代码块")

        # 3) 共享常量必须出现
        for key, val in reg["constants"].items():
            if val not in text:
                problems.append(f"{label}: 缺少共享常量 `{key}` = {val}")

        # 4) 弱同步指针
        for ptr in reg["pointers"].get(label, []):
            if ptr not in text:
                problems.append(f"{label}: 缺少弱同步指针 `{ptr}`")

    # 5) 镜像副本（.chat/skills 下的独立 SKILL.md）必须与权威版逐字一致
    for m in reg.get("mirrors", []):
        src, dst = Path(m["source"]), Path(m["copy"])
        if src.exists() and dst.exists():
            if src.read_text(encoding="utf-8") != dst.read_text(encoding="utf-8"):
                problems.append(
                    f"镜像副本 {dst} 与权威版不一致（执行 apply 自动同步；"
                    f"该目录非软链接，scripts/ 为硬链接无需处理）"
                )
            elif verbose:
                ok_lines.append(f"  mirror | {dst.parent.name:22s} ✅ 与权威版一致")

    if verbose and ok_lines:
        print("\n".join(ok_lines))
    return (not problems), problems


def do_apply(reg: dict, init: bool = False, backup: bool = True) -> None:
    blocks = source_blocks(reg)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bdir = Path(reg["backup_dir"])
    if backup:
        bdir.mkdir(parents=True, exist_ok=True)

    for t in reg["targets"]:
        p = Path(t)
        label = p.parent.name
        if not p.exists():
            sys.exit(f"[FATAL] 目标文档不存在：{p}")
        text = p.read_text(encoding="utf-8")
        before = text

        if reg["section_title"] not in text:
            text = text.rstrip("\n") + build_section(reg, blocks)
            action = "新建共性基线章节（6 块）"
        else:
            changed = 0
            for bid in reg["blocks"]:
                if block_re(bid).search(text):
                    if init:
                        continue
                    text = block_re(bid).sub(
                        lambda m, b=blocks[bid]: m.group(1) + "\n" + b + "\n" + m.group(3),
                        text,
                        count=1,
                    )
                    changed += 1
                else:
                    # 缺失块插到该章节内最后一个 END 之后，避免落到章节外
                    sec_start = text.index(reg["section_title"])
                    ends = [m.end() for m in re.finditer(r"<!-- SHARED:\S+ END -->", text)
                            if m.start() > sec_start]
                    new_block = f"\n\n{marker(bid, 'START')}\n{blocks[bid]}\n{marker(bid, 'END')}"
                    if ends:
                        pos = max(ends)
                        text = text[:pos] + new_block + text[pos:]
                    else:
                        anchor = reg["section_intro"]
                        pos = text.index(anchor) + len(anchor)
                        text = text[:pos] + new_block + text[pos:]
                    changed += 1
            action = f"更新 {changed} 个共性块" + ("（--init 跳过已存在块）" if init else "")

        if text == before:
            print(f"  {label:20s} | 无变化")
            continue

        if backup:
            bak = bdir / f"{label}.SKILL.bak.{stamp}.md"
            bak.write_text(before, encoding="utf-8")
        atomic_write(p, text)
        print(f"  {label:20s} | {action} | +{len(text) - len(before)} 字符"
              + (f" | 备份 {bak.name}" if backup else ""))


def do_mirrors(reg: dict, backup: bool = True) -> None:
    """把权威版 SKILL.md 镜像到 .chat/skills 下的独立副本（非软链接目录）。"""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bdir = Path(reg["backup_dir"])
    for m in reg.get("mirrors", []):
        src, dst = Path(m["source"]), Path(m["copy"])
        if not src.exists() or not dst.exists():
            continue
        if dst.is_symlink():
            continue
        s = src.read_text(encoding="utf-8")
        d = dst.read_text(encoding="utf-8")
        if s == d:
            print(f"  镜像 {dst.parent.name:20s} | 已一致，无需改动")
            continue
        if backup:
            bdir.mkdir(parents=True, exist_ok=True)
            bak = bdir / f"mirror.{dst.parent.name}.SKILL.bak.{stamp}.md"
            bak.write_text(d, encoding="utf-8")
        atomic_write(dst, s)
        print(f"  镜像 {dst.parent.name:20s} | 已从权威版同步 "
              f"({len(d)} → {len(s)} 字符)" + (f" | 备份 {bak.name}" if backup else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description="两技能共性规范同步器")
    ap.add_argument("command", choices=["list", "check", "apply", "diff"])
    ap.add_argument("--init", action="store_true", help="apply 时只补齐缺失块")
    ap.add_argument("--no-backup", action="store_true", help="apply 时不备份")
    ap.add_argument("--verbose", "-v", action="store_true", help="check 显示逐块哈希")
    args = ap.parse_args()
    reg = load_reg()

    if args.command == "list":
        print(f"单一事实源: {reg['source']}")
        print(f"目标文档  : {len(reg['targets'])} 份")
        for t in reg["targets"]:
            print(f"  - {t}")
        print(f"共性块    : {len(reg['blocks'])} 个")
        for bid in reg["blocks"]:
            print(f"  - {bid}")
        print(f"共享常量  : {len(reg['constants'])} 项 | 弱同步指针: "
              f"{sum(len(v) for v in reg['pointers'].values())} 项")
        print(f"镜像副本  : {len(reg.get('mirrors', []))} 份")
        for m in reg.get("mirrors", []):
            print(f"  - {m['copy']}")
        return 0

    ok, problems = do_check(reg, verbose=args.verbose)
    if args.command == "apply":
        do_apply(reg, init=args.init, backup=not args.no_backup)
        do_mirrors(reg, backup=not args.no_backup)
        print("\n--- apply 后复检 ---")
        ok, problems = do_check(reg)
    elif args.command == "diff":
        print("\n".join(problems) if problems else "✅ 无漂移")
        return 0 if ok else 1

    if ok:
        print("✅ 共性同步校验通过：两份 SKILL.md 的 6 个共性块与单一事实源完全一致，"
              "共享常量/指针齐全，代码围栏配对正常")
        return 0
    print(f"❌ 检出 {len(problems)} 处漂移：")
    for i, p in enumerate(problems, 1):
        print(f"  {i:2d}. {p}")
    print("\n修复：改 SHARED.md → python3 sync_shared.py apply → python3 sync_shared.py check")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
