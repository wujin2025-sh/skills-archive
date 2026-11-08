#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
edit_req_plandate.py — 调整需求计划交付时间（需求预计上线时间 & 需求预计交付验收时间）
====================================================================================
访问国泰海通金融科技平台「需求管理」详情页，点击右上角「修改排期」按钮，
在「需求排期确认」弹窗中自动修改「需求预计交付验收时间」与「需求预计上线时间」并提交保存。

支持：
  - 按需求编号（R26xxxxxxx）：修改单个需求
  - 按史诗编号（E/PG 开头）：自动枚举史诗下所有关联需求，同一浏览器会话批量修改

用法:
    .venv/bin/python edit_req_plandate.py <需求编号/史诗编号> <目标交付验收日期> [目标上线日期] [--headed] [--refresh-epic]

示例:
    .venv/bin/python edit_req_plandate.py R2607150083 20261031
    .venv/bin/python edit_req_plandate.py R2607150083 2026-10-31 2026-11-05
    .venv/bin/python edit_req_plandate.py PG202204-0259 20261031 --headed
    .venv/bin/python edit_req_plandate.py PG202204-0259 20261031 --refresh-epic   # 强制刷新大宽表缓存
"""

import sys
import os
import re
import time
import pickle
import asyncio
import json
import base64
import argparse
import subprocess
import uuid
import hashlib
import requests
from playwright.async_api import async_playwright

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
        os.path.join(os.path.dirname(SKILL_ROOT), "config.json"),
        os.path.expanduser("~/.config/gtht/config.json"),
        "config.json",
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
                if u and u not in ("YOUR_USERNAME", "你的工号", "125360_example") and not username:
                    username = u
                if not password:
                    if p_plain and p_plain not in ("YOUR_PASSWORD", "YOUR_PLAIN_PASSWORD", "你的登录密码", "密码", "您的密码"):
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
CONTENT_URL = "https://fintech.gtht.com.cn/api/table-service/table/row/getSheetContent?sheetId=1597051509256884224"

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
# 3. Session / Token 读取（用于史诗枚举 API）
# ============================================================
def load_session_credentials():
    cookies = {}
    token = None
    if not os.path.exists(SESSION_FILE):
        return cookies, token
    try:
        with open(SESSION_FILE, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        for c in session_data.get("cookies", []):
            if c.get("domain") in ("fintech.gtht.com.cn", ".gtht.com.cn"):
                cookies[c["name"]] = c["value"]
        for origin_data in session_data.get("origins", []):
            if origin_data.get("origin") == "https://fintech.gtht.com.cn":
                for item in origin_data.get("localStorage", []):
                    if item.get("name") == "GTJA_TOKEN":
                        token = item.get("value")
                        break
    except Exception as e:
        print(f"[API] 读取 session 文件失败: {e}")
    return cookies, token


BIGTABLE_CACHE = os.path.join(SCRIPT_DIR, ".sheet_rows_cache_plandate.pkl")
BIGTABLE_TTL = 300  # 大宽表快照 300s 内复用（连续批量/重复运行秒级命中）


def _direct_session():
    """直连 Session：trust_env=False 不读系统代理/环境代理（macOS 系统代理会导致
    ProxyError 503 / ReadTimeout 60s）。标准 requests 与包装环境均兼容。"""
    s = requests.Session()
    try:
        s.trust_env = False
    except Exception:
        pass
    return s


def get_demands_by_epic(epic_id, cookies, token, refresh_epic=False):
    """根据史诗编号获取关联的需求 ID 列表。
    优先用大宽表 getSheetContent 扫描（epicCode/epicConcat 可靠匹配，与 adjust-plandate 一致），
    listAllByExamples 史诗管理 API 作为补充（部分史诗编号在该接口搜不到，如 PG202204-0259）。
    性能优化（2026-11-01）：
      - 所有 HTTP 请求强制 trust_env=False 直连（不经系统代理，杜绝 ProxyError / ReadTimeout 60s）；
      - 大宽表 38MB 快照带 300s 短 TTL 热缓存（.sheet_rows_cache_plandate.pkl），连续运行秒级复用，
        --refresh-epic 强制刷新；缓存命中会打印时间戳提示，避免"静默回退旧数据"。
    """
    headers = {"accept": "application/json", "content-type": "application/json"}
    if token:
        headers["token"] = token

    def _scan_bigtable():
        # 短 TTL 热缓存（300s）：命中直接复用，秒级完成；强制刷新则跳过缓存
        if os.path.exists(BIGTABLE_CACHE) and not refresh_epic:
            try:
                age = time.time() - os.path.getmtime(BIGTABLE_CACHE)
                if age <= BIGTABLE_TTL:
                    with open(BIGTABLE_CACHE, "rb") as f:
                        cached = pickle.load(f)
                    where = time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(BIGTABLE_CACHE)))
                    print(f"[缓存] 复用 {where} 大宽表快照 {len(cached)} 行（{int(age)}s 前生成，--refresh-epic 强制刷新）")
                    return cached
            except Exception as e:
                print(f"[缓存] 读取大宽表缓存失败（{e}），回退在线拉取...")
        hdr = dict(headers)
        hdr["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        hdr["Referer"] = "https://fintech.gtht.com.cn/kjpt/OnlineGrid?tableId=1597051499572236288"
        raw = _direct_session().get(CONTENT_URL, cookies=cookies, headers=hdr, timeout=120)
        if raw.status_code != 200:
            raise ValueError(f"大宽表 HTTP 状态码错误: {raw.status_code}")
        js = raw.json()
        if js.get("code") != 200:
            raise ValueError(f"大宽表 API 错误: {js.get('message') or js.get('msg')}")
        rows = js.get("data", {}).get("data", [])
        # 落缓存（TTL 300s，下次复用；写入失败不影响主流程）
        try:
            with open(BIGTABLE_CACHE, "wb") as f:
                pickle.dump(rows, f)
            print(f"[缓存] 大宽表快照已落盘 {len(rows)} 行 -> {BIGTABLE_CACHE}（{BIGTABLE_TTL}s 内复用）")
        except Exception as e:
            print(f"[缓存] 大宽表快照落盘失败（不影响主流程）: {e}")
        return rows

    # ===== 路径 1：大宽表扫描（可靠主路径，与 adjust-plandate 一致）=====
    try:
        print(f"[API] 正在通过大宽表扫描获取史诗 {epic_id} 关联的需求...")
        rows = _scan_bigtable()
        demand_ids = set()
        epic_id_lower = epic_id.lower()
        for r in rows:
            epic_code = str(r.get("epicCode") or "").strip()
            epic_concat = str(r.get("epicConcat") or "").strip()
            demand_id = str(r.get("demandId") or "").strip()
            if not demand_id:
                continue
            if epic_code == epic_id or epic_id_lower in epic_concat.lower():
                demand_ids.add(demand_id)
        if demand_ids:
            print(f"[API] 大宽表扫描命中 {len(demand_ids)} 个关联需求: {sorted(demand_ids)}")
            return sorted(demand_ids)
        print("[API] 大宽表扫描未命中，尝试史诗管理接口补充...")
    except Exception as e:
        print(f"[API] 大宽表扫描异常: {e}，尝试史诗管理接口补充...")

    # ===== 路径 2：史诗管理接口 listAllByExamples 补充 =====
    try:
        LIST_URL = "https://fintech.gtht.com.cn/api/multi-project-collaboration-service/kjptProjectCollaborationEpic/listAllByExamples"

        def _search_epic(kw, size, current=1):
            r = _direct_session().post(LIST_URL, cookies=cookies, headers=headers,
                                       json={"current": current, "size": size, "searchKeyWords": kw}, timeout=60)
            if r.status_code != 200:
                raise ValueError(f"查询史诗列表 HTTP 状态码错误: {r.status_code}")
            return r.json().get("data", {}).get("records", [])

        epic_record = None
        records = _search_epic(epic_id, 50)
        epic_record = next((rec for rec in records if str(rec.get("code")) == epic_id), None)
        if not epic_record:
            prefix = epic_id.split("-")[0]
            for page in (1, 2, 3, 4, 5):
                page_records = _search_epic(prefix, 200, current=page)
                epic_record = next((rec for rec in page_records if str(rec.get("code")) == epic_id), None)
                if epic_record or len(page_records) < 200:
                    break
        if not epic_record:
            print(f"[API] 警告: 未找到史诗 {epic_id}，请核对编号是否正确。")
            return []

        epic_internal_id = epic_record["id"]
        print(f"[API] 史诗 {epic_id} 的内部ID为: {epic_internal_id}")
        DEMAND_URL = "https://fintech.gtht.com.cn/api/demand-service/demandsub/list"
        r2 = _direct_session().post(DEMAND_URL, cookies=cookies, headers=headers,
                                    json={"currentPage": 1, "pageSize": 500, "epicIds": epic_internal_id, "companyId": "comp01"},
                                    timeout=60)
        if r2.status_code != 200:
            raise ValueError(f"查询关联需求列表 HTTP 状态码错误: {r2.status_code}")
        demand_records = r2.json().get("data", {}).get("records", [])
        demand_ids = [rec["demandId"].strip() for rec in demand_records if rec.get("demandId")]
        return sorted(list(set(demand_ids)))
    except Exception as e:
        print(f"[API] 史诗管理接口补充也失败: {e}")
        return []


# ============================================================
# 4. 登录（Session 复用）
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


# ============================================================
# 5. 修改单个需求排期弹窗
# ============================================================
async def fill_date_input(page, modal, selector, target_date):
    """快路径优先填日期：fill 一次性注入（触发 React input 事件）→ 回读校验；
    回读不一致则回退逐字符键入（delay=30）+ Enter；最后关闭日期面板并轮询回读，
    值到位即继续（替代原 500+300+500+1000ms 固定 sleep，单框最多 ~2.5s 兜底）。"""
    inp = modal.locator(selector).first
    if await inp.count() == 0:
        return False

    await inp.scroll_into_view_if_needed()
    try:
        await inp.evaluate("el => el.removeAttribute('readonly')")
    except Exception:
        pass
    try:
        await inp.click(timeout=2000)
    except Exception:
        await inp.evaluate("el => el.click()")

    # 快路径：fill 一次性注入
    try:
        await inp.fill(target_date)
    except Exception:
        pass
    await page.wait_for_timeout(150)
    v = await inp.input_value()
    if v != target_date:
        # 慢路径：逐字符键入（delay=30 比原 50 快 40%）+ Enter
        is_mac = sys.platform == "darwin"
        await page.keyboard.press("Meta+A" if is_mac else "Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(target_date, delay=30)
        await page.keyboard.press("Enter")

    # 关闭日期面板下拉，触发 React blur 同步
    try:
        await modal.locator('.ant-modal-title').click(force=True)
    except Exception:
        pass

    # 轮询回读：值到位即继续（兜底 2.5s）
    deadline = time.time() + 2.5
    while time.time() < deadline:
        v = await inp.input_value()
        if v == target_date:
            break
        await page.wait_for_timeout(120)
    return v


async def modify_single_demand(page, demand_id, target_date, online_date):
    detail_url = DETAIL_URL_TEMPL.format(demand_id)
    print(f"\n[需求 {demand_id}] 开始处理...")

    # 页面导航：commit 即返回（不等 SPA 全渲染），随后条件等待「修改排期」按钮出现
    try:
        await page.goto(detail_url, wait_until="commit", timeout=60000)
    except Exception as e:
        print(f"[导航] 页面导航异常: {e}，改用 domcontentloaded 重试...")
        await page.goto(detail_url, wait_until="domcontentloaded", timeout=60000)

    # 检查重定向登录
    if "login" in page.url.lower():
        print("[登录] Session 已失效，请先确保登录态正常！")
        return {"success": False, "demand_id": demand_id, "error": "登录态失效"}

    # 条件等待「修改排期」按钮出现（替代原固定 2.5s sleep，页面可用即继续）
    btn = page.locator('button:has-text("修改排期"), .ant-btn:has-text("修改排期")').first
    try:
        await btn.wait_for(state="visible", timeout=15000)
    except Exception:
        if await btn.count() == 0:
            print(f"[错误] 未找到需求 {demand_id} 详情页的「修改排期」按钮，可能无权限或页面结构有变！")
            return {"success": False, "demand_id": demand_id, "error": "未找到「修改排期」按钮"}

    print("[交互] 点击「修改排期」按钮...")
    try:
        await btn.click(timeout=5000)
    except Exception as e:
        print(f"[交互] 常规点击受阻 ({e})，尝试使用 JS 模拟点击...")
        await btn.evaluate("node => node.click()")

    # 定位「需求排期确认」弹窗
    modal = page.locator('.ant-modal-content').last
    try:
        await modal.wait_for(state="visible", timeout=5000)
    except Exception:
        print("[错误] 未弹出「需求排期确认」弹窗！")
        return {"success": False, "demand_id": demand_id, "error": "未弹出排期确认弹窗"}

    sel1 = 'input[placeholder="需求预计交付验收时间"]'
    sel2 = 'input[placeholder="需求预计上线时间"]'
    inp1 = modal.locator(sel1).first
    inp2 = modal.locator(sel2).first

    v1_old = await inp1.input_value() if await inp1.count() > 0 else ""
    v2_old = await inp2.input_value() if await inp2.count() > 0 else ""
    print(f"[当前值] 需求预计交付验收时间: {v1_old} | 需求预计上线时间: {v2_old}")

    # 幂等跳过（前置，2026-11-01 优化）：读取弹窗当前值后立即判断，达标直接取消返回，不执行 fill；
    # 判断条件不变 = 弹窗打开时平台当前值==目标值。切勿改用填值后的 v1_new/v2_new 判断
    # （填值成功即等于目标值，会把"刚填好未提交"误判为已达成而取消弹窗，导致修改丢失）
    if v1_old == target_date and v2_old == online_date:
        print("[跳过] 打开弹窗时两个日期字段均已等于目标值，无需提交。")
        # 尝试关闭弹窗（若已自动关闭则忽略），轮询弹窗隐藏最多 2.5s
        try:
            cancel_btn = modal.locator('button:has-text("取 消"), button:has-text("取消")').first
            if await cancel_btn.count() > 0:
                await cancel_btn.click()
                try:
                    await modal.wait_for(state="hidden", timeout=2500)
                except Exception:
                    pass
        except Exception:
            pass
        return {"success": True, "demand_id": demand_id, "old_acceptance_date": v1_old,
                "old_online_date": v2_old, "new_acceptance_date": v1_old, "new_online_date": v2_old,
                "skipped": True}

    # 修改日期输入框（自适应顺序调整以绕过前端最大/最小日期范围校验）
    print(f"[修改] 尝试 Order 1: 先填上线时间 ({online_date})，再填交付验收时间 ({target_date})...")
    v2_new = await fill_date_input(page, modal, sel2, online_date)
    v1_new = await fill_date_input(page, modal, sel1, target_date)

    if v1_new != target_date or v2_new != online_date:
        print(f"[修改] Order 1 未能完全生效（当前值: {v1_new} | {v2_new}），尝试 Order 2: 先填交付验收时间，再填上线时间...")
        v1_new = await fill_date_input(page, modal, sel1, target_date)
        await page.wait_for_timeout(300)
        v2_new = await fill_date_input(page, modal, sel2, online_date)
        await page.wait_for_timeout(300)

    print(f"[新设定值] 需求预计交付验收时间: {v1_new} | 需求预计上线时间: {v2_new}")

    # 收回所有下拉遮罩
    try:
        await modal.locator('.ant-modal-title').click()
    except Exception:
        pass

    # 点击确认按钮
    confirm_btn = modal.locator('button:has-text("确 认"), button:has-text("确认"), .ant-btn-primary').first
    if await confirm_btn.count() == 0:
        print("[错误] 弹窗内未找到「确 认」按钮！")
        return {"success": False, "demand_id": demand_id, "error": "未找到弹窗确认按钮"}

    print("[提交] 点击弹窗「确 认」按钮...")
    try:
        await confirm_btn.click()
    except Exception as e:
        print(f"[提交] 点击确认按钮异常 ({e})，尝试 JS 模拟点击...")
        await confirm_btn.evaluate("node => node.click()")
    # 轮询弹窗关闭（成功提交后弹窗即隐藏），替代原固定 3.5s sleep，最多等 8s
    try:
        await modal.wait_for(state="hidden", timeout=8000)
    except Exception:
        print("[提交] 等待弹窗关闭超时（按成功处理，可在平台复核）")

    return {"success": True, "demand_id": demand_id, "old_acceptance_date": v1_old,
            "old_online_date": v2_old, "new_acceptance_date": v1_new, "new_online_date": v2_new,
            "skipped": False}


# ============================================================
# 6. 主流程
# ============================================================
async def run(target_id, target_date, online_date, headed, refresh_epic=False):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not headed,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            storage_state=SESSION_FILE if os.path.exists(SESSION_FILE) else None,
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = await context.new_page()

        try:
            # 1. 确保登录
            await ensure_login(context, page)

            # 2. 提取 Token 和 Cookies（用于史诗枚举 API）
            cookies_list = await context.cookies()
            cookies = {c["name"]: c["value"] for c in cookies_list
                       if c.get("domain") in ("fintech.gtht.com.cn", ".gtht.com.cn")}
            # 优先从 session 文件读取 token（避免空白页 localStorage 访问受限）
            _, token = load_session_credentials()
            if not token:
                try:
                    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(1500)
                    token = await page.evaluate("() => localStorage.getItem('GTJA_TOKEN')")
                except Exception:
                    token = None

            # 3. 确定要处理的需求 ID 列表
            demand_ids = []
            target_id_upper = target_id.strip().upper()
            if target_id_upper.startswith("R") and "-" not in target_id_upper:
                demand_ids = [target_id_upper]
                print(f"[模式] 单个需求修改模式: {demand_ids[0]}")
            elif target_id_upper.startswith("E") or target_id_upper.startswith("PG"):
                print(f"[模式] 史诗批量修改模式: {target_id}")
                demand_ids = get_demands_by_epic(target_id, cookies, token, refresh_epic=refresh_epic)
                if not demand_ids:
                    print(f"未找到史诗「{target_id}」下的任何需求！请核对史诗编号是否正确。")
                    sys.exit(1)
                print(f"[史诗] 关联的需求 ID 列表（{len(demand_ids)} 个）: {demand_ids}")
            else:
                # 默认按史诗处理（含纯数字/其他）
                print(f"[模式] 史诗批量修改模式 (默认): {target_id}")
                demand_ids = get_demands_by_epic(target_id, cookies, token, refresh_epic=refresh_epic)
                if not demand_ids:
                    print(f"未找到史诗「{target_id}」下的任何需求！请核对史诗编号是否正确。")
                    sys.exit(1)
                print(f"[史诗] 关联的需求 ID 列表（{len(demand_ids)} 个）: {demand_ids}")

            # 4. 循环修改各需求排期
            results = []
            success_count = 0
            fail_count = 0
            for did in demand_ids:
                try:
                    res = await modify_single_demand(page, did, target_date, online_date)
                    results.append(res)
                    if res.get("success"):
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception as ex:
                    print(f"修改需求 {did} 发生异常: {ex}")
                    results.append({"success": False, "demand_id": did, "error": str(ex)})
                    fail_count += 1

            # 5. 汇总输出
            print(f"\n{'='*60}")
            print(f"[汇总] 处理完成。成功: {success_count} 个，失败: {fail_count} 个")
            for r in results:
                if r.get("success"):
                    skip = "（已跳过，值一致）" if r.get("skipped") else ""
                    print(f"  ✅ {r['demand_id']}: 交付验收 {r.get('old_acceptance_date')} -> {r.get('new_acceptance_date')}"
                          f" | 上线 {r.get('old_online_date')} -> {r.get('new_online_date')}{skip}")
                else:
                    print(f"  ❌ {r.get('demand_id')}: {r.get('error')}")
            print(f"{'='*60}")

            # 保存结果截图（非致命）
            if demand_ids:
                try:
                    screenshot_path = os.path.join(SCRIPT_DIR, "edit_plandate_last_result.png")
                    # timeout 3s：headless 等字体加载会拖到 10s 超时，缩短后失败即忽略（非关键步骤）
                    await page.screenshot(path=screenshot_path, timeout=3000)
                    print(f"[截图] 结果已保存: {screenshot_path}")
                except Exception as se:
                    print(f"[截图] 截图保存失败（不影响修改结果）: {se}")

        except Exception as e:
            print(f"\n执行发生异常: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            try:
                await context.storage_state(path=SESSION_FILE)
            except Exception:
                pass
            await browser.close()


def main():
    parser = argparse.ArgumentParser(description="调整需求计划交付时间（需求预计上线时间 & 需求预计交付验收时间）")
    parser.add_argument("target_id", help="需求编号（如 R2607150083）或史诗编号（如 PG202204-0259）")
    parser.add_argument("target_date", help="目标需求预计交付验收日期，例如 20261031 或 2026-10-31")
    parser.add_argument("online_date", nargs="?", default=None, help="目标需求预计上线日期（可选，默认同交付验收日期）")
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    parser.add_argument("--refresh-epic", action="store_true", help="强制刷新大宽表快照缓存（史诗枚举默认复用 300s 内缓存）")
    args = parser.parse_args()

    target_date = format_date_str(args.target_date)
    online_date = format_date_str(args.online_date) if args.online_date else target_date

    print(f"\n{'='*50}")
    print(f"  调整需求计划交付时间")
    print(f"  目标 ID: {args.target_id}")
    print(f"  需求预计交付验收时间: {target_date}")
    print(f"  需求预计上线时间: {online_date}")
    print(f"  模式: {'可视化 (Headed)' if args.headed else '无头 (Headless)'}")
    print(f"  史诗枚举刷新: {'强制刷新缓存' if args.refresh_epic else '300s 缓存优先'}")
    print(f"{'='*50}")

    asyncio.run(run(args.target_id.strip(), target_date, online_date, args.headed, refresh_epic=args.refresh_epic))


if __name__ == "__main__":
    main()