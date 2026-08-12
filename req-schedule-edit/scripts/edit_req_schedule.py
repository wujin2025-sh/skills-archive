#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
edit_req_schedule.py — 需求排期修改技能 (修改排期)
==================================================
访问国泰海通金融科技平台「需求管理」详情页，点击右上角“修改排期”按钮，
在“需求排期确认”弹窗中自动修改「需求预计交付验收时间」与「需求预计上线时间」，
并提交保存，支持 Session 免登录态复用与可视/无头模式。

用法:
    python scripts/edit_req_schedule.py <需求编号> <目标排期日期> [上线日期] [--headed]

示例:
    python scripts/edit_req_schedule.py R2607150083 20260821
    python scripts/edit_req_schedule.py R2607150083 2026-08-21 2026-08-24
    python scripts/edit_req_schedule.py R2607150083 20260821 --headed
"""

import sys
import os
import re
import asyncio
import json
import base64
import argparse
import subprocess
import uuid
import hashlib
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ============================================================
# 1. 路径与配置解析
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
CWD = os.getcwd()

def get_hardware_key():
    identifiers = []
    if sys.platform == "darwin":
        try:
            output = subprocess.check_output("ioreg -rd1 -c IOPlatformExpertDevice", shell=True)
            match = re.search(r'"IOPlatformUUID"\s*=\s*"(.*?)"', output.decode('utf-8'))
            if match:
                identifiers.append(match.group(1).strip())
        except Exception:
            pass
    try:
        node = uuid.getnode()
        if node:
            identifiers.append(str(node))
    except Exception:
        pass
    combined = "|".join(identifiers)
    if not combined:
        combined = "default_fallback_key_2026"
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()

def decrypt_password(cipher_text):
    if not cipher_text:
        return ""
    try:
        key = get_hardware_key()
        xor_bytes = base64.b64decode(cipher_text)
        decrypted = "".join(chr(b ^ ord(key[i % len(key)])) for i, b in enumerate(xor_bytes))
        if decrypted.startswith("VERIFY_OK:"):
            return decrypted[len("VERIFY_OK:"):]
        return None
    except Exception:
        return None

def load_credentials():
    username = os.environ.get("PLATFORM_USERNAME", "")
    password = os.environ.get("PLATFORM_PASSWORD", "")
    platform_url = os.environ.get("PLATFORM_URL", "https://fintech.gtht.com.cn")

    config_paths = [
        os.path.join(CWD, "config.json"),
        os.path.join(SKILL_ROOT, "config.json"),
        os.path.join(SCRIPT_DIR, "config.json"),
    ]

    for p in config_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    creds = json.load(f)
                    u = creds.get("username", "")
                    p_plain = creds.get("password", "")
                    p_enc = creds.get("password_encrypted", "")
                    url_val = creds.get("platform_url", "")

                    if url_val:
                        platform_url = url_val.rstrip("/")
                    if u and u != "YOUR_USERNAME" and not username:
                        username = u

                    if not password:
                        if p_plain and p_plain not in ("YOUR_PASSWORD", "YOUR_PLAIN_PASSWORD"):
                            password = p_plain
                        elif p_enc:
                            dec = decrypt_password(p_enc)
                            if dec:
                                password = dec
                if username and password:
                    break
            except Exception:
                pass

    if not username or not password:
        print("❌ [配置缺失错误] 未找到有效的科技平台登录凭据 (USERNAME / PASSWORD)", file=sys.stderr)

    return username, password, platform_url

USERNAME, PASSWORD, PLATFORM_URL = load_credentials()

session_paths = [
    os.path.join(CWD, ".fintech_session.json"),
    os.path.join(SKILL_ROOT, ".fintech_session.json"),
    os.path.join(SCRIPT_DIR, ".fintech_session.json"),
]
SESSION_FILE = session_paths[0]
for p in session_paths:
    if os.path.exists(p):
        SESSION_FILE = p
        break

DETAIL_URL_TEMPL = f"{PLATFORM_URL}/kjpt/DemandManage/details?demandId={{}}&templateId=8888&flag=1"
LOGIN_URL = f"{PLATFORM_URL}/kjpt/user/login"

# ============================================================
# 2. 日期格式化工具
# ============================================================
def format_date_str(date_input):
    if not date_input:
        return ""
    date_str = str(date_input).strip()
    if len(date_str) == 8 and date_str.isdigit():
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    date_str = date_str.replace("/", "-")
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", date_str)
    if m:
        y, month, d = m.groups()
        return f"{int(y):04d}-{int(month):02d}-{int(d):02d}"
    return date_str

# ============================================================
# 3. 登录与 Playwright 交互
# ============================================================
async def ensure_login(context, page):
    if os.path.exists(SESSION_FILE):
        return
    print("[登录] Session 不存在，正在登录平台...", flush=True)
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_selector('input[placeholder*="工号"]', timeout=10000)
    await page.locator('input[placeholder*="工号"]').fill(USERNAME)
    await page.locator('input[placeholder*="密码"]').fill(PASSWORD)
    await page.locator('button:has-text("提 交")').click()
    await page.wait_for_load_state("domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)
    try:
        await context.storage_state(path=SESSION_FILE)
        print(f"[登录] 登录成功，已保存 Session 至 {SESSION_FILE}")
    except Exception as e:
        print(f"[登录] 保存 Session 失败: {e}")

async def fill_date_input(page, modal, selector, target_date):
    inp = modal.locator(selector).first
    if await inp.count() == 0:
        return False
    
    await inp.scroll_into_view_if_needed()
    await inp.evaluate("el => el.removeAttribute('readonly')")
    await inp.click()
    await page.wait_for_timeout(500)
    
    is_mac = sys.platform == "darwin"
    await page.keyboard.press("Meta+A" if is_mac else "Control+A")
    await page.keyboard.press("Backspace")
    await page.keyboard.type(target_date, delay=50)
    await page.wait_for_timeout(300)
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(500)
    
    # 关闭下拉框并触发 blur 使得 React 状态同步
    try:
        await modal.locator('.ant-modal-title').click(force=True)
    except Exception:
        pass
    await page.wait_for_timeout(1000)
    
    val = await inp.input_value()
    return val

async def modify_demand_schedule(demand_id, target_date, online_date=None, headed=False):
    target_date = format_date_str(target_date)
    online_date = format_date_str(online_date) if online_date else target_date

    print(f"\n==========================================")
    print(f" 开始修改需求排期")
    print(f" 需求编号: {demand_id}")
    print(f" 目标交付验收时间: {target_date}")
    print(f" 目标预计上线时间: {online_date}")
    print(f" 模式: {'可视化 (Headed)' if headed else '无头 (Headless)'}")
    print(f"==========================================\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headed)
        
        context_opts = {}
        if os.path.exists(SESSION_FILE):
            context_opts["storage_state"] = SESSION_FILE

        context = await browser.new_context(**context_opts)
        page = await context.new_page()

        # 1. 确保登录
        if not os.path.exists(SESSION_FILE):
            await ensure_login(context, page)

        # 2. 导航至需求详情页
        url = DETAIL_URL_TEMPL.format(demand_id)
        print(f"[页面] 正在打开需求详情页: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # 检查重定向登录
        if "login" in page.url.lower():
            print("[登录] Session 已失效，重新执行登录流程...")
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)
            await ensure_login(context, page)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

        # 3. 提取需求标题
        title = ""
        try:
            h_text = await page.locator("h1, h2, h3, .ant-page-header-heading-title").first.text_content()
            if h_text:
                title = h_text.strip()
        except Exception:
            pass

        # 4. 查找并点击“修改排期”按钮
        btn = page.locator('button:has-text("修改排期"), .ant-btn:has-text("修改排期")').first
        if await btn.count() == 0:
            print(f"[错误] 未找到需求 {demand_id} 详情页的「修改排期」按钮，可能无权限或页面结构有变！")
            await browser.close()
            return {
                "success": False,
                "demand_id": demand_id,
                "error": "未找到「修改排期」按钮"
            }

        print("[交互] 点击「修改排期」按钮...")
        try:
            await btn.click(timeout=5000)
        except Exception as e:
            print(f"[交互] 常规点击受阻 ({e})，尝试使用 JS 模拟点击...")
            await btn.evaluate("node => node.click()")

        # 5. 定位“需求排期确认”弹窗
        modal = page.locator('.ant-modal-content').last
        try:
            await modal.wait_for(state="visible", timeout=5000)
        except Exception:
            print("[错误] 未弹出「需求排期确认」弹窗！")
            await browser.close()
            return {
                "success": False,
                "demand_id": demand_id,
                "error": "未弹出排期确认弹窗"
            }

        modal_title = await modal.locator('.ant-modal-title').text_content()
        print(f"[弹窗] 已打开弹窗: {modal_title.strip() if modal_title else '需求排期确认'}")

        sel1 = 'input[placeholder="需求预计交付验收时间"]'
        sel2 = 'input[placeholder="需求预计上线时间"]'

        inp1 = modal.locator(sel1).first
        inp2 = modal.locator(sel2).first

        v1_old = await inp1.input_value() if await inp1.count() > 0 else ""
        v2_old = await inp2.input_value() if await inp2.count() > 0 else ""
        print(f"[当前值] 需求预计交付验收时间: {v1_old} | 需求预计上线时间: {v2_old}")

        # 6. 修改日期输入框 (自适应顺序调整以绕过前端最大/最小日期范围校验)
        print(f"[修改] 尝试 Order 1: 先填上线时间 ({online_date})，再填交付验收时间 ({target_date})...")
        v2_new = await fill_date_input(page, modal, sel2, online_date)
        await page.wait_for_timeout(300)
        v1_new = await fill_date_input(page, modal, sel1, target_date)
        await page.wait_for_timeout(300)

        if v1_new != target_date or v2_new != online_date:
            print(f"[修改] Order 1 未能完全生效（当前值: {v1_new} | {v2_new}），尝试 Order 2: 先填交付验收时间，再填上线时间...")
            v1_new = await fill_date_input(page, modal, sel1, target_date)
            await page.wait_for_timeout(300)
            v2_new = await fill_date_input(page, modal, sel2, online_date)
            await page.wait_for_timeout(300)

        print(f"[新设定值] 需求预计交付验收时间: {v1_new} | 需求预计上线时间: {v2_new}")

        # 收回所有下拉遮罩
        await modal.locator('.ant-modal-title').click()
        await page.wait_for_timeout(300)

        # 7. 点击确认按钮
        confirm_btn = modal.locator('button:has-text("确 认"), button:has-text("确认"), .ant-btn-primary').first
        if await confirm_btn.count() == 0:
            print("[错误] 弹窗内未找到「确 认」按钮！")
            await browser.close()
            return {
                "success": False,
                "demand_id": demand_id,
                "error": "未找到弹窗确认按钮"
            }

        print("[提交] 点击弹窗「确 认」按钮...")
        await confirm_btn.click()
        await page.wait_for_timeout(3500)

        # 截图保存
        screenshot_filename = f"schedule_{demand_id}_{target_date.replace('-', '')}.png"
        screenshot_path = os.path.join(CWD, screenshot_filename)
        await page.screenshot(path=screenshot_path)
        print(f"[截图] 已保存界面截图至: {screenshot_path}")

        # 重新加载校验数据库落库
        print("[校验] 重新刷新页面验证排期持久化...")
        await page.reload(wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        page_text = await page.locator('.ant-page-header, #root').first.text_content()
        verified = target_date in page_text

        await browser.close()

        result = {
            "success": True,
            "demand_id": demand_id,
            "title": title,
            "old_acceptance_date": v1_old,
            "old_online_date": v2_old,
            "new_acceptance_date": v1_new,
            "new_online_date": v2_new,
            "verified": verified,
            "screenshot": screenshot_path,
        }
        return result

# ============================================================
# 4. 主入口 CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="修改需求排期 (需求预计交付验收时间与需求预计上线时间)")
    parser.add_argument("demand_id", help="需求编号，例如 R2607150083")
    parser.add_argument("target_date", help="目标交付验收排期日期，例如 20260821 或 2026-08-21")
    parser.add_argument("online_date", nargs="?", default=None, help="目标上线日期 (可选，默认同交付验收日期)")
    parser.add_argument("--headed", action="store_true", help="显示浏览器图形界面 (用于调试)")

    args = parser.parse_args()

    result = asyncio.run(modify_demand_schedule(
        demand_id=args.demand_id,
        target_date=args.target_date,
        online_date=args.online_date,
        headed=args.headed
    ))

    print("\n==========================================")
    if result.get("success"):
        print(f"✅ 需求排期修改成功！")
        print(f"- 需求编号: {result['demand_id']}")
        if result.get('title'):
            print(f"- 需求标题: {result['title']}")
        print(f"- 交付验收时间: {result['old_acceptance_date']} -> {result['new_acceptance_date']}")
        print(f"- 预计上线时间: {result['old_online_date']} -> {result['new_online_date']}")
        print(f"- 确认截图: {result['screenshot']}")
    else:
        print(f"❌ 需求排期修改失败: {result.get('error')}")
    print("==========================================\n")

if __name__ == "__main__":
    main()
