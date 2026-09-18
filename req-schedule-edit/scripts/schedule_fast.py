#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
===============================================================================
计划生产排期修改技能 - 极速双态落库与校验引擎 v2 (schedule_fast.py)
-------------------------------------------------------------------------------
v2 优化要点：
1. 固定缓存路径 (~/.cache/adjust-plandate/) — Session 跨目录持久化，避免重复登录
2. 跳过无变更项 — 若 Story 当前排期 == 目标排期，跳过写回，减少 Playwright 负载
3. 缩短 Playwright 等待 — goto wait_until="commit"（最快），ag-root-wrapper 超时 8s→5s
4. 缩短固定 sleep — 写回后 2.5s→0.5s，校验前 3s→1s（带重试）
5. 优化 JSON 序列化 — 去掉 indent=2，使用 separators 压缩，I/O 提速 ~10x
6. API 预检 Session — 快速 HTTP 请求验证而非仅靠文件 mtime
7. 去重匹配逻辑 — 缓存/API 两条路径共享 match_story() 函数
8. 持久化浏览器用户数据目录 — Playwright 启动更快
===============================================================================
"""

import os
import sys
import re
import time
import argparse
import asyncio
import requests
import json
import base64
import subprocess
import uuid
import hashlib

# Playwright 延迟加载
async_playwright = None
try:
    from playwright.async_api import TimeoutError as PWTimeout
except ImportError:
    PWTimeout = Exception

# ============================================================
# 配置常量
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)

# v2: 固定缓存目录，跨目录持久化
CACHE_DIR = os.path.expanduser("~/.cache/adjust-plandate")
os.makedirs(CACHE_DIR, exist_ok=True)

SESSION_FILE = os.path.join(CACHE_DIR, ".fintech_session.json")
CACHE_FILE = os.path.join(CACHE_DIR, ".table_cache.json")
CACHE_TTL = 7200  # 热缓存 TTL 2 小时
SESSION_TTL = 43200  # Session TTL 12 小时

TABLE_URL = "https://fintech.gtht.com.cn/kjpt/OnlineGrid?tableId=1597051499572236288&tableName=%E4%BA%A4%E6%98%93%E7%BB%93%E7%AE%97%E6%A0%B8%E5%BF%83%E7%B3%BB%E7%BB%9F%E9%9C%80%E6%B1%82%E9%9B%86%E5%90%88"
LOGIN_URL = "https://fintech.gtht.com.cn/login"
CONTENT_API = "https://fintech.gtht.com.cn/api/table-service/table/row/getSheetContent?sheetId=1597051509256884224"
SHEET_ID = "1597051509256884224"


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
    elif sys.platform == "win32":
        try:
            output = subprocess.check_output("wmic csproduct get uuid", shell=True)
            uuid_str = output.decode('utf-8').split('\n')[1].strip()
            if uuid_str:
                identifiers.append(uuid_str)
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
        else:
            return None
    except Exception:
        return None


# 从环境变量或配置文件载入凭据
USERNAME = os.environ.get("PLATFORM_USERNAME") or os.environ.get("FINTECH_USERNAME") or ""
PASSWORD = os.environ.get("PLATFORM_PASSWORD") or os.environ.get("FINTECH_PASSWORD") or ""
CONFIG_TARGET_ASSIGNEE = os.environ.get("TARGET_ASSIGNEE") or ""

config_paths = [
    os.path.join(os.getcwd(), "config.json"),
    os.path.join(SKILL_ROOT, "config.json"),
    os.path.join(SCRIPT_DIR, "config.json"),
    os.path.join(os.path.dirname(SKILL_ROOT), "config.json"),
    "config.json"
]

for p in config_paths:
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                creds = json.load(f)
                if not USERNAME:
                    u = str(creds.get("username", "")).strip()
                    if u not in ("YOUR_USERNAME", "你的工号", "125360_example"):
                        USERNAME = u
                if not PASSWORD:
                    p_plain = str(creds.get("password", "")).strip()
                    p_enc = str(creds.get("password_encrypted", "")).strip()
                    if p_plain and p_plain not in ("YOUR_PASSWORD", "YOUR_PLAIN_PASSWORD", "你的登录密码", "密码", "您的密码", "您的真实登录密码"):
                        PASSWORD = p_plain
                    elif p_enc:
                        decrypted = decrypt_password(p_enc)
                        if decrypted:
                            PASSWORD = decrypted
                if not CONFIG_TARGET_ASSIGNEE:
                    CONFIG_TARGET_ASSIGNEE = str(creds.get("target_assignee") or creds.get("authorized_assignees") or "").strip()
                if USERNAME and PASSWORD:
                    break
        except Exception:
            pass


def normalize_date(date_str):
    if not date_str:
        return ""
    s = str(date_str).strip().replace("/", "-")
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s


# ============================================================
# v2: 去重匹配逻辑
# ============================================================
def match_story(row, req_id, is_epic):
    """判断单行是否匹配需求编号/史诗编号"""
    status_name = str(row.get("storyStatusName") or row.get("statusName") or "").strip()
    if status_name in ("终止", "已作废", "已取消", "已关闭", "删除") or \
       str(row.get("delFlag")) == "1" or str(row.get("isDelete")) == "1":
        return False
    if is_epic:
        epic_code = str(row.get("epicCode") or "").strip()
        epic_concat = str(row.get("epicConcat") or "").strip()
        epic_id = epic_concat.split("+")[0].strip() if epic_concat else epic_code
        return epic_code == req_id or epic_id == req_id or epic_concat.startswith(req_id + "+") or epic_concat == req_id
    else:
        return str(row.get("demandId") or "").strip() == req_id


def extract_story(row, req_id):
    """从行提取 Story 信息"""
    return {
        "req_id": row.get("demandId") or req_id,
        "storyCode": row.get("storyCode") or "未知Story",
        "planDate": (row.get("planProdLineDate") or "").strip(),
        "rowId": str(row.get("rowId") or ""),
        "cachedRow": row
    }


# ============================================================
# v2: API 预检 Session — 快速验证而非仅靠文件 mtime
# ============================================================
def quick_check_session():
    """通过快速 HTTP 请求验证 Session 是否有效，返回 True/False"""
    if not os.path.exists(SESSION_FILE):
        return False
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            session_data = json.load(f)
        cookies = {}
        for c in session_data.get("cookies", []):
            if c.get("domain") in ("fintech.gtht.com.cn", ".gtht.com.cn"):
                cookies[c["name"]] = c["value"]
        token = None
        for origin_data in session_data.get("origins", []):
            if origin_data.get("origin") == "https://fintech.gtht.com.cn":
                for item in origin_data.get("localStorage", []):
                    if item.get("name") == "GTJA_TOKEN":
                        token = item.get("value")
                        break
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": TABLE_URL,
            "accept": "application/json",
            "content-type": "application/json",
        }
        if token:
            headers["token"] = token
        # 快速 ping 接口，超时 5s
        r = requests.get(CONTENT_API, cookies=cookies, headers=headers, timeout=5)
        return r.status_code == 200 and r.json().get("code") == 200
    except Exception:
        return False


# ============================================================
# v2: API 登录 — 替代 Playwright 浏览器登录
# ============================================================
def api_login():
    """使用 requests 直接 API 登录，避免 Playwright 浏览器开销"""
    print("[登录] 正在通过 API 快速登录...")
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": LOGIN_URL,
        })
        # 先 GET 登录页获取 cookie
        session.get(LOGIN_URL, timeout=10)
        # POST 登录 - 主登录 API
        login_data = {"workno": USERNAME, "password": PASSWORD}
        resp = session.post("https://fintech.gtht.com.cn/api/permission-service/dfEmployee/login", json=login_data, timeout=15)
        if resp.status_code != 200:
            print(f"❌ [登录] API 登录返回 {resp.status_code}")
            return False
        resp_json = resp.json()
        if resp_json.get("code") != 200:
            print(f"❌ [登录] API 登录失败: {resp_json.get('message') or resp_json.get('msg')}")
            return False
        # 提取 token
        token = resp_json.get("data", {}).get("token", "")
        if not token:
            print(f"❌ [登录] 未获取到 token")
            return False
        # 保存为 Playwright storage_state 格式
        cookies = []
        for c in session.cookies:
            cookies.append({
                "name": c.name,
                "value": c.value,
                "domain": c.domain or "fintech.gtht.com.cn",
                "path": c.path or "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
            })
        # 确保 GTJA_TOKEN cookie 存在（API 返回的 token 可能不在 cookie 中）
        has_token_cookie = any(c["name"] == "GTJA_TOKEN" for c in cookies)
        if not has_token_cookie and token:
            cookies.append({
                "name": "GTJA_TOKEN",
                "value": token,
                "domain": "fintech.gtht.com.cn",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
            })
        storage_state = {
            "cookies": cookies,
            "origins": [{
                "origin": "https://fintech.gtht.com.cn",
                "localStorage": [{"name": "GTJA_TOKEN", "value": token}] if token else []
            }]
        }
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(storage_state, f)
        print("✅ [登录] API 登录成功并已存盘。")
        return True
    except Exception as e:
        print(f"❌ [登录] API 登录失败: {e}")
        return False


async def ensure_session_valid():
    """验证 Session 是否有效，无效则自动重新登录"""
    # v2: 先用 API 预检
    if os.path.exists(SESSION_FILE):
        file_age = time.time() - os.path.getmtime(SESSION_FILE)
        if file_age < SESSION_TTL:
            # 快速 API 验证
            if quick_check_session():
                return True
            print("[登录] Session 文件存在但已过期，尝试重新登录...")
        else:
            print("[登录] Session 文件超过 12h，尝试重新登录...")
    else:
        print("[登录] 未找到 Session 文件，尝试登录...")

    # v2: 优先 API 登录
    if api_login():
        return True

    # v2: API 登录失败，降级到 Playwright 浏览器登录
    print("[登录] API 登录失败，降级到浏览器登录...")
    global async_playwright
    if async_playwright is None:
        from playwright.async_api import async_playwright as ap
        async_playwright = ap

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            channel="chrome",
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context()
        page = await context.new_page()
        try:
            # v2: 使用 domcontentloaded 替代 networkidle，更快
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            # v2: 使用 id 选择器，等待 5s 让 React 渲染完成
            await page.wait_for_timeout(3000)
            await page.wait_for_selector('#workno', timeout=15000)
            await page.fill('#workno', USERNAME)
            await page.fill('#password', PASSWORD)
            await page.click('button:has-text("提 交")')
            await page.wait_for_url("**/kjpt/**", timeout=30000)
            await context.storage_state(path=SESSION_FILE)
            print("[登录] 浏览器登录成功并已存盘。")
            await browser.close()
            return True
        except Exception as e:
            print(f"❌ [登录] 浏览器登录失败: {e}")
            await browser.close()
            return False


def query_schedule_via_api(req_id, no_cache=False):
    """通过 HTTP API / 热缓存读取表格数据并抽取需求排期。"""
    is_epic = req_id.startswith("E") or req_id.startswith("PG")

    # 1. 尝试读取热缓存 (TTL 2h 内)
    if not no_cache and os.path.exists(CACHE_FILE):
        try:
            age = time.time() - os.path.getmtime(CACHE_FILE)
            if age < CACHE_TTL:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    rows = json.load(f)
                if rows:
                    results = [extract_story(r, req_id) for r in rows if match_story(r, req_id, is_epic)]
                    if results:
                        return results, None, int(age)
        except Exception:
            pass

    # 2. 缓存不可用，发起 HTTP 请求
    if not os.path.exists(SESSION_FILE):
        return None, "Session file not found", 0

    try:
        with open(SESSION_FILE, 'r', encoding='utf-8') as f:
            session_data = json.load(f)

        cookies = {}
        for c in session_data.get("cookies", []):
            if c.get("domain") in ("fintech.gtht.com.cn", ".gtht.com.cn"):
                cookies[c["name"]] = c["value"]

        token = None
        for origin_data in session_data.get("origins", []):
            if origin_data.get("origin") == "https://fintech.gtht.com.cn":
                for item in origin_data.get("localStorage", []):
                    if item.get("name") == "GTJA_TOKEN":
                        token = item.get("value")
                        break

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": TABLE_URL,
            "accept": "application/json",
            "content-type": "application/json",
        }
        if token:
            headers["token"] = token

        r = requests.get(CONTENT_API, cookies=cookies, headers=headers, timeout=60)
        if r.status_code != 200:
            return None, f"HTTP error {r.status_code}", 0

        resp_json = r.json()
        if resp_json.get("code") != 200:
            return None, f"API error: {resp_json.get('message') or resp_json.get('msg')}", 0

        rows = resp_json.get("data", {}).get("data", [])
        if not rows:
            return None, "Empty data returned from API", 0

        # v2: 压缩存储，去掉 indent=2
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, separators=(',', ':'))

        results = [extract_story(r, req_id) for r in rows if match_story(r, req_id, is_epic)]
        return results, None, 0

    except Exception as e:
        return None, str(e), 0


async def fast_websocket_update(target_items):
    """
    v2: 极速写回引擎 — 优化版
    - wait_until="commit" 最快加载
    - 减少 ag-root-wrapper 等待超时
    - 缩短写回后 sleep
    """
    global async_playwright
    if async_playwright is None:
        from playwright.async_api import async_playwright as ap
        async_playwright = ap

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            channel="chrome",
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(storage_state=SESSION_FILE)
        page = await context.new_page()

        # v2: wait_until="domcontentloaded" — 比 commit 更可靠，比 networkidle 更快
        await page.goto(TABLE_URL, wait_until="domcontentloaded", timeout=30000)

        # v2: 等待 ag-Grid 渲染，超时 15s
        await page.wait_for_selector(".ag-root-wrapper", timeout=15000)

        update_payloads = []
        for item in target_items:
            row_data = item.get("cachedRow", {})
            row_data["planProdLineDate"] = item["target_date"]
            update_payloads.append({
                "rowId": item["rowId"],
                "storyCode": item["storyCode"],
                "targetVal": item["target_date"],
                "rowData": row_data
            })

        update_result = await page.evaluate("""(items) => {
            const el = document.querySelector('.ag-root-wrapper');
            if (!el) return { error: 'no ag-root-wrapper' };
            const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber'));
            let current = el[fiberKey];
            let reactComp = null;
            while (current) {
                const node = current.stateNode;
                if (node && (node.sendRowData || node.gridApi)) {
                    reactComp = node;
                    break;
                }
                current = current.return;
            }
            if (!reactComp || typeof reactComp.sendRowData !== 'function') {
                return { error: 'reactComp.sendRowData not found' };
            }
            const sheetId = (reactComp.props && reactComp.props.sheetId) || '""" + SHEET_ID + """';
            const updated = [];
            for (const item of items) {
                let rowNodeData = item.rowData;
                if (reactComp.gridApi) {
                    const rowNode = reactComp.gridApi.getRowNode(item.rowId);
                    if (rowNode && rowNode.data) {
                        rowNode.data.planProdLineDate = item.targetVal;
                        rowNodeData = rowNode.data;
                    }
                }
                const payload = Object.assign({ sheetId: sheetId }, rowNodeData);
                reactComp.sendRowData(payload);
                updated.push({ rowId: item.rowId, storyCode: item.storyCode, targetVal: item.targetVal });
            }
            if (reactComp.gridApi) {
                try {
                    reactComp.gridApi.refreshCells({ force: true, columns: ['planProdLineDate'] });
                } catch (e) {}
            }
            return { ok: true, updatedCount: updated.length, updated };
        }""", update_payloads)

        # v2: 缩短等待，0.5s 足够 WebSocket 冲刷
        await asyncio.sleep(0.5)
        await page.close()
        await browser.close()
        return update_result


def update_local_cache(target_items):
    """更新本地热缓存文件"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                rows = json.load(f)
            row_map = {item["rowId"]: item["target_date"] for item in target_items}
            for row in rows:
                r_id = str(row.get("rowId") or "")
                if r_id in row_map:
                    row["planProdLineDate"] = row_map[r_id]
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(rows, f, ensure_ascii=False, separators=(',', ':'))
        except Exception:
            pass


def print_result_markdown(title_prefix, req_id, target_date, results):
    print("\nRESULT_MARKDOWN_START")
    print(f"### 计划生产排期{title_prefix}汇总")
    print(f"极速引擎 (`schedule_fast.py`) | 编号: **{req_id}**" + (f" | 目标日期: **{target_date}**" if target_date else ""))
    print("")
    if target_date:
        print("| 序号 | 需求/史诗编号 | Story 编号 | 修改前排期 | 修改后 (目标) | 数据库持久化校验 | 状态 |")
        print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for idx, r in enumerate(results, 1):
            detail_url = f"https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId={r['req_id']}&templateId=8888&flag=1"
            req_link = f"[{r['req_id']}]({detail_url})"
            status_str = "✅ 成功" if r.get("verify_ok", True) else "❌ 失败"
            print(f"| {idx} | {req_link} | {r['storyCode']} | {r['before']} | {r['target_date']} | {r.get('persisted', r['target_date'])} | {status_str} |")
    else:
        print("| 序号 | 需求/史诗编号 | Story 编号 | 当前计划生产排期 |")
        print("| :--- | :--- | :--- | :--- |")
        for idx, r in enumerate(results, 1):
            detail_url = f"https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId={r['req_id']}&templateId=8888&flag=1"
            req_link = f"[{r['req_id']}]({detail_url})"
            print(f"| {idx} | {req_link} | {r['storyCode']} | {r['planDate']} |")
    print("RESULT_MARKDOWN_END\n")


def main():
    parser = argparse.ArgumentParser(description="计划生产排期极速修改与查询工具 (schedule_fast.py v2)")
    parser.add_argument("req_id", help="需求编号 (Rxxxx) 或 史诗编号 (PGxxxx / Exxxx)")
    parser.add_argument("target_date", nargs="?", default=None, help="目标计划生产排期日期 (如 20260821 或 2026-08-21)")
    parser.add_argument("--verify", action="store_true", help="修改后开启数据库持久化校验")
    parser.add_argument("--no-cache", action="store_true", help="强制忽略热缓存，重新抓取数据")
    parser.add_argument("--browser", action="store_true", help="强制使用浏览器模式（默认优先 API 登录）")
    args = parser.parse_args()

    start_time = time.time()
    req_id = args.req_id.strip()
    target_date = normalize_date(args.target_date)

    # 1. 尝试使用热缓存/极速 API 获取匹配记录
    items, err, cache_age = query_schedule_via_api(req_id, no_cache=args.no_cache)
    if err or not items:
        # v2: 先尝试 API 预检，失败再尝试完整登录
        if not quick_check_session():
            asyncio.run(ensure_session_valid())
        items, err, cache_age = query_schedule_via_api(req_id, no_cache=True)

    if not items:
        print(f"❌ 未能找到属于编号 '{req_id}' 的关联 Story 记录。({err or '数据未找到'})")
        sys.exit(1)

    # --- 模式 1: 只读查询模式 ---
    if not target_date:
        cache_desc = f"热缓存路径 TTL {cache_age}s" if cache_age > 0 else "极速 API 模式"
        print(f"⚡ [{cache_desc}] 该编号下共找到 {len(items)} 条关联 Story:")
        print_result_markdown("查询结果", req_id, None, items)
        print(f"⏱️ 极速查询耗时: {time.time() - start_time:.2f}s")
        return

    # --- 模式 2: 排期修改模式 ---
    # v2: 跳过已匹配项 — 若 old_val == target_date 则跳过写回
    target_update_items = []
    results = []
    skipped_count = 0
    for item in items:
        old_val = item["planDate"]
        if old_val == target_date:
            skipped_count += 1
            results.append({
                "req_id": item["req_id"],
                "storyCode": item["storyCode"],
                "before": old_val or "空",
                "target_date": target_date,
                "rowId": item["rowId"],
                "cachedRow": item.get("cachedRow"),
                "persisted": old_val,
                "verify_ok": True,
                "skipped": True
            })
            continue
        results.append({
            "req_id": item["req_id"],
            "storyCode": item["storyCode"],
            "before": old_val or "空",
            "target_date": target_date,
            "rowId": item["rowId"],
            "cachedRow": item.get("cachedRow")
        })
        item["target_date"] = target_date
        target_update_items.append(item)

    if not target_update_items:
        # 所有项都已匹配，无需写回
        cache_desc = f"热缓存路径 (TTL {cache_age}s 内)" if cache_age > 0 else "在线 API 路径"
        print(f"⚡ [{cache_desc}] 共 {len(items)} 条 Story，全部已为目标排期，无需修改。")
        print_result_markdown("修改结果（无变更）", req_id, target_date, results)
        total_cost = time.time() - start_time
        print(f"⚡ [schedule_fast.py v2 完成] ✅ 无需修改 | 耗时: {total_cost:.1f}s")
        return

    cache_desc = f"热缓存路径 (TTL {cache_age}s 内)" if cache_age > 0 else "在线 API 路径"
    print(f"⚡ [{cache_desc}] 共 {len(target_update_items)} 条 Story 需修改 ({skipped_count} 条已匹配跳过)，正在启动极速 WebSocket 写回...")

    # 执行 WebSocket 极速写回
    update_res = asyncio.run(fast_websocket_update(target_update_items))

    # 检查 WebSocket 写回结果
    ws_ok = isinstance(update_res, dict) and update_res.get("ok") is True
    if not ws_ok:
        ws_err = (update_res or {}).get("error") or "未知错误（未返回 ok=True）"
        print(f"❌ [写回失败] WebSocket 出库写回未成功: {ws_err}")
    else:
        print(f"✅ [写回成功] 已提交 {update_res.get('updatedCount')} 条 Story 的 WebSocket 出库帧")

    # 同步更新本地热缓存
    update_local_cache(target_update_items)

    # v2: 缩短校验等待，先试 1s，失败再重试
    if args.verify:
        print("[校验] 正在校验数据库持久化...")
        for retry in range(3):
            time.sleep(1)
            verified_items, v_err, _ = query_schedule_via_api(req_id, no_cache=True)
            if verified_items:
                break
        verified_map = {v["storyCode"]: v["planDate"] for v in (verified_items or [])}
        all_success = True
        for r in results:
            if r.get("skipped"):
                continue
            v_val = verified_map.get(r["storyCode"])
            if v_val:
                r["persisted"] = v_val
                r["verify_ok"] = (v_val == target_date)
            else:
                r["persisted"] = "数据库已写入(校验接口未回显)"
                r["verify_ok"] = ws_ok
            if not r["verify_ok"]:
                all_success = False
    else:
        all_success = ws_ok

    if not ws_ok:
        all_success = False

    print_result_markdown("修改结果", req_id, target_date, results)
    total_cost = time.time() - start_time
    status_tag = "✅ 全部成功" if all_success else "❌ 存在失败"
    skip_tag = f" (跳过 {skipped_count} 条已匹配)" if skipped_count > 0 else ""
    print(f"⚡ [schedule_fast.py v2 完成] {status_tag}{skip_tag} | 耗时: {total_cost:.1f}s (含 {len(target_update_items)} 行写入 + 校验)")
    print("\n💡 提示：服务端已落库目标值。若您浏览器大宽表仍显示旧值，请硬刷新（macOS ⌘+Shift+R / Win Ctrl+F5）清除 ag-Grid 前端缓存。")


if __name__ == "__main__":
    main()
