#!/usr/bin/env python3
# Word2Knowledge 文本清洗 - 纯本地正则降噪
# v2.0: 修复标题/列表/代码块被错误合并的问题

import sys
import re


def is_protected_line(line):
    """
    判断该行是否不应与其他行合并：
    - 标题行: # ## ### 等
    - 列表行: - * + 开头，或有序列表 1. 2. 等
    - 引用行: > 开头
    - 代码围栏: ``` 开头
    - 图片/链接占位符: ![[
    - 表格行: | 或 + 开头
    - 水平线: --- 或 *** 或 ===
    - YAML frontmatter: --- 开头
    - 空行
    """
    s = line.strip()
    if not s:
        return True
    if re.match(r'^#{1,6}\s', s):        # 标题
        return True
    if re.match(r'^[-*+]\s', s):         # 无序列表
        return True
    if re.match(r'^\d+\.\s', s):         # 有序列表
        return True
    if s.startswith('>'):                 # 引用
        return True
    if s.startswith('```'):              # 代码围栏
        return True
    if re.match(r'^\s*\!\[\[', s):       # 图片占位符
        return True
    if re.match(r'^[|+]', s):            # 表格
        return True
    if re.match(r'^[-*=]{3,}$', s):      # 水平线
        return True
    return False


def clean_text(lines):
    result = []
    buffer = ""
    in_code_block = False

    for raw_line in lines:
        line = raw_line.rstrip('\n').rstrip('\r')

        # ----------------------------------------
        # 清理 ![[...]] 的多余属性
        # ----------------------------------------
        if '![[' in line:
            line = re.sub(r'!\[\[([^\]]*)\]\]\{[^}]*\}', r'![[\1]]', line)

        stripped = line.strip()

        # ----------------------------------------
        # 代码块：进入/退出，内部直接透传不处理
        # ----------------------------------------
        if stripped.startswith('```'):
            if buffer:
                result.append(buffer)
                buffer = ""
            in_code_block = not in_code_block
            result.append(line)
            continue

        if in_code_block:
            result.append(line)
            continue

        # ----------------------------------------
        # 空行：刷新 buffer，最多保留一个空行
        # ----------------------------------------
        if not stripped:
            if buffer:
                result.append(buffer)
                buffer = ""
            if result and result[-1].strip() != "":
                result.append("")
            continue

        # ----------------------------------------
        # 受保护行：直接输出，不参与合并
        # ----------------------------------------
        if is_protected_line(stripped):
            if buffer:
                result.append(buffer)
                buffer = ""
            result.append(line)
            continue

        # ----------------------------------------
        # 普通段落行：尝试合并连续被折断的行
        # 判断依据：上一行末尾是否以句末标点结束
        # ----------------------------------------
        SENTENCE_END = re.compile(r'[。！？…\.;；!?]\s*$')

        if buffer:
            if SENTENCE_END.search(buffer):
                # 上一行是完整句子，直接换行输出
                result.append(buffer)
                buffer = stripped
            else:
                # 上一行未结束，合并（中文不加空格，英文加空格）
                last_char = buffer[-1] if buffer else ''
                first_char = stripped[0] if stripped else ''
                if re.match(r'[a-zA-Z0-9]', last_char) and re.match(r'[a-zA-Z0-9]', first_char):
                    buffer = buffer + ' ' + stripped
                else:
                    buffer = buffer + stripped
        else:
            buffer = stripped

    # 刷新最后的 buffer
    if buffer:
        result.append(buffer)

    # ----------------------------------------
    # 去除连续多余空行（最多保留一个）
    # ----------------------------------------
    final = []
    for line in result:
        if line.strip() == "" and final and final[-1].strip() == "":
            continue
        final.append(line)

    # 去除末尾空行
    while final and final[-1].strip() == "":
        final.pop()

    return final


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python3 clean_text.py <input.md> <output.md>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    final = clean_text(lines)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(final) + '\n')

    print(f"  ✅ 文本清洗完成 → {output_file}")
