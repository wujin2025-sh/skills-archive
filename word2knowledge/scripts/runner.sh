#!/bin/bash
# Word2Knowledge 核心流水线 - 图文资产分离架构
# v2.0: 集成表格修复、临时文件清理、完整4步流程

# ==========================================
# 环境变量配置
# ==========================================
OBSIDIAN_INBOX="${OBSIDIAN_INBOX:-/Users/wujin/0000WorkFiles/myobsidian/Obsidian-Notes/000_Inbox}"

# 检测项目根目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -d "$SCRIPT_DIR/tools" ]; then
    PROJECT_ROOT="$SCRIPT_DIR"
else
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
fi

TMP_DIR="$PROJECT_ROOT/.tmp"
TOOLS_DIR="$PROJECT_ROOT/tools"
mkdir -p "$TMP_DIR"

# ==========================================
# 参数校验
# ==========================================
if [ "$#" -eq 0 ]; then
    echo "❌ 错误: 请传入至少一个 .docx 文件路径。"
    echo "用法: bash runner.sh <file1.docx> [file2.docx ...]"
    exit 1
fi

# 校验 pandoc
if ! command -v pandoc &>/dev/null; then
    echo "❌ 错误: 未找到 pandoc，请先安装: brew install pandoc"
    exit 1
fi

echo "🚀 启动 Word2Knowledge 处理引擎..."
echo "📂 输出目录: $OBSIDIAN_INBOX"
echo ""

# ==========================================
# 主循环
# ==========================================
for INPUT_FILE in "$@"; do
    if [ ! -f "$INPUT_FILE" ]; then
        echo "⚠️  警告: 找不到文件 '$INPUT_FILE'，跳过。"
        continue
    fi

    BASENAME=$(basename "$INPUT_FILE" .docx)
    RAW_MD="$TMP_DIR/temp_${BASENAME}_raw.md"
    CLEAN_MD="$TMP_DIR/temp_${BASENAME}_cleaned.md"
    ASSETS_DIR="$OBSIDIAN_INBOX/assets/${BASENAME}"
    OUTPUT_MD="$OBSIDIAN_INBOX/${BASENAME}.md"

    mkdir -p "$ASSETS_DIR"

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📄 处理文件: $BASENAME.docx"
    echo ""

    # ------------------------------------------
    # Step 1/4: Pandoc 解析，提取内容和图片
    # ------------------------------------------
    echo "  ▶ [1/4] Pandoc 解析 & 图片提取..."
    pandoc "$INPUT_FILE" -f docx -t markdown \
        --extract-media="$TMP_DIR" \
        --wrap=none \
        -o "$RAW_MD" 2>/dev/null

    if [ $? -ne 0 ]; then
        echo "  ❌ Pandoc 解析失败，跳过: $INPUT_FILE"
        continue
    fi

    # ------------------------------------------
    # Step 2/4: 图片迁移 & Obsidian 双链重构
    # ------------------------------------------
    echo "  ▶ [2/4] 图片迁移 & 双链重构..."
    if [ -d "$TMP_DIR/media" ]; then
        IMG_COUNT=0
        for IMG in "$TMP_DIR/media/"*; do
            [ -f "$IMG" ] || continue
            IMG_NAME=$(basename "$IMG")
            NEW_IMG_NAME="${BASENAME}_${IMG_NAME}"
            mv "$IMG" "$ASSETS_DIR/$NEW_IMG_NAME"
            IMG_COUNT=$((IMG_COUNT + 1))
        done
        rm -rf "$TMP_DIR/media"
        echo "     迁移图片: ${IMG_COUNT} 张 → $ASSETS_DIR"
    else
        echo "     无嵌入图片"
    fi

    # 重写图片链接：添加 BASENAME_ 前缀，去除 {width=...} 属性
    export BASENAME
    perl -i -pe 's/!\[\[([^\]]+)\/([^\]"]+)\]\]\{[^}]*\}/![[${1}\/${ENV{BASENAME}}_$2]]/g' "$RAW_MD"

    # ------------------------------------------
    # Step 3/4: 文本清洗（修复换行/空行/排版噪声）
    # ------------------------------------------
    echo "  ▶ [3/4] 文本清洗..."
    python3 "$TOOLS_DIR/clean_text.py" "$RAW_MD" "$CLEAN_MD"

    # ------------------------------------------
    # Step 4/4: 表格修复（GFM → 标准 Markdown）
    # ------------------------------------------
    echo "  ▶ [4/4] 表格格式修复..."
    python3 "$TOOLS_DIR/fix_tables.py" "$CLEAN_MD" "$BASENAME"

    # ------------------------------------------
    # 归档输出
    # ------------------------------------------
    cp "$CLEAN_MD" "$OUTPUT_MD"

    # 清理当前文档的临时文件
    rm -f "$RAW_MD" "$CLEAN_MD"

    echo ""
    echo "  ✅ 完成!"
    echo "     📄 Markdown → $OUTPUT_MD"
    echo "     📸 图片     → $ASSETS_DIR"
done

# 清理空的 .tmp 目录
rmdir "$TMP_DIR" 2>/dev/null

echo ""
echo "🎉 全部完成。所有产物已归档至 $OBSIDIAN_INBOX"
