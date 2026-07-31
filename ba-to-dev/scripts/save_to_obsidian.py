#!/usr/bin/env python3
"""
将结构化需求文档内容自动保存为 Markdown 文件到 Obsidian 笔记目录。
用法: echo '<markdown_content>' | python3 save_to_obsidian.py <filename>

参数:
  filename - 文件名，格式为 YYYYMMDD-需求-名称.md
  stdin    - 通过 stdin 传入的 Markdown 完整内容
"""
import sys
import os
from datetime import datetime, timezone, timedelta

TARGET_DIR = "/Volumes/Macintosh HD_Data/obsidian/100_Projects/需求分析"

def main():
    if len(sys.argv) < 2:
        print("Usage: echo '<content>' | python3 save_to_obsidian.py <filename>", file=sys.stderr)
        sys.exit(1)

    filename = sys.argv[1]

    # 验证文件名格式
    if not filename.endswith(".md"):
        filename += ".md"

    # 从 stdin 读取内容
    content = sys.stdin.read()
    if not content:
        print("Error: no content provided via stdin", file=sys.stderr)
        sys.exit(1)

    # 构造完整路径
    filepath = os.path.join(TARGET_DIR, filename)

    # 确保目标目录存在
    os.makedirs(TARGET_DIR, exist_ok=True)

    # 写入文件
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"FILE_SAVED:{filepath}")

if __name__ == "__main__":
    main()
