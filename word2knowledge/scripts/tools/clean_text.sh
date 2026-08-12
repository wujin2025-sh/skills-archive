#!/bin/bash
# Word2Knowledge 文本清洗 - 纯本地 Python 正则降噪
# 不再依赖外部 API，由 Codex 代理直接处理文本
#
# 用法: bash clean_text.sh <input.md> <output.md>

INPUT_FILE=$1
OUTPUT_FILE=$2

if [ ! -f "$INPUT_FILE" ]; then
    echo "❌ 找不到输入文件: $INPUT_FILE"
    exit 1
fi

python3 /Users/wujin/.codex/skills/word2knowledge/scripts/tools/clean_text.py "$INPUT_FILE" "$OUTPUT_FILE"
