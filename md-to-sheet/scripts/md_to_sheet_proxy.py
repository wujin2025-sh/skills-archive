#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md-to-sheet 代理模式启动器。

用「代理模式 HTTP 客户端」替换 sync_utils.call_mcp（绕过损坏的 AILink 连接器
运行时 / mcporter），然后运行 md_to_sheet.py 主体。

用法：
  python3 md_to_sheet_proxy.py rzrq [--date 20260602] [--dry-run]
"""
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_COMMON_DIR = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", "common"))
for d in (_COMMON_DIR, _SCRIPT_DIR):
    if d not in sys.path:
        sys.path.insert(0, d)

# 1) 先补丁 sync_utils.call_mcp 为代理模式
import sync_utils  # noqa: E402
import mcp_http_proxy  # noqa: E402

sync_utils.call_mcp = mcp_http_proxy.call_mcp

# 2) 再跑 md_to_sheet 主体（其内部 from sync_utils import call_mcp 会拿到已补丁版本）
import runpy  # noqa: E402

argv = sys.argv[1:] or ["rzrq"]
os.environ.setdefault("MD_TO_SHEET_ARGS", " ".join(argv))
sys.argv = ["md_to_sheet.py"] + argv
runpy.run_path(
    os.path.join(_SCRIPT_DIR, "md_to_sheet.py"),
    run_name="__main__",
)