#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selftest.py — 跨平台冒烟测试（安装后 / 迁移后运行）

检查项：
  1. Python 版本（≥3.9）
  2. 配置：config 文件位置 / 状态目录 / vault 根 / 模板目录
  3. 导入：session / platform_api / 各入口脚本
  4. 派生：api_base / ws_base / origin 推导正确性
  5. 凭据：平台 / pingcode 凭据是否已配置（不打印明文）
  6. 依赖：requests / websocket-client / playwright
  7. OCR 后端探测：swift / pytesseract / paddleocr（仅探测可用性，不实际跑）

用法：
  python3 selftest.py [--strict]     # --strict: 任一关键项失败即 exit 1
"""
import importlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config

RESULTS = []


def check(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, bool(ok), detail))
    mark = "✅" if ok else "⚠️"
    print(f"{mark} {name}" + (f"  — {detail}" if detail else ""))


def _import(name: str):
    try:
        importlib.import_module(name)
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _has_cmd(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def main() -> int:
    print("=== gtht-demand-fetch selftest ===")
    v = sys.version_info
    check("Python ≥3.9", v >= (3, 9), f"{v.major}.{v.minor}.{v.micro}")

    # 配置 / 状态
    cfile = config.get_config_file()
    check("config 文件", cfile.exists(), str(cfile))
    state = config.ensure_state_dir()
    check("state 目录", state.is_dir(), str(state))
    vault = config.get_vault_root()
    check("vault 根", vault.is_dir(), str(vault))
    tpl = config.get_template_dir()
    check("模板目录", tpl.is_dir(), str(tpl))
    attach = config.get_attach_dir()
    check("附件目录", attach.is_dir(), str(attach))

    # 派生
    api_base = config.get_api_base()
    ws_base = config.get_ws_base()
    origin = config.get_origin()
    check("api_base 推导", api_base.startswith("http"), api_base)
    check("ws_base 推导", ws_base.startswith("wss://"), ws_base)
    check("origin 推导", origin.startswith("https://"), origin)

    # 凭据（只报有无，不打印明文）
    cfg = config.load_config()
    has_plat = bool(cfg.get("username") and cfg.get("password"))
    has_pc = bool((cfg.get("pingcode") or {}).get("username"))
    check("平台凭据", has_plat, "已配置" if has_plat else "未配置 → 无法登录")
    check("pingcode 凭据", has_pc, "已配置" if has_pc else "未配置 → wiki 抓取需人工登录")

    # 表 ID
    table_id, sheet_id = config.get_table_sheet()
    check("table/sheet ID", bool(table_id and sheet_id), f"{table_id}/{sheet_id}")

    # 依赖
    for mod in ["requests", "websocket", "PIL", "playwright"]:
        ok, d = _import(mod)
        check(f"依赖 {mod}", ok, d)

    # 模块导入
    for mod in ["session", "platform_api", "fetch_demand", "fetch_pingcode",
                "schedule_fast", "submit_review", "split_story", "batch_sync_status"]:
        ok, d = _import(mod)
        check(f"导入 {mod}", ok, d)

    # OCR 后端探测
    order = config.get_ocr_backend_order()
    check("OCR 后端顺序", bool(order), ",".join(order))
    swift_ok = _has_cmd("swift") and (Path(__file__).parent / "ocr.swift").exists()
    check("OCR swift", swift_ok, "macOS Vision 最快路径" if swift_ok else "不可用")
    try:
        import pytesseract  # noqa
        tess_cmd = pytesseract.get_tesseract_version()  # 触发 which 校验
        check("OCR pytesseract", True, f"tesseract {tess_cmd}")
    except Exception as e:
        check("OCR pytesseract", False, f"{type(e).__name__}: {e}")
    try:
        import paddleocr  # noqa
        check("OCR paddleocr", True, "已安装")
    except Exception as e:
        check("OCR paddleocr", False, f"{type(e).__name__}: 未安装（可选）")

    # 汇总
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n=== 汇总: {len(RESULTS)-len(failed)}/{len(RESULTS)} 通过 ===")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  ⚠️ {name}: {detail}")
    if failed:
        # 关键项：config/state/依赖/模块导入失败 → 视为失败
        critical = {"config 文件", "state 目录", "导入 session", "依赖 requests",
                    "依赖 websocket", "依赖 playwright"}
        crit_fail = [r for r in failed if r[0] in critical]
        print(f"\n关键失败 {len(crit_fail)} 项，非关键失败 {len(failed)-len(crit_fail)} 项")
        return 1 if (crit_fail or "--strict" in sys.argv) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
