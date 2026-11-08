#!/bin/bash
# 极速接口毫秒级查询命令行工具 (统一路由至 SQLite 结构化接口引擎)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ $# -eq 0 ]; then
echo "=================================================="
echo "💡 极速接口知识库查询 (支持实时接口 / 文件接口)"
echo "=================================================="
echo "用法: ./query_interface.sh <功能号/文件编号/表名/关键字...> [支持多关键字]"
echo ""
echo "示例:"
echo "  ./query_interface.sh 7390704 7490704"
echo "  ./query_interface.sh z59 s03 s04"
echo "  ./query_interface.sh 420662"
echo "  ./query_interface.sh credittargetstk"
echo ""
echo "提示: 建议改用 interface_query.py (支持字段明细 + 自动升级服务治理平台)"
echo "=================================================="
exit 1
fi

PY=/Users/wujin/.workbuddy/binaries/python/envs/default/bin/python
[ -x "$PY" ] || PY=python3
"$PY" "$DIR/query_fast.py" "$@"
