#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
req_query.py — 需求查询（需求管理列表页）
============================================
访问金融科技平台，通过右上角全局搜索框查询需求编号，
提取核心需求要素并输出，同时在 headed 模式下打开需求详情页。
支持 session 复用，避免重复登录。

优化点:
  - 异步 Playwright，支持并行查询（大宽表 + 详情页同时执行）
  - 智能等待替代固定 time.sleep

用法:
    .venv/bin/python req_query.py <需求编号> [--headed]
    .venv/bin/python req_query.py R2605250074 --headed

依赖: playwright
      虚拟环境 .venv/
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
import requests
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ============================================================
# 配置
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)

def get_hardware_key():
    identifiers = []
    
    # 1. Try to get macOS Hardware UUID
    if sys.platform == "darwin":
        try:
            output = subprocess.check_output("ioreg -rd1 -c IOPlatformExpertDevice", shell=True)
            match = re.search(r'"IOPlatformUUID"\s*=\s*"(.*?)"', output.decode('utf-8'))
            if match:
                identifiers.append(match.group(1).strip())
        except Exception:
            pass
            
    # 2. Try to get MAC Address
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

# 加载凭证配置 (config.json)
USERNAME = ""
PASSWORD = ""
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
                u = creds.get("username", "")
                
                # 支持明文密码或加密后的密码
                p_plain = creds.get("password", "")
                p_enc = creds.get("password_encrypted", "")
                
                # 如果是占位符，忽略它
                if u == "YOUR_USERNAME":
                    u = ""
                if p_plain in ("YOUR_PASSWORD", "YOUR_PLAIN_PASSWORD"):
                    p_plain = ""
                
                p_val = ""
                if p_plain:
                    p_val = p_plain
                elif p_enc:
                    decrypted = decrypt_password(p_enc)
                    if decrypted:
                        p_val = decrypted
                    
                if u and p_val:
                    USERNAME = u
                    PASSWORD = p_val
                    break
        except Exception:
            pass

if not USERNAME or not PASSWORD:
    print("错误: 未在 config.json 中配置有效的用户名或密码，或者您的密码无法在当前电脑上解密！", file=sys.stderr)
    print("如果您是从其他电脑复制的技能包，或者更换了电脑，请重新加密您的密码：", file=sys.stderr)
    print("  python scripts/encrypt_pwd.py", file=sys.stderr)
    print("配置文件搜索路径：", file=sys.stderr)
    for p in config_paths:
        print(f"  - {os.path.abspath(p)}", file=sys.stderr)
    sys.exit(1)

# 加载 Session 文件 (优先使用已存在的路径，默认在当前工作目录或 Skill 根目录下)
session_paths = [
    os.path.join(os.getcwd(), ".fintech_session.json"),
    os.path.join(SKILL_ROOT, ".fintech_session.json"),
    os.path.join(SCRIPT_DIR, ".fintech_session.json"),
]
SESSION_FILE = session_paths[0]
for p in session_paths:
    if os.path.exists(p):
        SESSION_FILE = p
        break

LOGIN_URL = "https://fintech.gtht.com.cn/kjpt/user/login"
TARGET_URL = "https://fintech.gtht.com.cn/kjpt/DemandManage/main"
DETAIL_URL_TEMPL = "https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId={}&templateId=8888&flag=1"
WIDE_TABLE_URL = (
    "https://fintech.gtht.com.cn/kjpt/OnlineGrid"
    "?tableId=1597051499572236288"
    "&tableName=%E4%BA%A4%E6%98%93%E7%BB%93%E7%AE%97%E6%A0%B8%E5%BF%83%E7%B3%BB%E7%BB%9F%E9%9C%80%E6%B1%82%E9%9B%86%E5%90%88"
)

# 全局搜索页表格列索引（基于 /kjpt/globalSearch 实际 ant-table 结构）
GS_COL_INDEX = {
    "id": 0,
    "title": 1,
    "level": 2,
    "requester": 3,
    "dept": 4,
    "expect_date": 5,
    "handler": 6,
    "product": 7,
    "module": 8,
    "type": 9,
    "status": 10,
    "oa_status": 11,
}


# ============================================================
# 工具函数（纯数据处理，无需异步）
# ============================================================
def _clean(s):
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


# ============================================================
# 登录（Session 复用）
# ============================================================
# 登录（Session 复用）
# ============================================================
async def ensure_login(context, page):
    """确保登录态有效。已登录则跳过，未登录则执行登录并保存 session"""
    print("[登录]", end=" ", flush=True)

    try:
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=15000)
        if "login" not in page.url.lower():
            print("已有登录态，跳过")
            return
    except Exception:
        pass

    print("登录中...", end=" ", flush=True)
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_selector('input[placeholder*="工号"]', timeout=8000)
    await page.locator('input[placeholder*="工号"]').fill(USERNAME)
    await page.locator('input[placeholder*="密码"]').fill(PASSWORD)
    await page.locator('button:has-text("Submit"), button:has-text("提 交")').first.click()
    try:
        await page.wait_for_selector('input[placeholder*="搜索需求"]', timeout=15000)
    except Exception:
        await page.wait_for_load_state("domcontentloaded", timeout=15000)

    try:
        await context.storage_state(path=SESSION_FILE)
        print("完成（session 已保存）")
    except Exception as e:
        print(f"完成（session 保存失败: {e}）")


# ============================================================
# 搜索需求（通过顶部全局搜索框）
# ============================================================
async def search_demand(page, demand_id):
    """
    通过页面右上角的全局搜索框输入需求编号并按 Enter，
    跳转到 /kjpt/globalSearch 页面提取搜索结果。
    """
    print(f"[搜索] 需求编号: {demand_id}")

    # 确保在需求管理列表页（有顶部搜索框）
    if "DemandManage/main" not in page.url and "globalSearch" not in page.url:
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_selector('input[placeholder*="搜索需求"]', timeout=10000)

    # 定位顶部全局搜索框
    top_search = page.locator('input[placeholder*="搜索需求"]')
    await top_search.click()
    await top_search.fill("")
    await top_search.fill(demand_id)

    # 按 Enter 触发搜索，跳转到 /kjpt/globalSearch
    await top_search.press("Enter")
    print("[搜索] 已按 Enter，等待全局搜索页面...")

    # 等待跳转到全局搜索页（智能等待替代轮询）
    try:
        await page.wait_for_url("**/globalSearch**", timeout=15000)
    except PWTimeout:
        print(f"[搜索] 未跳转到全局搜索页，当前 URL: {page.url}")
        return []

    # 等待表格行加载（智能等待：第一行第一列有内容）
    try:
        await page.wait_for_function("""() => {
            const rows = document.querySelectorAll('.ant-table-tbody .ant-table-row');
            if (rows.length === 0) return false;
            const cells = rows[0].querySelectorAll('td');
            return cells.length >= 2 && cells[0].textContent?.trim();
        }""", timeout=15000)
    except PWTimeout:
        print("[搜索] 等待表格超时")

    # 提取所有行数据
    rows_data = await page.evaluate("""() => {
        const rows = document.querySelectorAll('.ant-table-tbody .ant-table-row');
        return Array.from(rows).map((row, idx) => {
            const cells = row.querySelectorAll('td');
            return {
                idx,
                cellCount: cells.length,
                texts: Array.from(cells).map(td => td.textContent?.trim() || ""),
            };
        });
    }""")

    # 前端精确匹配：编号列（索引0）完全匹配
    matched = []
    for r in rows_data:
        texts = r["texts"]
        if len(texts) > GS_COL_INDEX["id"]:
            if texts[GS_COL_INDEX["id"]].strip() == demand_id:
                matched.append(r)

    print(f"[搜索] 精确匹配: {len(matched)} 行")
    return matched


# ============================================================
# 打开详情页并提取 Story 列表
# ============================================================
async def open_detail_page(page, demand_id):
    """
    打开需求详情页，返回 (stories_data, col_map)。
    """
    detail_url = DETAIL_URL_TEMPL.format(demand_id)
    print(f"[详情] 打开: {detail_url}")
    await page.goto(detail_url, wait_until="domcontentloaded", timeout=60000)
    print(f"[详情] 当前 URL: {page.url}")

    # 等待 Story 表格加载（智能等待：表头 + 数据行都要就绪）
    try:
        await page.wait_for_function("""() => {
            const tables = document.querySelectorAll('.ant-table');
            if (tables.length === 0) return false;
            const firstHeader = tables[0].querySelector('.ant-table-thead');
            if (!firstHeader) return false;
            if (!firstHeader.textContent.includes('Story编号')) return false;

            // 1. 检查是否有数据行且有具体内容（排除骨架屏）
            const rows = tables[0].querySelectorAll('.ant-table-tbody .ant-table-row');
            if (rows.length > 0) {
                const cells = rows[0].querySelectorAll('td');
                if (cells.length > 1 && cells[1].textContent?.trim()) {
                    return true;
                }
            }

            // 2. 检查是否有空数据占位，且非正在加载状态
            const loading = document.querySelector('.ant-spin-spinning') || document.querySelector('.ant-table-loading');
            const placeholder = tables[0].querySelector('.ant-table-placeholder') || document.querySelector('.ant-empty');
            if (placeholder && !loading) {
                return true;
            }
            return false;
        }""", timeout=20000)
    except PWTimeout:
        print("[详情] 等待 Story 表格超时")

    # 提取 Story 表格数据（含表头映射）
    result = await page.evaluate("""() => {
        const tables = document.querySelectorAll('.ant-table');
        if (tables.length === 0) return { stories: [], colMap: {} };

        let storyTable = null;
        for (const table of tables) {
            const header = table.querySelector('.ant-table-thead');
            if (header && header.textContent.includes('Story编号')) {
                storyTable = table;
                break;
            }
        }
        if (!storyTable) return { stories: [], colMap: {} };

        const headerCells = storyTable.querySelectorAll('.ant-table-thead th');
        const colMap = {};
        Array.from(headerCells).forEach((th, idx) => {
            const name = th.textContent?.trim() || '';
            if (name) colMap[name] = idx;
        });

        const rows = storyTable.querySelectorAll('.ant-table-tbody .ant-table-row');
        const stories = Array.from(rows).map(row => {
            const cells = row.querySelectorAll('td');
            return Array.from(cells).map(td => td.textContent?.trim() || '');
        });

        return { stories, colMap };
    }""")

    stories_data = result.get("stories", [])
    col_map = result.get("colMap", {})
    print(f"[详情] Story 数量: {len(stories_data)}")
    return stories_data, col_map


# ============================================================
# 根据史诗编号查询关联需求编号列表
# ============================================================
def get_demands_by_epic_api(epic_id):
    """
    尝试通过直接调用 HTTP API 接口来获取史诗关联的需求列表。
    """
    print(f"[API] 正在尝试通过 API 查询史诗 {epic_id} 关联的需求列表...")
    
    cookies = {}
    token = None
    if os.path.exists(SESSION_FILE):
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
            print(f"[API] 读取 Session 文件失败: {e}", file=sys.stderr)
            
    if not cookies or not token:
        print("[API] 缺少 Session 缓存，退回浏览器模式", file=sys.stderr)
        return None
        
    try:
        CONTENT_URL = "https://fintech.gtht.com.cn/api/table-service/table/row/getSheetContent?sheetId=1597051509256884224"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://fintech.gtht.com.cn/kjpt/OnlineGrid?tableId=1597051499572236288",
            "accept": "application/json",
            "content-type": "application/json",
        }
        if token:
            headers["token"] = token
            
        r = requests.get(CONTENT_URL, cookies=cookies, headers=headers, timeout=30)
        if r.status_code != 200:
            print(f"[API] 请求失败，HTTP 状态码: {r.status_code}", file=sys.stderr)
            return None
            
        resp_json = r.json()
        if resp_json.get("code") != 200:
            print(f"[API] 接口返回错误: {resp_json.get('msg')}", file=sys.stderr)
            return None
            
        raw_rows = resp_json.get("data", {}).get("data", [])
        
        demands = set()
        epic_upper = epic_id.upper()
        for row in raw_rows:
            epic_concat = row.get("epicConcat", "") or ""
            if epic_upper in str(epic_concat).upper():
                d_id = row.get("demandId", "")
                if d_id and d_id.startswith("R"):
                    demands.add(d_id)
        return sorted(list(demands))
    except Exception as e:
        print(f"[API] 接口获取数据异常: {e}", file=sys.stderr)
        return None

async def get_demands_by_epic_playwright(epic_id):
    """
    使用 Playwright 登录并访问大宽表，搜索 Epic ID，提取关联的 Demand ID 列表
    """
    print(f"[Playwright] 正在启动浏览器查询史诗 {epic_id} 关联的需求列表...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = await browser.new_context(
            storage_state=SESSION_FILE if os.path.exists(SESSION_FILE) else None,
            viewport={"width": 1440, "height": 900},
            locale="zh-CN"
        )
        page = await context.new_page()
        try:
            await ensure_login(context, page)
            await page.goto(WIDE_TABLE_URL, wait_until="domcontentloaded", timeout=60000)
            
            await page.wait_for_selector('.ag-root', timeout=30000)
            await page.wait_for_selector('#filter-text-box', state="visible", timeout=10000)
            
            search_box = page.locator('#filter-text-box')
            await search_box.click()
            await search_box.fill("")
            await search_box.type(epic_id, delay=20)
            await search_box.press("Enter")
            
            await asyncio.sleep(2.0)
            
            try:
                await page.evaluate("""() => {
                    document.querySelectorAll('button').forEach(b => {
                        const txt = b.textContent?.trim();
                        if (txt === '一键展开') b.click();
                    });
                }""")
                await asyncio.sleep(1.5)
            except Exception:
                pass
                
            demands = await page.evaluate("""() => {
                const headerCells = document.querySelectorAll('.ag-header-cell[col-id]');
                const nameToColId = {};
                headerCells.forEach(cell => {
                    const colId = cell.getAttribute('col-id');
                    const label = cell.querySelector('.ag-header-cell-label');
                    const text = label ? label.textContent.trim() : (cell.textContent.trim() || '');
                    if (colId && text) {
                        nameToColId[text] = colId;
                    }
                });

                const dColId = nameToColId['需求编号'];
                if (!dColId) return [];

                const dataRows = document.querySelectorAll('.ag-row:not(.ag-row-group)');
                const demandsSet = new Set();
                dataRows.forEach(row => {
                    const cells = row.querySelectorAll('.ag-cell[col-id]');
                    cells.forEach(cell => {
                        const cid = cell.getAttribute('col-id');
                        if (cid === dColId) {
                            const val = cell.textContent.trim();
                            if (val && val.startsWith('R')) {
                                demandsSet.add(val);
                            }
                        }
                    });
                });
                return Array.from(demandsSet);
            }""")
            
            await context.storage_state(path=SESSION_FILE)
            return sorted(list(demands))
        except Exception as e:
            print(f"[Playwright] 查询史诗关联需求失败: {e}", file=sys.stderr)
            return []
        finally:
            await browser.close()

async def get_demands_by_epic(epic_id):
    try:
        res = get_demands_by_epic_api(epic_id)
        if res is not None:
            return res
    except Exception as e:
        print(f"[API] API 接口报错: {e}，将采用浏览器模式...", file=sys.stderr)
        
    return await get_demands_by_epic_playwright(epic_id)


# ============================================================
# 查询大宽表（计划生产排期 + 备注）
# ============================================================
async def query_wide_table(page, demand_id):
    """
    从大宽表（交易结算核心系统需求集合）查询指定需求的计划生产排期和备注。
    返回 dict: {系统名: {"plan_date": "...", "remark": "..."}}
    """
    print(f"[大宽表] 查询: {demand_id}")

    try:
        await page.goto(WIDE_TABLE_URL, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        print(f"[大宽表] 页面打开失败: {e}")
        return {}

    # 等待 AG Grid 渲染（智能等待替代轮询）
    try:
        await page.wait_for_selector('.ag-root', timeout=30000)
        await page.wait_for_selector('#filter-text-box', state="visible", timeout=10000)
    except PWTimeout:
        print("[大宽表] 等待 AG Grid 超时")
        return {}

    # 搜索（使用 #filter-text-box，逐字符输入避免自动清空）
    try:
        search_box = page.locator('#filter-text-box')
        await search_box.click()
        await search_box.fill("")
        await search_box.type(demand_id, delay=20)
        await search_box.press("Enter")
        # 智能等待过滤生效
        try:
            await page.wait_for_function("""() => {
                const bar = document.querySelector('.ag-status-bar') || document.querySelector('[ref="statusBar"]');
                return bar && bar.innerText.includes('过滤后数据总数');
            }""", timeout=5000)
        except PWTimeout:
            await asyncio.sleep(1.5)
    except Exception as e:
        print(f"[大宽表] 搜索失败: {e}")
        return {}

    # 获取过滤出来的行数，如果为 0 则直接退出，不执行展开和提取，这可以节省大量时间
    filtered_count = await page.evaluate("""() => {
        const bar = document.querySelector('.ag-status-bar') || document.querySelector('[ref="statusBar"]');
        if (!bar) return -1;
        const text = bar.innerText || "";
        const parts = text.split("过滤后数据总数");
        if (parts.length > 1) {
            const match = parts[1].match(/\\d+/);
            if (match) return parseInt(match[0], 10);
        }
        return -1;
    }""")
    print(f"[大宽表] 过滤行数: {filtered_count}")
    if filtered_count == 0:
        return {}

    # 一键展开分组
    try:
        await page.evaluate("""() => {
            document.querySelectorAll('button').forEach(b => {
                const txt = b.textContent?.trim();
                if (txt === '一键展开') b.click();
            });
        }""")
        # 智能等待展开渲染完成
        try:
            await page.wait_for_function("""() => {
                return document.querySelectorAll('.ag-row:not(.ag-row-group)').length > 0;
            }""", timeout=3000)
        except PWTimeout:
            await asyncio.sleep(0.5)
    except Exception:
        pass

    # 提取数据
    result = await page.evaluate("""(demandId) => {
        const headerCells = document.querySelectorAll('.ag-header-cell[col-id]');
        const colIdToName = {};
        const nameToColId = {};
        headerCells.forEach(cell => {
            const colId = cell.getAttribute('col-id');
            const label = cell.querySelector('.ag-header-cell-label');
            const text = label ? label.textContent.trim() : (cell.textContent.trim() || '');
            if (colId && text) {
                colIdToName[colId] = text;
                nameToColId[text] = colId;
            }
        });

        const neededCols = ['需求编号', 'Story系统', '计划生产排期', '备注'];
        const found = neededCols.filter(c => nameToColId[c]);
        if (found.length < 2) {
            return { error: true, foundNames: Object.keys(nameToColId).slice(0, 20), neededCols };
        }

        const dataRows = document.querySelectorAll('.ag-row:not(.ag-row-group)');
        const records = [];

        dataRows.forEach(row => {
            const cells = row.querySelectorAll('.ag-cell[col-id]');
            const rowData = {};
            cells.forEach(cell => {
                const cid = cell.getAttribute('col-id');
                rowData[cid] = cell.textContent.trim();
            });

            const dColId = nameToColId['需求编号'];
            const rowDid = dColId ? (rowData[dColId] || '') : '';
            if (rowDid !== demandId) return;

            const sColId = nameToColId['Story系统'];
            const pColId = nameToColId['计划生产排期'];
            const rColId = nameToColId['备注'];

            records.push({
                system: sColId ? (rowData[sColId] || '') : '',
                planDate: pColId ? (rowData[pColId] || '') : '',
                remark: rColId ? (rowData[rColId] || '') : '',
            });
        });

        return { records, foundColumns: found };
    }""", demand_id)

    if result.get("error"):
        print(f"[大宽表] 列匹配不足，已找到: {result.get('foundNames', [])}")
        return {}

    lookup = {}
    for item in result.get("records", []):
        sys = item.get("system", "")
        if sys:
            lookup[sys] = {
                "plan_date": item.get("planDate", ""),
                "remark": item.get("remark", ""),
            }

    print(f"[大宽表] 找到 {len(lookup)} 条系统记录: {list(lookup.keys())}")
    return lookup


# 详情页 Story 表格列索引（fallback，动态映射优先）
STORY_COL = {
    "id": 1,
    "name": 2,
    "it_status": 3,
    "status": 4,
    "system": 5,
    "dev_effort": 7,
    "sit_effort": 8,
    "uat_effort": 9,
    "dev_finish": 10,
    "story_delivery": 11,
    "dev_evaluator": 12,
    "dev_owner": 13,
    "sit_owner": 14,
    "uat_owner": 15,
    "schedule": 17,
    "release_date": 18,
}

# Story 表格中 th 列名 → 字段名映射
STORY_HEADER_MAP = {
    "Story编号": "id",
    "Story名称": "name",
    "IT评估状态": "it_status",
    "Story状态": "status",
    "所属系统": "system",
    "开发工作量": "dev_effort",
    "SIT测试工作量": "sit_effort",
    "UAT测试工作量": "uat_effort",
    "预计开发完成时间": "dev_finish",
    "Story预计交付验收时间": "story_delivery",
    "开发实际评估人": "dev_evaluator",
    "开发负责人": "dev_owner",
    "SIT测试负责人": "sit_owner",
    "UAT测试负责人": "uat_owner",
    "版本排期": "schedule",
    "版本计划发布日期": "release_date",
}


# ============================================================
# 提取核心需求要素
# ============================================================
def extract_demand_info(matched_rows, demand_id):
    if not matched_rows:
        return None

    row = matched_rows[0]
    texts = row["texts"]

    def get_col(name):
        idx = GS_COL_INDEX.get(name)
        if idx is not None and idx < len(texts):
            return _clean(texts[idx])
        return ""

    return {
        "编号": demand_id,
        "标题": get_col("title"),
        "级别": get_col("level"),
        "提出人": get_col("requester"),
        "提出部门": get_col("dept"),
        "期望上线时间": get_col("expect_date"),
        "受理人": get_col("handler"),
        "状态": get_col("status"),
        "OA状态": get_col("oa_status"),
    }


# ============================================================
# 格式化输出
# ============================================================
def _build_col_index(col_map):
    """根据表头列名动态构建字段名 → td 索引映射"""
    result = {}
    for header_text, th_idx in col_map.items():
        field_name = None
        for key, val in STORY_HEADER_MAP.items():
            if key in header_text or header_text in key:
                field_name = val
                break
        if field_name:
            result[field_name] = th_idx
    return result


def _match_wide_table(system_name, wide_table_data):
    """根据系统名模糊匹配大宽表数据"""
    if not wide_table_data or not system_name:
        return None
    for wt_sys, wt_data in wide_table_data.items():
        if system_name in wt_sys or wt_sys in system_name:
            return wt_data
    return None


def format_demand(info, stories=None, col_map=None, wide_table_data=None):
    """格式化核心需求要素为对话窗口输出"""
    if not info:
        return "**需求查询　|　未找到匹配结果**\n"

    lines = []
    lines.append(f"**需求查询　|　{info['编号']}**")
    lines.append("")

    lines.append(f"　　**标题**：{info['标题']}")
    lines.append(f"　　**级别**：{info['级别']}")
    lines.append(f"　　**状态**：{info['状态']}")
    lines.append(f"　　**OA状态**：{info['OA状态']}")
    lines.append("")

    lines.append(f"　　**提出人**：{info['提出人']}")
    lines.append(f"　　**提出部门**：{info['提出部门']}")
    lines.append(f"　　**受理人**：{info['受理人']}")
    lines.append(f"　　**期望上线时间**：{info['期望上线时间']}")

    if stories is not None:
        ci = _build_col_index(col_map) if col_map else STORY_COL

        lines.append("")
        lines.append(f"　　**关联 Story（{len(stories)} 条）**")
        if stories:
            for i, s in enumerate(stories, 1):
                def scol(name):
                    idx = ci.get(name)
                    if idx is not None and idx < len(s):
                        return _clean(s[idx])
                    return ""

                story_system = scol('system')

                wt = _match_wide_table(story_system, wide_table_data)
                plan_date = wt.get("plan_date", "") if wt else ""
                remark = wt.get("remark", "") if wt else ""

                lines.append(f"　　　　**{i}. {scol('id')}** — {scol('name')}")
                lines.append(f"　　　　　　状态：{scol('status')} | IT评估：{scol('it_status')}")

                sys_parts = [f"系统：{story_system}"]
                sched = scol('schedule')
                if sched:
                    sys_parts.append(f"工程排期：{sched}")
                if plan_date:
                    sys_parts.append(f"计划生产排期：{plan_date}")
                lines.append(f"　　　　　　{' | '.join(sys_parts)}")

                lines.append(f"　　　　　　开发负责人：{scol('dev_owner')} | SIT负责人：{scol('sit_owner')} | UAT负责人：{scol('uat_owner')}")
                lines.append(f"　　　　　　计划交付：{scol('story_delivery')} | 发布日期：{scol('release_date')}")

                if remark:
                    lines.append(f"　　　　　　备注：{remark}")

                lines.append("")
        else:
            lines.append("　　　　（无关联 Story）")
            lines.append("")

    lines.append(f"　　**详情页**：{DETAIL_URL_TEMPL.format(info['编号'])}")

    return "\n".join(lines)


# ============================================================
# 主函数（异步）
# ============================================================
async def run(demand_id, headed, output):
    """异步主流程"""

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not headed,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            storage_state=SESSION_FILE if os.path.exists(SESSION_FILE) else None,
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = await context.new_page()

        try:
            await ensure_login(context, page)

            # 步骤1: 全局搜索 → 提取核心要素
            matched = await search_demand(page, demand_id)
            info = extract_demand_info(matched, demand_id)

            if info:
                # 步骤2+3 并行: 大宽表查询 + 详情页 Story 提取
                print("[并行] 同时查询大宽表和详情页...")
                page2 = await context.new_page()

                wt_task = asyncio.create_task(query_wide_table(page2, demand_id))
                detail_task = asyncio.create_task(open_detail_page(page, demand_id))

                wide_table_data, (stories, col_map) = await asyncio.gather(wt_task, detail_task)

                await page2.close()
            else:
                wide_table_data = {}
                stories, col_map = [], {}

            # 步骤4: 格式化输出
            output_text = format_demand(info, stories, col_map, wide_table_data)
            print("\n" + "=" * 60)
            print(output_text)
            print("=" * 60)

            # 写文件
            if output:
                os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
                with open(output, "w", encoding="utf-8") as f:
                    f.write(output_text)
                    f.write("\n")
                print(f"\n结果已写入: {output}")

            # headed 模式下保持详情页打开
            if headed and info:
                screenshot_path = os.path.join(SCRIPT_DIR, f"req_query_{demand_id}.png")
                await page.screenshot(path=screenshot_path, full_page=False)
                print(f"[截图] 已保存: {screenshot_path}")
                print("\n[提示] 详情页已打开，按 Enter 关闭浏览器...")
                try:
                    # asyncio 环境下用 loop.run_in_executor 避免阻塞
                    await asyncio.get_event_loop().run_in_executor(None, input)
                except EOFError:
                    pass

        except Exception as e:
            print(f"\n执行失败: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            try:
                await context.storage_state(path=SESSION_FILE)
            except Exception:
                pass
            await browser.close()


async def run_epic(epic_id):
    demands = await get_demands_by_epic(epic_id)
    print("EPIC_DEMANDS:" + " ".join(demands))

def main():
    parser = argparse.ArgumentParser(description="需求查询 — 金融科技平台（异步优化版）")
    parser.add_argument("demand_id", help="需求编号（如 R2605250074）或史诗编号（如 PG202204-0236）")
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口并打开详情页")
    parser.add_argument("--output", "-o", help="输出文件路径（默认输出到对话）")
    parser.add_argument("--epic", action="store_true", help="按史诗编号进行查询获取关联需求列表")
    args = parser.parse_args()

    demand_id = args.demand_id.strip().upper()
    if not demand_id:
        print("错误：请输入需求编号或史诗编号")
        sys.exit(1)

    print(f"\n{'='*50}")
    print(f"  需求查询（异步版）")
    print(f"  编号: {demand_id}")
    print(f"{'='*50}")

    is_epic = args.epic or demand_id.startswith("PG") or demand_id.startswith("E")
    if is_epic:
        asyncio.run(run_epic(demand_id))
    else:
        asyncio.run(run(demand_id, args.headed, args.output))


if __name__ == "__main__":
    main()
