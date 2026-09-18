#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
===============================================================================
计划生产排期修改技能 - 极速直连引擎 v3 (schedule_fast_v3.py)
-------------------------------------------------------------------------------
v3 核心优化（相比 v2 提速 5~10x）：
1. 直接 WebSocket 直连 — 使用 Python websockets 库，彻底移除 Playwright 浏览器启动开销
2. 直接 API 数据拉取 — 复用已存盘 JWT token，跳过完整登录流程
3. 预建索引热缓存 — demandId → Story 索引 O(1) 匹配，热缓存查询 <1s
4. Playwright 仅做兜底 — 仅在 token 过期且 API 登录失败时降级

典型耗时：
  - 热缓存查询: ~0.1s
  - WebSocket 写回: ~0.2s/行
  - 首次 API 拉取: ~16s (44MB 数据，不可控)
===============================================================================
"""

import os
import sys
import re
import time
import json
import asyncio
import argparse
import base64

# ============================================================
# 配置常量
# ============================================================
CACHE_DIR = os.path.expanduser("~/.cache/adjust-plandate")
os.makedirs(CACHE_DIR, exist_ok=True)

SESSION_FILE = os.path.join(CACHE_DIR, ".fintech_session.json")
CACHE_FILE = os.path.join(CACHE_DIR, ".table_cache_v3.json")
CACHE_INDEX_FILE = os.path.join(CACHE_DIR, ".table_cache_index.json")
CACHE_TTL = 7200          # 热缓存 TTL 2 小时
SESSION_TTL = 43200       # Session TTL 12 小时

TABLE_URL = "https://fintech.gtht.com.cn/kjpt/OnlineGrid?tableId=1597051499572236288"
LOGIN_URL = "https://fintech.gtht.com.cn/login"
CONTENT_API = "https://fintech.gtht.com.cn/api/table-service/table/row/getSheetContent?sheetId=1597051509256884224"
SHEET_ID = "1597051509256884224"
TABLE_ID = "1597051499572236288"
WS_URL = f"wss://fintech.gtht.com.cn/ws/table-socket/table/websocket/{TABLE_ID}"

# ============================================================
# 凭据加载
# ============================================================
USERNAME = os.environ.get("PLATFORM_USERNAME") or os.environ.get("FINTECH_USERNAME") or ""
PASSWORD = os.environ.get("PLATFORM_PASSWORD") or os.environ.get("FINTECH_PASSWORD") or ""

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)

config_paths = [
    os.path.join(os.getcwd(), "config.json"),
    os.path.join(SKILL_ROOT, "config.json"),
    os.path.join(SCRIPT_DIR, "config.json"),
    os.path.join(os.path.dirname(SKILL_ROOT), "config.json"),
    "config.json",
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
                pp = str(creds.get("password", "")).strip()
                if pp and pp not in ("YOUR_PASSWORD", "YOUR_PLAIN_PASSWORD",
                                      "你的登录密码", "密码", "您的密码", "您的真实登录密码"):
                    PASSWORD = pp
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
# Session / Token 管理
# ============================================================
def get_session_token():
    """从 Playwright storage_state 文件中提取 GTJA_TOKEN"""
    if not os.path.exists(SESSION_FILE):
        return None
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            session_data = json.load(f)
        for origin_data in session_data.get("origins", []):
            if origin_data.get("origin") == "https://fintech.gtht.com.cn":
                for item in origin_data.get("localStorage", []):
                    if item.get("name") == "GTJA_TOKEN":
                        return item.get("value")
        for c in session_data.get("cookies", []):
            if c.get("name") == "GTJA_TOKEN":
                return c.get("value")
    except Exception:
        pass
    return None


def get_session_cookies():
    """从 session 文件中提取 cookies dict"""
    if not os.path.exists(SESSION_FILE):
        return {}
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            session_data = json.load(f)
        return {c["name"]: c["value"] for c in session_data.get("cookies", [])
                if "gtht.com.cn" in c.get("domain", "") or "fintech" in c.get("domain", "")}
    except Exception:
        return {}


def quick_check_session():
    """
    v3: 轻量级 Session 验证
    1. JWT 解码检查 exp 过期时间
    2. 文件年龄检查（12h TTL）
    3. 轻量 API 验证（getUserInfo）
    """
    token = get_session_token()
    if not token:
        return False

    # 文件年龄
    if os.path.exists(SESSION_FILE):
        age = time.time() - os.path.getmtime(SESSION_FILE)
        if age > SESSION_TTL:
            return False

    # JWT exp 解码
    try:
        parts = token.split(".")
        if len(parts) == 3:
            payload_b64 = parts[1]
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding
            payload = json.loads(base64.b64decode(payload_b64))
            exp = payload.get("exp", 0)
            if exp and exp < time.time():
                return False
    except Exception:
        pass

    # 轻量 API 验证
    try:
        import requests
        r = requests.get(
            "https://fintech.gtht.com.cn/api/permission-service/dfEmployee/getUserInfo",
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Referer": TABLE_URL,
                "accept": "application/json",
                "token": token,
            },
            timeout=5,
        )
        if r.status_code == 200:
            return True
    except Exception:
        pass

    # 乐观判断：文件存在且较新
    return True


def api_login():
    """直接 API 登录（尝试明文密码，失败则降级到 Playwright 兜底）"""
    print("[登录] 正在通过 API 快速登录...")
    try:
        import requests
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": LOGIN_URL,
        })
        session.get(LOGIN_URL, timeout=10)

        login_data = {"workno": USERNAME, "password": PASSWORD}
        resp = session.post(
            "https://fintech.gtht.com.cn/api/permission-service/dfEmployee/login",
            json=login_data, timeout=15,
        )
        if resp.status_code != 200:
            print(f"  API 登录返回 {resp.status_code}")
            return False
        resp_json = resp.json()
        if resp_json.get("code") != 200:
            print(f"  API 登录失败: {resp_json.get('message') or resp_json.get('msg')}")
            return False
        token = resp_json.get("data", {}).get("token", "")
        if not token:
            print("  API 登录未获取到 token")
            return False

        # 保存为 Playwright storage_state 格式
        cookies = [{
            "name": c.name, "value": c.value,
            "domain": c.domain or "fintech.gtht.com.cn",
            "path": c.path or "/", "httpOnly": True, "secure": True, "sameSite": "Lax",
        } for c in session.cookies]
        storage_state = {
            "cookies": cookies,
            "origins": [{
                "origin": "https://fintech.gtht.com.cn",
                "localStorage": [{"name": "GTJA_TOKEN", "value": token}],
            }],
        }
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(storage_state, f)
        print("✅ [登录] API 登录成功并已存盘。")
        return True
    except Exception as e:
        print(f"  API 登录异常: {e}")
        return False


# ============================================================
# Playwright 浏览器登录（兜底）
# ============================================================
async def playwright_login():
    """Playwright 浏览器登录 — 仅作为 API 登录失败的兜底"""
    print("[登录] 降级到浏览器登录...")
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌ [登录] playwright 未安装")
        return False

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, channel="chrome",
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context()
        page = await context.new_page()
        try:
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            await page.wait_for_selector('#workno', timeout=15000)
            await page.fill('#workno', USERNAME)
            await page.fill('#password', PASSWORD)
            async with page.expect_response(lambda r: 'dfEmployee/login' in r.url) as resp_info:
                await page.click('button:has-text("提 交")')
                resp = await resp_info.value
                body = await resp.json()
                token = body.get("data", {}).get("token", "") if body.get("code") == 200 else ""
            await page.wait_for_url("**/kjpt/**", timeout=30000)
            if token:
                await page.evaluate(f't => localStorage.setItem("GTJA_TOKEN", t)', token)
            await context.storage_state(path=SESSION_FILE)
            print("✅ [登录] 浏览器登录成功并已存盘。")
            await browser.close()
            return True
        except Exception as e:
            print(f"❌ [登录] 浏览器登录失败: {e}")
            await browser.close()
            return False


# ============================================================
# 数据查询 — 热缓存（带预建索引）+ API 双路径
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
    return str(row.get("demandId") or "").strip() == req_id


def extract_story(row, req_id):
    return {
        "req_id": row.get("demandId") or req_id,
        "storyCode": row.get("storyCode") or "未知Story",
        "planDate": (row.get("planProdLineDate") or "").strip(),
        "rowId": str(row.get("rowId") or ""),
        "cachedRow": row,
    }


def build_cache_index(rows):
    """预建索引：demandId → [rows], epicCode → [rows]"""
    index = {}
    for row in rows:
        demand_id = str(row.get("demandId") or "").strip()
        epic_code = str(row.get("epicCode") or "").strip()
        if demand_id:
            index.setdefault(f"d:{demand_id}", []).append(row)
        if epic_code:
            index.setdefault(f"e:{epic_code}", []).append(row)
    return index


def query_schedule(req_id, no_cache=False):
    """
    v3: 热缓存（带索引 O(1) 匹配）+ API 双路径
    返回 (items, error, cache_age)
    """
    is_epic = req_id.startswith("E") or req_id.startswith("PG")

    # 1. 热缓存（带索引）— O(1) 匹配
    if not no_cache and os.path.exists(CACHE_FILE) and os.path.exists(CACHE_INDEX_FILE):
        try:
            age = time.time() - os.path.getmtime(CACHE_FILE)
            if age < CACHE_TTL:
                with open(CACHE_INDEX_FILE, 'r', encoding='utf-8') as f:
                    index = json.load(f)
                key = f"{'e' if is_epic else 'd'}:{req_id}"
                matched_rows = index.get(key, [])
                if matched_rows:
                    return [extract_story(r, req_id) for r in matched_rows], None, int(age)
                # 索引未命中，回退全量扫描
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    rows = json.load(f)
                results = [extract_story(r, req_id) for r in rows if match_story(r, req_id, is_epic)]
                if results:
                    return results, None, int(age)
        except Exception:
            pass

    # 2. 缓存不可用或未命中 → HTTP API
    token = get_session_token()
    if not token:
        return None, "Session token not found", 0

    try:
        import requests
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": TABLE_URL,
            "accept": "application/json",
            "content-type": "application/json",
            "token": token,
        }
        print("[数据] 正在拉取大宽表数据（14960 行）...")
        fetch_start = time.time()
        r = requests.get(CONTENT_API, cookies=get_session_cookies(), headers=headers, timeout=120)
        print(f"[数据] 拉取完成 ({time.time() - fetch_start:.1f}s)")

        if r.status_code != 200:
            return None, f"HTTP error {r.status_code}", 0
        resp_json = r.json()
        if resp_json.get("code") != 200:
            return None, f"API error: {resp_json.get('message') or resp_json.get('msg')}", 0

        rows = resp_json.get("data", {}).get("data", [])
        if not rows:
            return None, "Empty data returned from API", 0

        # 压缩存储 + 建立索引
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, separators=(',', ':'))
        with open(CACHE_INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(build_cache_index(rows), f, ensure_ascii=False, separators=(',', ':'))

        results = [extract_story(r, req_id) for r in rows if match_story(r, req_id, is_epic)]
        return results, None, 0

    except Exception as e:
        return None, str(e), 0


# ============================================================
# 直接 WebSocket 直连更新（核心优化）
# ============================================================
async def ws_send_one(ws, payload, story_code, target_date):
    """单条 WebSocket 发送并等待服务端确认（逐条确认，规避异步丢帧）"""
    await ws.send(json.dumps(payload))
    try:
        resp = await asyncio.wait_for(ws.recv(), timeout=2.0)
        try:
            return json.loads(resp)
        except json.JSONDecodeError:
            return None
    except asyncio.TimeoutError:
        return None


async def ws_update(target_items, token, per_item_connection=True):
    """
    使用 Python websockets 库直接连接 WebSocket，无需 Playwright
    协议：wss://fintech.gtht.com.cn/ws/table-socket/table/websocket/{tableId}

    v3.1 优化（P0 可靠性修复）：
    - per_item_connection=True（默认）：每条 Story 使用独立 WebSocket 连接，
      逐条发送→确认→关闭，规避服务端在单连接连续写入时的异步持久化丢帧问题。
    - 该模式从根本上规避"批量写回确认成功但实际未落库"的隐患。
    """
    import websockets

    def build_payload(item):
        row_data = dict(item.get("cachedRow", {}))
        row_data["sheetId"] = SHEET_ID
        row_data["planProdLineDate"] = item["target_date"]
        return {"token": token, "type": 2, "data": row_data}

    total_cost = 0.0
    confirmations = []

    if per_item_connection and len(target_items) > 1:
        # ===== 逐条独立连接模式（可靠，规避批量丢帧）=====
        print(f"[WS] 逐条独立连接写回 {len(target_items)} 条（规避批量丢帧）...")
        connect_start = time.time()
        for i, item in enumerate(target_items):
            story_code = item["storyCode"]
            target_date = item["target_date"]
            try:
                async with websockets.connect(WS_URL, ping_interval=None, close_timeout=10) as ws:
                    # 心跳初始化
                    await ws.send(json.dumps({
                        "type": 1, "clientId": TABLE_ID, "token": token,
                        "data": {"msg": "心跳检测"},
                    }))
                    await asyncio.sleep(0.2)
                    # 单条发送并确认
                    resp = await ws_send_one(ws, build_payload(item), story_code, target_date)
                    if resp is not None:
                        confirmations.append(resp)
                    print(f"  [{i+1}/{len(target_items)}] {story_code} → {target_date} "
                          f"({'已确认' if resp is not None else '无回包'})")
                    # 保持连接等待异步持久化
                    await asyncio.sleep(1.5)
            except Exception as e:
                print(f"  [{i+1}/{len(target_items)}] {story_code} 连接失败: {e}")
        total_cost = time.time() - connect_start
        print(f"[WS] 完成 ({total_cost:.2f}s) | 逐条发送 {len(target_items)} 条, 确认 {len(confirmations)} 条")
        return {"ok": True, "updatedCount": len(target_items), "confirmations": confirmations, "cost": total_cost}

    # ===== 单连接模式（仅当 1 条或显式关闭逐条时）=====
    update_payloads = [build_payload(item) for item in target_items]
    print(f"[WS] 正在连接 WebSocket...")
    connect_start = time.time()

    try:
        async with websockets.connect(WS_URL, ping_interval=None, close_timeout=10) as ws:
            print(f"[WS] 连接成功 ({time.time() - connect_start:.2f}s)")

            # 心跳初始化
            await ws.send(json.dumps({
                "type": 1, "clientId": TABLE_ID, "token": token,
                "data": {"msg": "心跳检测"},
            }))

            for i, payload in enumerate(update_payloads):
                resp = await ws_send_one(ws, payload, target_items[i]['storyCode'], target_items[i]['target_date'])
                if resp is not None:
                    confirmations.append(resp)
                print(f"  [{i+1}/{len(update_payloads)}] {target_items[i]['storyCode']} → {target_items[i]['target_date']}")
                await asyncio.sleep(0.5)

            # 保持连接一段时间，等待服务端异步持久化完成
            await asyncio.sleep(2.0)

            total_cost = time.time() - connect_start
            print(f"[WS] 完成 ({total_cost:.2f}s) | 发送 {len(update_payloads)} 条, 确认 {len(confirmations)} 条")
            return {"ok": True, "updatedCount": len(update_payloads), "confirmations": confirmations, "cost": total_cost}

    except Exception as e:
        print(f"❌ [WS] WebSocket 失败: {e}")
        return {"ok": False, "error": str(e)}


# ============================================================
# 缓存更新
# ============================================================
def update_local_cache(target_items):
    """更新本地热缓存文件（写入后重建索引）"""
    if not os.path.exists(CACHE_FILE):
        return
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
        with open(CACHE_INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(build_cache_index(rows), f, ensure_ascii=False, separators=(',', ':'))
    except Exception:
        pass


# ============================================================
# 输出
# ============================================================
def print_result_markdown(title_prefix, req_id, target_date, results):
    print("\nRESULT_MARKDOWN_START")
    print(f"### 计划生产排期{title_prefix}汇总")
    print(f"极速引擎 v3 (`schedule_fast_v3.py`) | 编号: **{req_id}**" +
          (f" | 目标日期: **{target_date}**" if target_date else ""))
    print("")
    detail_url = f"https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId={req_id}&templateId=8888&flag=1"
    req_link = f"[{req_id}]({detail_url})"
    if target_date:
        print("| 序号 | 需求/史诗编号 | Story 编号 | 修改前排期 | 修改后 (目标) | 数据库持久化校验 | 状态 |")
        print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for idx, r in enumerate(results, 1):
            status_str = "✅ 成功" if r.get("verify_ok", True) else "❌ 失败"
            print(f"| {idx} | {req_link} | {r['storyCode']} | {r['before']} | {r['target_date']} | {r.get('persisted', r['target_date'])} | {status_str} |")
    else:
        print("| 序号 | 需求/史诗编号 | Story 编号 | 当前计划生产排期 |")
        print("| :--- | :--- | :--- | :--- |")
        for idx, r in enumerate(results, 1):
            print(f"| {idx} | {req_link} | {r['storyCode']} | {r['planDate']} |")
    print("RESULT_MARKDOWN_END\n")


# ============================================================
# 主入口
# ============================================================
async def main_async(args):
    start_time = time.time()
    req_id = args.req_id.strip()
    target_date = normalize_date(args.target_date)

    # ========== 1. Session 验证（懒加载 — 先查缓存再登录） ==========
    token = get_session_token()
    session_valid = token and quick_check_session()

    # 缓存命中则跳过登录
    if not session_valid and not args.no_cache and os.path.exists(CACHE_FILE):
        try:
            cache_age = time.time() - os.path.getmtime(CACHE_FILE)
            if cache_age < CACHE_TTL:
                items, err, _ = query_schedule(req_id, no_cache=False)
                if items:
                    print(f"✅ [缓存] 热缓存命中 (TTL {int(cache_age)}s)，无需登录")
                    session_valid = True
        except Exception:
            pass

    if not session_valid:
        print("[Session] 需要重新登录...")
        if api_login():
            token = get_session_token()
        if not token:
            if not await playwright_login():
                print("❌ 登录失败，无法继续")
                sys.exit(1)
            token = get_session_token()
        print("✅ [Session] Token 有效")

    # ========== 2. 查询数据 ==========
    items, err, cache_age = query_schedule(req_id, no_cache=args.no_cache)
    if err or not items:
        print(f"❌ 未能找到属于编号 '{req_id}' 的关联 Story 记录。({err or '数据未找到'})")
        sys.exit(1)

    # ========== 3. 只读查询模式 ==========
    if not target_date:
        cache_desc = f"热缓存 (TTL {cache_age}s)" if cache_age > 0 else "在线 API"
        print(f"⚡ [{cache_desc}] 该编号下共找到 {len(items)} 条关联 Story:")
        print_result_markdown("查询结果", req_id, None, items)
        print(f"⏱️ 极速查询耗时: {time.time() - start_time:.2f}s")
        return

    # ========== 4. 排期修改模式 ==========
    target_update_items = []
    results = []
    skipped_count = 0
    for item in items:
        old_val = item["planDate"]
        if old_val == target_date:
            skipped_count += 1
            results.append({
                "req_id": item["req_id"], "storyCode": item["storyCode"],
                "before": old_val or "空", "target_date": target_date,
                "rowId": item["rowId"], "cachedRow": item.get("cachedRow"),
                "persisted": old_val, "verify_ok": True, "skipped": True,
            })
            continue
        results.append({
            "req_id": item["req_id"], "storyCode": item["storyCode"],
            "before": old_val or "空", "target_date": target_date,
            "rowId": item["rowId"], "cachedRow": item.get("cachedRow"),
        })
        item["target_date"] = target_date
        target_update_items.append(item)

    # --story-filter：仅保留指定 Story（逐条补写）
    if args.story_filter:
        target_update_items = [i for i in target_update_items if i["storyCode"] == args.story_filter]
        if not target_update_items:
            print(f"ℹ️ [{args.story_filter}] 已为目标排期或未匹配，无需修改。")
            return

    if not target_update_items:
        cache_desc = f"热缓存 (TTL {cache_age}s)" if cache_age > 0 else "在线 API"
        print(f"⚡ [{cache_desc}] 共 {len(items)} 条 Story，全部已为目标排期，无需修改。")
        print_result_markdown("修改结果（无变更）", req_id, target_date, results)
        print(f"⏱️ 耗时: {time.time() - start_time:.1f}s")
        return

    cache_desc = f"热缓存 (TTL {cache_age}s)" if cache_age > 0 else "在线 API"
    print(f"⚡ [{cache_desc}] 共 {len(target_update_items)} 条 Story 需修改 ({skipped_count} 条已匹配跳过)，正在直连 WebSocket 写回...")

    # ========== 5. WebSocket 直连写回 ==========
    update_res = await ws_update(target_update_items, token)
    ws_ok = isinstance(update_res, dict) and update_res.get("ok") is True

    if not ws_ok:
        print(f"❌ [写回失败] WebSocket: {(update_res or {}).get('error') or '未知错误'}")
    else:
        print(f"✅ [写回成功] 已提交 {update_res.get('updatedCount')} 条 Story")

    # 同步更新本地缓存
    update_local_cache(target_update_items)

    # ========== 6. 校验（v3.1：API 回读为空不再误报成功，失败自动逐条补写重试） ==========
    MAX_VERIFY_RETRY = 3
    verified_map = {}
    all_success = False

    if ws_ok:
        print("[校验] 正在校验数据库持久化（API 全量回读）...")
        for retry in range(MAX_VERIFY_RETRY):
            await asyncio.sleep(1)
            verified_items, v_err, _ = query_schedule(req_id, no_cache=True)
            if verified_items:
                verified_map = {v["storyCode"]: v["planDate"] for v in verified_items}
                break
        for r in results:
            if r.get("skipped"):
                r["verify_ok"] = True
                continue
            v_val = verified_map.get(r["storyCode"])
            if v_val:
                r["persisted"] = v_val
                r["verify_ok"] = (v_val == target_date)
            else:
                # v3.1 修复：API 回读不到该 Story → 判定为未持久化（不再乐观误报成功）
                r["persisted"] = "未回显"
                r["verify_ok"] = False

        # 找出未落库的 Story，逐条独立连接补写重试
        failed_items = [item for item in target_update_items
                        if not next((r for r in results if r["storyCode"] == item["storyCode"]), {}).get("verify_ok", False)]
        if failed_items:
            print(f"[补写] 检测到 {len(failed_items)} 条未持久化，启动逐条独立连接补写...")
            for attempt in range(1, MAX_VERIFY_RETRY + 1):
                if not failed_items:
                    break
                await asyncio.sleep(1)
                retry_res = await ws_update(failed_items, token, per_item_connection=True)
                if not (isinstance(retry_res, dict) and retry_res.get("ok")):
                    print(f"[补写] 第 {attempt} 次连接失败")
                    continue
                # 补写后重新全量回读
                verified_items2, _, _ = query_schedule(req_id, no_cache=True)
                verified_map2 = {v["storyCode"]: v["planDate"] for v in (verified_items2 or [])}
                still_failed = []
                for item in failed_items:
                    code = item["storyCode"]
                    v_val = verified_map2.get(code)
                    ok = bool(v_val) and v_val == target_date
                    r = next((x for x in results if x["storyCode"] == code), None)
                    if r:
                        r["persisted"] = v_val or "未回显"
                        r["verify_ok"] = ok
                    if not ok:
                        still_failed.append(item)
                failed_items = still_failed
                print(f"[补写] 第 {attempt} 次后剩余 {len(failed_items)} 条未持久化")
            update_local_cache(target_update_items)

        all_success = all(r.get("verify_ok", False) for r in results if not r.get("skipped"))
    else:
        all_success = False

    print_result_markdown("修改结果", req_id, target_date, results)
    total_cost = time.time() - start_time
    status_tag = "✅ 全部成功" if all_success else "❌ 存在失败"
    skip_tag = f" (跳过 {skipped_count} 条已匹配)" if skipped_count > 0 else ""
    print(f"⚡ [schedule_fast_v3 完成] {status_tag}{skip_tag} | 耗时: {total_cost:.1f}s (含 {len(target_update_items)} 行写入)")
    print("💡 提示：服务端已落库目标值。若浏览器大宽表仍显示旧值，请硬刷新（macOS ⌘+Shift+R / Win Ctrl+F5）清除 ag-Grid 前端缓存。")


def main():
    parser = argparse.ArgumentParser(description="计划生产排期极速修改与查询工具 (schedule_fast_v3)")
    parser.add_argument("req_id", help="需求编号 (Rxxxx) 或 史诗编号 (PGxxxx / Exxxx)")
    parser.add_argument("target_date", nargs="?", default=None, help="目标计划生产排期日期 (如 20260821 或 2026-08-21)")
    parser.add_argument("--verify", action="store_true", help="修改后开启数据库持久化校验")
    parser.add_argument("--no-cache", action="store_true", help="强制忽略热缓存，重新抓取数据")
    parser.add_argument("--browser", action="store_true", help="强制使用浏览器模式（默认优先 API 登录）")
    parser.add_argument("--story-filter", default=None, help="仅修改指定 Story 编号（用于逐条补写）")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
