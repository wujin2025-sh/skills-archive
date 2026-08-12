#!/usr/bin/env python3
"""
Word2Knowledge - Table Fixer v2.1
修复 Pandoc 输出的各类表格格式问题，使其在 Obsidian 中正确渲染。

修复项：
1. GFM 表格（+---+）→ 标准 Markdown（|---|）
2. Fixed-width 表格（--- --- ---）→ 标准 Markdown
3. 修复 broken pipe headers（混合 dash 的表头）
4. 修复分隔行列数与表头不匹配
5. 删除 GFM 合并单元格边框行（| +---+---+）
6. 清理交叉引用链接（[图 1](#_Ref...)）
7. 合并表格中多行续行（<br> 连接）
"""

import re
import sys


# ──────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────

def strip_line(line):
    return line.rstrip('\n').rstrip('\r')


def is_gfm_separator(s):
    """判断是否是 GFM 分隔行：+---+---+"""
    s = s.strip()
    return (s.startswith('+') and s.endswith('+')
            and '--' in s
            and all(c in '+-: ' for c in s)
            and s.count('+') >= 2)


def is_gfm_merged_subrow(s):
    """判断是否是 GFM 合并单元格子行：|    +---+---+"""
    s = s.strip()
    return (s.startswith('|') and s.endswith('+')
            and '--' in s and s.count('+') >= 2
            and s.index('+') > s.index('|'))


def count_cols_from_gfm_sep(sep):
    return sep.strip().count('+') - 1


def pipe_cells(s):
    """拆分 pipe 行为 cell 列表（不含空首尾）"""
    return [c.strip() for c in s.strip().strip('|').split('|')]


def make_separator(n):
    return '| ' + ' | '.join(['---'] * n) + ' |'


# ──────────────────────────────────────────
# Step 1: GFM (+---+) → 标准 Markdown
# ──────────────────────────────────────────

def convert_gfm_to_md(lines):
    """
    Pandoc GFM 格式：
      +----------+----------+
      | header1  | header2  |
      +==========+==========+
      | data1    | data2    |
      +----------+----------+

    → 标准 Markdown:
      | header1 | header2 |
      | --- | --- |
      | data1 | data2 |
    """
    result = []
    i = 0
    in_gfm_table = False
    first_sep_done = False

    while i < len(lines):
        line = strip_line(lines[i])
        s = line.strip()

        if is_gfm_separator(s):
            n_cols = count_cols_from_gfm_sep(s)
            in_gfm_table = True

            if not first_sep_done:
                # 第一个分隔行：后面紧跟 header，再跟 =====
                first_sep_done = True
                # 向后找 header 行
                i += 1
                if i < len(lines):
                    header_line = strip_line(lines[i])
                    result.append(header_line)
                    i += 1
                # 向后找 ===== 分隔行（跳过）
                if i < len(lines) and is_gfm_separator(strip_line(lines[i]).strip()):
                    sep = make_separator(n_cols)
                    result.append(sep)
                    i += 1
            else:
                # 后续分隔行：直接跳过
                i += 1
            continue

        if is_gfm_merged_subrow(s):
            i += 1
            continue

        result.append(line)
        i += 1

    return result


# ──────────────────────────────────────────
# Step 2: Fixed-width table → 标准 Markdown
# ──────────────────────────────────────────

def convert_fixed_width_tables(lines):
    """
    Fixed-width 表格（Pandoc simple table）：
      ------- ----- ------
      col1    col2  col3
      ------- ----- ------
      data1   data2 data3
      ------- ----- ------

    → 标准 Markdown
    """
    result = []
    i = 0

    def is_fw_sep(s):
        """判断是否是 fixed-width 分隔行（只含 - 和空格）"""
        s = s.strip()
        return bool(s) and re.match(r'^[-= ]+$', s) and '---' in s and '|' not in s

    while i < len(lines):
        line = strip_line(lines[i])
        s = line.strip()

        if is_fw_sep(s):
            # 收集整个表格块
            sep_pattern = s
            col_spans = [(m.start(), m.end()) for m in re.finditer(r'-+', sep_pattern)]
            n_cols = len(col_spans)

            def split_fw_row(row, spans):
                cells = []
                for start, end in spans:
                    cells.append(row[start:end].strip() if start < len(row) else '')
                return cells

            # 向后扫描直到下一个分隔行（表头）
            i += 1
            header_cells = []
            if i < len(lines):
                header_row = strip_line(lines[i])
                if not is_fw_sep(header_row.strip()):
                    header_cells = split_fw_row(header_row, col_spans)
                    i += 1

            # 跳过第二个分隔行
            if i < len(lines) and is_fw_sep(strip_line(lines[i]).strip()):
                i += 1

            # 收集数据行
            data_rows = []
            while i < len(lines):
                row = strip_line(lines[i])
                rs = row.strip()
                if is_fw_sep(rs):
                    i += 1
                    break
                if not rs:
                    break
                data_rows.append(split_fw_row(row, col_spans))
                i += 1

            if header_cells:
                result.append('| ' + ' | '.join(header_cells) + ' |')
                result.append(make_separator(n_cols))
                for dr in data_rows:
                    while len(dr) < n_cols:
                        dr.append('')
                    result.append('| ' + ' | '.join(dr[:n_cols]) + ' |')
            continue

        result.append(line)
        i += 1

    return result


# ──────────────────────────────────────────
# Step 3: 修复 broken pipe headers
# ──────────────────────────────────────────

def fix_broken_pipe_headers(lines):
    """
    修复表头中混入 dash 分隔的情况：
    | --------------- -------- **文件编号** | **文件名称** |
    → 只保留 ** 内容
    """
    result = []
    for line in lines:
        s = line.strip() if isinstance(line, str) else line.strip()
        if (s.startswith('|') and '**' in s
                and re.search(r'[-=]{3,}', s) and s.endswith('|')):
            parts = s.strip('|').split('|')
            clean_parts = []
            for p in parts:
                cleaned = re.sub(r'[-=]{2,}', '', p).strip()
                if cleaned:
                    clean_parts.append(cleaned)
            if clean_parts:
                result.append('| ' + ' | '.join(clean_parts) + ' |')
                result.append(make_separator(len(clean_parts)))
                continue
        result.append(line)
    return result


# ──────────────────────────────────────────
# Step 4: 修复分隔行列数与表头不匹配
# ──────────────────────────────────────────

def fix_separator_column_counts(lines):
    result = []
    for line in lines:
        s = line.strip() if isinstance(line, str) else line.strip()
        if s.startswith('|') and s.endswith('|') and '---' in s:
            cells = pipe_cells(s)
            if all(re.match(r'^:?-+:?$', c) for c in cells if c):
                # 这是分隔行，检查和上一行是否对齐
                if result:
                    prev = result[-1].strip() if isinstance(result[-1], str) else result[-1].strip()
                    if prev.startswith('|') and prev.endswith('|'):
                        prev_cells = pipe_cells(prev)
                        h_cols = len([c for c in prev_cells if c])
                        s_cols = len([c for c in cells if c])
                        if h_cols != s_cols and h_cols > 0:
                            result.append(make_separator(h_cols))
                            continue
        result.append(line)
    return result


# ──────────────────────────────────────────
# Step 5: 清理交叉引用链接
# ──────────────────────────────────────────

def fix_cross_refs(lines):
    result = []
    for line in lines:
        s = line.strip() if isinstance(line, str) else line
        s = re.sub(r'\[图 (\d+)\]\(#_Ref[^\)]*\)', r'图 \1', s)
        s = s.replace('和所示', '所示')
        result.append(s)
    return result


# ──────────────────────────────────────────
# Step 6: 合并表格续行
# ──────────────────────────────────────────

def merge_table_continuations(lines):
    """
    处理表格中只有末列有内容的续行，合并到上一行（用 <br> 连接）
    """
    result = []
    for line in lines:
        s = line.strip() if isinstance(line, str) else line.strip()
        if s.startswith('|') and s.endswith('|'):
            cells = pipe_cells(s)
            non_empty = [(idx, c) for idx, c in enumerate(cells) if c.strip()]
            if len(non_empty) == 1 and non_empty[0][0] == len(cells) - 1:
                content = non_empty[0][1].strip()
                # 往回找最近的 pipe 行
                merged = False
                for j in range(len(result) - 1, -1, -1):
                    prev = result[j].strip() if isinstance(result[j], str) else result[j].strip()
                    if prev.startswith('|') and prev.endswith('|') and '---' not in prev:
                        prev_cells = pipe_cells(prev)
                        if len(prev_cells) == len(cells):
                            prev_cells[-1] = prev_cells[-1].strip() + '<br>' + content
                            result[j] = '| ' + ' | '.join(prev_cells) + ' |'
                            merged = True
                            break
                        else:
                            break
                if not merged:
                    result.append(s)
                continue
        result.append(s)
    return result


# ──────────────────────────────────────────
# Main
# ──────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("用法: python3 fix_tables.py <file.md> [basename]")
        sys.exit(1)

    input_file = sys.argv[1]

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = [l.rstrip('\n').rstrip('\r') for l in f.readlines()]

    lines = convert_gfm_to_md(lines)
    lines = convert_fixed_width_tables(lines)
    lines = fix_broken_pipe_headers(lines)
    lines = fix_separator_column_counts(lines)
    lines = fix_cross_refs(lines)
    lines = merge_table_continuations(lines)

    with open(input_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"  ✅ 表格修复完成 → {input_file}")


if __name__ == '__main__':
    main()
