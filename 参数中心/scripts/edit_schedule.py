#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
需求定位 — 大宽表需求定位工具（v2 稳定版）
==========================================
打开「交易结算核心系统需求集合」大宽表，在搜索框输入需求编号，
筛选结果，保持浏览器打开供人工查看。

用法:
    .venv/bin/python scripts/edit_schedule.py <需求编号>

示例:
    .venv/bin/python scripts/edit_schedule.py PG202204-0155
    .venv/bin/python scripts/edit_schedule.py R2604020071

依赖: playwright，虚拟环境 .venv/

性能边界:
    总耗时 ~20s，其中 ~16s 为 AG Grid 服务端渲染 2 万+ 行数据（不可控）。
    URL 预过滤参数测试无效，AG Grid 过滤引擎需数据模型加载完毕后才生效。
"""

import sys
import os
import re
import time
import argparse
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ============================================================
# 配置
# ============================================================
USERNAME = "125360"
PASSWORD = "wujin@1124"
LOGIN_URL = "https://fintech.gtht.com.cn/kjpt/user/login"

TABLE_URL = (
    "https://fintech.gtht.com.cn/kjpt/OnlineGrid?tableId=1589911659881828352&tableName=%E5%8F%82%E6%95%B0%E4%B8%AD%E5%BF%83%E6%8C%81%E7%BB%AD%E5%BB%BA%E8%AE%BE"
)

SESSION_FILE = "/Volumes/Macintosh HD_Data/WorkBuddy/需求管理/.fintech_session.json"


# ── JS 片段 ──
_JS_LOGIN = "() => !!document.querySelector('input[placeholder*=\"工号\"]')"
_JS_FILTER_BAR = (
    "() => {"
    "  const b = document.querySelector('.ag-status-bar');"
    "  return b && /过滤后数据总数/.test(b.innerText || '');"
    "}"
)
_JS_ROWS_VISIBLE = (
    "() => {"
    "  const vp = document.querySelector('.ag-body-viewport');"
    "  if (!vp) return false;"
    "  return vp.querySelectorAll('.ag-row').length > 0;"
    "}"
)


# ============================================================
# 登录（Session 复用）
# ============================================================
def ensure_login(context, page):
    """commit 模式快速检测登录态，有 session 则 ~0.6s 完成。"""
    print("[登录]", end=" ", flush=True)
    t0 = time.time()

    try:
        page.goto(TABLE_URL, wait_until="commit", timeout=10000)
        page.wait_for_timeout(500)  # DOM 登录表单已渲染，无需等页面完整加载
        if not page.evaluate(_JS_LOGIN):
            print(f"已有登录态（{time.time() - t0:.1f}s）")
            return
    except Exception:
        pass

    print("登录中...", end=" ", flush=True)
    page.goto(LOGIN_URL, wait_until="commit", timeout=30000)
    page.wait_for_selector('input[placeholder*="工号"]', timeout=15000)
    page.locator('input[placeholder*="工号"]').fill(USERNAME)
    page.locator('input[placeholder*="密码"]').fill(PASSWORD)
    page.locator('button:has-text("提 交")').click()
    page.wait_for_load_state("domcontentloaded", timeout=60000)
    try:
        page.wait_for_url("**/OnlineGrid**", timeout=15000)
    except PWTimeout:
        pass
    time.sleep(0.5)

    try:
        context.storage_state(path=SESSION_FILE)
        print(f"完成（{time.time() - t0:.1f}s）")
    except Exception as e:
        print(f"完成（session 保存失败: {e})")


# ============================================================
# 搜索 + 筛选
# ============================================================
def search_req(page, req_id):
    print(f"[搜索] 需求编号: {req_id}")
    t0 = time.time()

    # ── 等待 AG Grid 数据模型就绪 ──
    # 这是最大瓶颈：~14-16s，服务端渲染 2 万+ 行数据
    try:
        page.wait_for_function(_JS_ROWS_VISIBLE, polling=300, timeout=25000)
    except PWTimeout:
        print("[搜索] ⚠️ 数据行超时，继续...")

    print(f"[搜索] 表格就绪（{time.time() - t0:.1f}s）")

    # ── 一键展开所有分组行 ──
    page.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const btn of btns) {
            if (btn.textContent.trim() === '一键展开') {
                btn.click();
                return true;
            }
        }
        return false;
    }""")
    try:
        page.wait_for_function(
            "() => document.querySelectorAll('.ag-row.ag-row-level-2').length > 0",
            polling=300, timeout=6000,
        )
    except PWTimeout:
        pass

    # ── 填入搜索框 ──
    search_box = page.locator("#filter-text-box")
    search_box.wait_for(state="visible", timeout=10000)
    search_box.click()
    search_box.fill(req_id)  # fill() 瞬间完成，比 type(delay) 快 ~10x
    print("[搜索] 关键字已填入，等待过滤...")

    # ── 等待过滤完成 ──
    try:
        page.wait_for_function(_JS_FILTER_BAR, polling=200, timeout=15000)
    except PWTimeout:
        print("[搜索] ⚠️ 过滤超时")

    grid_info = page.evaluate("""() => {
        const rows = document.querySelectorAll('.ag-row');
        const bar = document.querySelector('.ag-status-bar');
        let n = 0;
        rows.forEach(r => { if (r.offsetParent !== null) n++; });
        return { visibleRows: n, statusText: bar ? bar.innerText : '' };
    }""")
    print(f"[搜索] 过滤完成 — 可见行: {grid_info['visibleRows']}, 状态: {grid_info['statusText'].strip()} ({time.time() - t0:.1f}s)")

    # ── 高亮需求编号单元格 ──
    page.evaluate("""({reqId}) => {
        const rows = document.querySelectorAll('.ag-row.ag-row-level-2');
        for (const row of rows) {
            const cells = row.querySelectorAll('.ag-cell');
            for (const cell of cells) {
                if (cell.textContent.trim() === reqId) {
                    cell.scrollIntoView({ block: 'center', behavior: 'instant' });
                    cell.style.outline = '3px solid #ff4d4f';
                    cell.style.outlineOffset = '-1px';
                    return true;
                }
            }
        }
        return false;
    }""", {"reqId": req_id})

    print("[定位] 需求编号单元格已高亮（红色边框）")


# ============================================================
# 主函数
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="需求定位工具")
    parser.add_argument("req_id", help="需求编号（如 PG202204-0155、R2604020071）")
    args = parser.parse_args()

    req_id = args.req_id.strip()

    if not re.match(r"^(R|PG)\d+", req_id, re.IGNORECASE):
        print(f"⚠️ 需求编号格式可能有误: {req_id}")

    print(f"\n{'='*50}")
    print(f"  需求定位")
    print(f"  编号: {req_id}")
    print(f"{'='*50}")
    print(f"  浏览器将导航到筛选结果页，保持开放。")
    print(f"{'='*50}\n")

    overall_t0 = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            storage_state=SESSION_FILE if os.path.exists(SESSION_FILE) else None,
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = context.new_page()

        try:
            ensure_login(context, page)
            search_req(page, req_id)

            try:
                context.storage_state(path=SESSION_FILE)
            except Exception:
                pass

            elapsed = time.time() - overall_t0
            print(f"\n{'='*50}")
            print(f"  定位完成（{elapsed:.1f}s）")
            print(f"  编号: {req_id}")
            print(f"  请手动查看，完成后关闭浏览器")
            print(f"{'='*50}")

            print("\n（浏览器保持打开，按 Ctrl+C 或手动关闭窗口）")
            try:
                while True:
                    time.sleep(10)
                    try:
                        page.title()
                    except Exception:
                        print("\n浏览器已关闭，脚本退出。")
                        break
            except KeyboardInterrupt:
                print("\n收到中断，关闭浏览器...")

        except Exception as e:
            print(f"\n❌ 失败: {e}")
            import traceback
            traceback.print_exc()
            print("\n（浏览器保持打开，按 Ctrl+C 或手动关闭窗口）")
            try:
                while True:
                    time.sleep(10)
                    try:
                        page.title()
                    except Exception:
                        break
            except KeyboardInterrupt:
                pass
        finally:
            try:
                context.storage_state(path=SESSION_FILE)
            except Exception:
                pass
            browser.close()


if __name__ == "__main__":
    main()
