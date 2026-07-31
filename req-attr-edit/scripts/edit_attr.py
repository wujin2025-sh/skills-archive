#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
edit_attr.py — 修改需求属性要素（支持需求编号/史诗编号，支持普通属性与自定义标签）
===================================================
用法:
    .venv/bin/python edit_attr.py <需求编号/史诗编号> <字段名> <目标值> [--headed]
    
    示例：
    .venv/bin/python edit_attr.py R2606160037 重点关注 是
    .venv/bin/python edit_attr.py R2607090122 需求自定义标签 CX-信用-两融 --headed
    .venv/bin/python edit_attr.py PG202204-0267 重点关注 是
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
# 配置与凭证加载
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)

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
        else:
            return None
    except Exception:
        return None

# 搜索 config.json 路径
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
                p_plain = creds.get("password", "")
                p_enc = creds.get("password_encrypted", "")
                
                if u == "YOUR_USERNAME":
                    u = ""
                
                p_val = ""
                if p_plain and p_plain not in ("YOUR_PASSWORD", "YOUR_PLAIN_PASSWORD"):
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
    print("错误: 未在 config.json 中配置有效的用户名或密码！", file=sys.stderr)
    sys.exit(1)

# Session 文件路径
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
DETAIL_URL_TEMPL = "https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId={}&templateId=8888&flag=1"
CONTENT_URL = "https://fintech.gtht.com.cn/api/table-service/table/row/getSheetContent?sheetId=1597051509256884224"

# ============================================================
# API 方式获取史诗关联的需求 ID
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

def fetch_data_via_api(cookies, token):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://fintech.gtht.com.cn/kjpt/OnlineGrid?tableId=1597051499572236288",
        "accept": "application/json",
        "content-type": "application/json",
    }
    if token:
        headers["token"] = token
    
    r = requests.get(CONTENT_URL, cookies=cookies, headers=headers, timeout=60)
    if r.status_code != 200:
        raise ValueError(f"HTTP 状态码错误: {r.status_code}")
    
    resp_json = r.json()
    if resp_json.get("code") != 200:
        raise ValueError(f"API 返回错误: {resp_json.get('message') or resp_json.get('msg')}")
        
    rows = resp_json.get("data", {}).get("data", [])
    return rows

def get_demands_by_epic(epic_id, cookies, token):
    """根据史诗编号获取关联的需求 ID 列表 (通过精准的史诗API检索)"""
    try:
        print(f"[API] 正在通过史诗管理接口获取史诗 {epic_id} 关联的需求...")
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
        }
        if token:
            headers["token"] = token
            
        # 1. 获取史诗内部 ID
        LIST_URL = "https://fintech.gtht.com.cn/api/multi-project-collaboration-service/kjptProjectCollaborationEpic/listAllByExamples"
        list_payload = {
            "current": 1,
            "size": 10,
            "searchKeyWords": epic_id
        }
        r = requests.post(LIST_URL, cookies=cookies, headers=headers, json=list_payload, timeout=60)
        if r.status_code != 200:
            raise ValueError(f"查询史诗列表 HTTP 状态码错误: {r.status_code}")
            
        records = r.json().get("data", {}).get("records", [])
        epic_record = None
        for rec in records:
            if rec.get("code") == epic_id:
                epic_record = rec
                break
                
        if not epic_record:
            if records:
                epic_record = records[0]
                
        if not epic_record:
            print(f"[API] 警告: 未找到史诗 {epic_id}")
            return []
            
        epic_internal_id = epic_record["id"]
        print(f"[API] 史诗 {epic_id} 的内部ID为: {epic_internal_id}")
        
        # 2. 查询此史诗关联的全部需求
        DEMAND_URL = "https://fintech.gtht.com.cn/api/demand-service/demandsub/list"
        demand_payload = {
            "currentPage": 1,
            "pageSize": 500,
            "epicIds": epic_internal_id,
            "companyId": "comp01"
        }
        r2 = requests.post(DEMAND_URL, cookies=cookies, headers=headers, json=demand_payload, timeout=60)
        if r2.status_code != 200:
            raise ValueError(f"查询关联需求列表 HTTP 状态码错误: {r2.status_code}")
            
        demand_records = r2.json().get("data", {}).get("records", [])
        demand_ids = [rec["demandId"].strip() for rec in demand_records if rec.get("demandId")]
        
        return sorted(list(set(demand_ids)))
    except Exception as e:
        print(f"[API] 获取史诗需求发生异常: {e}")
        try:
            print("[API] 正在尝试通过宽表扫描进行旧版扫描兜底...")
            raw_rows = fetch_data_via_api(cookies, token)
            demand_ids = set()
            epic_id_lower = epic_id.lower()
            for r in raw_rows:
                epic_concat = r.get("epicConcat", "") or ""
                demand_id = r.get("demandId", "") or ""
                if epic_id_lower in epic_concat.lower() and demand_id:
                    demand_ids.add(demand_id.strip())
            return sorted(list(demand_ids))
        except Exception as e2:
            print(f"[API] 宽表扫描兜底也失败: {e2}")
            return []

# ============================================================
# 登录（Session 复用）
# ============================================================
async def ensure_login(context, page):
    """确保已登录。"""
    print("[登录]", end=" ", flush=True)
    try:
        test_url = DETAIL_URL_TEMPL.format("R2606160037")
        await page.goto(test_url, wait_until="domcontentloaded", timeout=15000)
        if "login" not in page.url.lower() and await page.evaluate("() => !!localStorage.getItem('GTJA_TOKEN')"):
            print("已有登录态，跳过")
            return
    except Exception:
        pass

    print("登录中...", end=" ", flush=True)
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_selector('input[placeholder*="工号"]', timeout=8000)
    await page.locator('input[placeholder*="工号"]').fill(USERNAME)
    await page.locator('input[placeholder*="密码"]').fill(PASSWORD)
    await page.locator('button:has-text("提 交")').click()
    await page.wait_for_load_state("domcontentloaded", timeout=60000)
    await asyncio.sleep(2)
    
    try:
        await context.storage_state(path=SESSION_FILE)
        print("完成（session 已保存）")
    except Exception as e:
        print(f"完成（session 保存失败: {e}）")

# ============================================================
# 修改单个需求属性
# ============================================================
async def edit_single_demand(page, demand_id, field_name, target_value):
    detail_url = DETAIL_URL_TEMPL.format(demand_id)
    print(f"\n[需求 {demand_id}] 开始处理...")
    
    # 访问详情页
    await page.goto(detail_url, wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(4)
    
    # 展开更多属性
    expand_btn = page.locator("a:has-text('展开更多'), span:has-text('展开更多')").first
    if await expand_btn.count() > 0:
        await expand_btn.click()
        await asyncio.sleep(1)
    
    # 定位目标字段的 th
    th = page.locator(f"th:has-text('{field_name}')").first
    if await th.count() == 0:
        print(f"错误: 未找到字段「{field_name}」，可能无权限或页面结构有变！")
        return False
        
    # 获取兄弟 td 并检查当前值
    td = page.locator(f"th:has-text('{field_name}') + td").first
    current_value = (await td.text_content()).strip()
    print(f"当前「{field_name}」值: {current_value}")
    
    # 判定值是否已是目标值 (一致采用相等判定，保证只保留指定标签)
    is_already_target = False
    if current_value == target_value:
        is_already_target = True
            
    if is_already_target:
        print("已经是目标值，无需修改。")
        return True
        
    # 如果是需求自定义标签，先在主页面上清理掉所有非目标标签
    if field_name == "需求自定义标签":
        while True:
            tags = await td.locator(".ant-tag").all()
            unwanted_tag = None
            unwanted_text = ""
            for tag in tags:
                tag_text = (await tag.text_content()).strip()
                if tag_text != target_value:
                    unwanted_tag = tag
                    unwanted_text = tag_text
                    break
            
            if not unwanted_tag:
                break
                
            print(f"[属性] 发现多余标签「{unwanted_text}」，准备在主页面删除...")
            close_btn = unwanted_tag.locator(".ant-tag-close-icon").first
            if await close_btn.count() > 0:
                await close_btn.click()
                await asyncio.sleep(1.5)
                confirm_btn = page.locator(".ant-popover button:has-text('确 定'), .ant-popover-buttons button:has-text('确 定'), .ant-modal button:has-text('确 定')").first
                if await confirm_btn.count() > 0:
                    await confirm_btn.click()
                    await asyncio.sleep(3) # 等待删除请求及界面更新
                else:
                    print("错误: 未找到标签删除确认按钮！")
                    break
            else:
                print("错误: 未找到标签删除图标！")
                break
        
        # 重新获取当前值并比对
        current_value = (await td.text_content()).strip()
        print(f"[属性] 主页面标签清理后当前值: {current_value}")
        if current_value == target_value:
            print("清理多余标签后值已符合目标，修改完成。")
            return True
        
    # 点击修改/添加图标 (.anticon-edit 或者空值时的 .anticon-plus)
    trigger_icon = td.locator(".anticon-edit, .anticon-plus").first
    if await trigger_icon.count() == 0:
        print("错误: 未找到修改或添加图标，该属性在此状态下可能不支持直接编辑！")
        return False
        
    await trigger_icon.click()
    await asyncio.sleep(1.5)
    
    # 检查是否拉起了模态弹窗 (例如“需求自定义标签”)
    modal = page.locator(".ant-modal-content").first
    if await modal.count() > 0 and await modal.is_visible():
        print("[属性] 检测到编辑弹窗，进入弹窗修改模式...")
        
        # 1. 移除已选的非目标标签 (只保留指定标签)
        select_container = modal.locator(".ant-select").first
        selected_items = await select_container.locator(".ant-select-selection-item").all()
        for item in selected_items:
            item_text = (await item.text_content()).strip()
            if item_text != target_value:
                print(f"[属性] 移除已有标签: {item_text}")
                remove_btn = item.locator(".ant-select-selection-item-remove").first
                if await remove_btn.count() > 0:
                    await remove_btn.click()
                    await asyncio.sleep(0.5)
                    
        # 2. 判断目标标签是否已经被选中，如果没有被选中，执行搜索并选中
        selected_items_after = await select_container.locator(".ant-select-selection-item").all_text_contents()
        selected_items_after_clean = [s.strip() for s in selected_items_after]
        
        if target_value not in selected_items_after_clean:
            # 定位搜索输入框并输入
            search_input = modal.locator("input[type='search']").first
            if await search_input.count() == 0:
                print("错误: 弹窗中未找到搜索输入框！")
                return False
                
            await search_input.click()
            await asyncio.sleep(0.5)
            
            print(f"[属性] 输入选项: {target_value}")
            await search_input.type(target_value, delay=100)
            await asyncio.sleep(1.5)
            
            # 定位并选中选项
            option = page.locator(".ant-select-item-option").filter(has_text=target_value).first
            if await option.count() == 0:
                available_options = await page.locator(".ant-select-item-option").all_text_contents()
                print(f"错误: 弹窗下拉选项中未找到「{target_value}」！可选: {available_options}")
                cancel_btn = modal.locator("button:has-text('取 消')").first
                if await cancel_btn.count() > 0:
                    await cancel_btn.click()
                return False
                
            print(f"[属性] 选中选项: {target_value}")
            await option.click()
            await asyncio.sleep(0.5)
            
        # 保存弹窗
        ok_btn = modal.locator("button:has-text('确 定')").first
        if await ok_btn.count() == 0:
            print("错误: 未找到弹窗确定保存按钮！")
            return False
            
        print("[属性] 点击确定保存修改...")
        await ok_btn.click()
        await asyncio.sleep(4)
        
    else:
        # 传统 inline 编辑模式 (例如“重点关注”)
        selector = td.locator(".ant-select-selector").first
        if await selector.count() == 0:
            print("错误: 编辑模式下未找到选择下拉框！")
            return False
            
        await selector.click()
        await asyncio.sleep(0.5)
        
        option = page.locator(".ant-select-item-option").filter(has_text=target_value).first
        if await option.count() == 0:
            available_options = await page.locator(".ant-select-item-option").all_text_contents()
            print(f"错误: 下拉选项中未找到「{target_value}」！可选: {available_options}")
            return False
            
        print(f"[属性] 选择选项: {target_value}")
        await option.click()
        await asyncio.sleep(0.5)
        
        # 确定保存
        check_icon = td.locator(".anticon-check").first
        if await check_icon.count() == 0:
            print("错误: 未找到确定保存按钮！")
            return False
            
        print("[属性] 点击确定保存修改...")
        await check_icon.click()
        await asyncio.sleep(3)
    
    # 验证修改结果
    updated_value = (await td.text_content()).strip()
    print(f"修改后「{field_name}」值: {updated_value}")
    
    success = False
    if updated_value == target_value:
        success = True
            
    if success:
        print(f"需求 {demand_id} 的「{field_name}」成功修改为「{target_value}」！")
        return True
    else:
        print(f"警告: 需求 {demand_id} 校验值不符！")
        return False

# ============================================================
# 修改单个需求的“是否大小远期同步测试”属性（在大宽表中修改）
# ============================================================
async def edit_single_demand_is_syn_test(page, demand_id, target_value):
    TABLE_URL = (
        "https://fintech.gtht.com.cn/kjpt/OnlineGrid"
        "?tableId=1597051499572236288"
        "&tableName=%E4%BA%A4%E6%98%93%E7%BB%93%E7%AE%97%E6%A0%B8%E5%BF%83%E7%B3%BB%E7%BB%9F%E9%9C%80%E6%B1%82%E9%9B%86%E5%90%88"
    )
    print(f"\n[需求 {demand_id}] 开始处理「是否大小远期同步测试」...")
    
    # 1. 确保在网格页面
    if "OnlineGrid" not in page.url:
        print("[网格] 正在导航到大宽表页面...")
        await page.goto(TABLE_URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)
        
    # 2. 搜索并展开需求行
    print(f"[网格] 正在过滤搜索需求: {demand_id}")
    search_input = page.locator('input[placeholder*="搜索"]').first
    await search_input.click()
    await search_input.fill("")
    await search_input.type(demand_id, delay=50)
    await search_input.press("Enter")
    await asyncio.sleep(4)
    
    # 3. 提取所有关联 Story 行
    row_data = await page.evaluate("""(reqId) => {
        const el = document.querySelector('.ag-root-wrapper');
        const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber'));
        let current = el[fiberKey];
        let api = null;
        while (current) {
            const node = current.stateNode;
            if (node && (node.gridApi || node.api || (node.gridOptions && node.gridOptions.api))) {
                api = node.gridApi || node.api || node.gridOptions.api;
                break;
            }
            current = current.return;
        }
        if (!api) return null;
        const results = [];
        api.forEachNode(node => {
            if (node.data && node.data.demandId === reqId) {
                results.push({ rowId: node.id, isSynTest: node.data.isSynTest, storyCode: node.data.storyCode });
            }
        });
        return results;
    }""", demand_id)
    
    if not row_data:
        print(f"❌ 警告: 未在大宽表中找到需求 {demand_id} 的任何 Story 行！")
        return False
        
    print(f"[网格] 找到 {len(row_data)} 个关联 Story 行。")
    all_ok = True
    for item in row_data:
        row_id = item["rowId"]
        story_code = item.get("storyCode", "未知")
        current_val = (item.get("isSynTest") or "").strip()
        print(f"  - Story {story_code} (rowId: {row_id}), 当前值: '{current_val}'")
        
        if current_val == target_value:
            print("    已经是目标值，无需修改。")
            continue
            
        # 触发编辑
        await page.evaluate("""({ rowId, colKey }) => {
            const el = document.querySelector('.ag-root-wrapper');
            const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber'));
            let current = el[fiberKey];
            let api = null;
            while (current) {
                const node = current.stateNode;
                if (node && (node.gridApi || node.api || (node.gridOptions && node.gridOptions.api))) {
                    api = node.gridApi || node.api || node.gridOptions.api;
                    break;
                }
                current = current.return;
            }
            if (!api) return;
            api.ensureColumnVisible(colKey);
            const rowNode = api.getRowNode(rowId);
            api.ensureNodeVisible(rowNode);
            api.startEditingCell({ rowIndex: rowNode.rowIndex, colKey: colKey });
        }""", {"rowId": row_id, "colKey": "isSynTest"})
        await asyncio.sleep(1.5)
        
        # 激活 Select 下拉框并点击目标值
        selector = page.locator(".ag-cell-inline-editing .ant-select-selector").first
        if await selector.count() > 0:
            await selector.click()
            await asyncio.sleep(1.0)
            
            option = page.locator(".ant-select-dropdown:visible .ant-select-item-option").filter(has_text=target_value).first
            if await option.count() > 0:
                await option.click()
                await asyncio.sleep(0.5)
                await page.keyboard.press("Enter")
                await asyncio.sleep(3.0) # 等待保存
                
                # 再次获取验证
                updated_val = await page.evaluate("""({ rowId, colKey }) => {
                    const el = document.querySelector('.ag-root-wrapper');
                    const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber'));
                    let current = el[fiberKey];
                    let api = null;
                    while (current) {
                        const node = current.stateNode;
                        if (node && (node.gridApi || node.api || (node.gridOptions && node.gridOptions.api))) {
                            api = node.gridApi || node.api || node.gridOptions.api;
                            break;
                        }
                        current = current.return;
                    }
                    if (!api) return '';
                    const rowNode = api.getRowNode(rowId);
                    return rowNode && rowNode.data ? (rowNode.data[colKey] || '') : '';
                }""", {"rowId": row_id, "colKey": "isSynTest"})
                
                print(f"    修改后最新值: '{updated_val}'")
                if updated_val == target_value:
                    print(f"    Story {story_code} 修改成功！")
                else:
                    print(f"    ❌ Story {story_code} 校验失败！")
                    all_ok = False
            else:
                print(f"    ❌ 下拉选项 '{target_value}' 未找到！")
                await page.keyboard.press("Escape")
                all_ok = False
        else:
            print("    ❌ 未定位到编辑框！")
            all_ok = False
            
    return all_ok

# ============================================================
# 主入口（异步）
# ============================================================
async def run(target_id, field_name, target_value, headed):
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
            # 1. 确保登录
            await ensure_login(context, page)
            
            # 2. 提取 Token 和 Cookies 以便可能需要调用 API
            cookies_list = await context.cookies()
            cookies = {c["name"]: c["value"] for c in cookies_list if c.get("domain") in ("fintech.gtht.com.cn", ".gtht.com.cn")}
            token = await page.evaluate("() => localStorage.getItem('GTJA_TOKEN')")
            
            # 3. 确定要处理的需求 ID 列表
            demand_ids = []
            target_id_upper = target_id.upper()
            if target_id_upper.startswith("R") and "-" not in target_id_upper:
                demand_ids = [target_id_upper]
                print(f"[模式] 单个需求修改模式: {demand_ids[0]}")
            elif target_id_upper.startswith("E") or target_id_upper.startswith("P"):
                print(f"[模式] 史诗批量修改模式 (识别特征: {target_id_upper[0]}开头): {target_id}")
                demand_ids = get_demands_by_epic(target_id, cookies, token)
                if not demand_ids:
                    print(f"未找到史诗「{target_id}」下的任何需求！请核对史诗编号是否正确。")
                    sys.exit(1)
                print(f"[史诗] 关联的需求 ID 列表: {demand_ids}")
            else:
                print(f"[模式] 史诗批量修改模式 (默认): {target_id}")
                demand_ids = get_demands_by_epic(target_id, cookies, token)
                if not demand_ids:
                    print(f"未找到史诗「{target_id}」下的任何需求！请核对史诗编号是否正确。")
                    sys.exit(1)
                print(f"[史诗] 关联的需求 ID 列表: {demand_ids}")
            
            # 4. 循环修改各需求属性
            success_count = 0
            fail_count = 0
            for did in demand_ids:
                try:
                    if field_name == "isSynTest":
                        res = await edit_single_demand_is_syn_test(page, did, target_value)
                    else:
                        res = await edit_single_demand(page, did, field_name, target_value)
                    if res:
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception as ex:
                    print(f"修改需求 {did} 发生异常: {ex}")
                    fail_count += 1
            
            print(f"\n[汇总] 处理完成。成功: {success_count} 个，失败: {fail_count} 个")
            
            # 保存最后一次处理结果截图
            if demand_ids:
                screenshot_path = os.path.join(SCRIPT_DIR, f"edit_last_result.png")
                await page.screenshot(path=screenshot_path)
                print(f"[截图] 结果已保存: {screenshot_path}")
                
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
    parser = argparse.ArgumentParser(description="修改需求要素属性（支持需求/史诗编号，支持普通属性与标签）")
    parser.add_argument("target_id", help="需求编号（如 R2606160037）或史诗编号（如 PG202204-0267）")
    parser.add_argument("field_name", help="要修改的字段名（如 重点关注，需求自定义标签，同步测试，是否大小远期同步测试）")
    parser.add_argument("target_value", help="目标值（如 是，CX-信用-两融）")
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    args = parser.parse_args()
    
    target_id = args.target_id.strip()
    field_name_raw = args.field_name.strip()
    target_value = args.target_value.strip()
    
    # 字段别名映射表
    FIELD_ALIASES = {
        "标签": "需求自定义标签",
        "需求标签": "需求自定义标签",
        "自定义标签": "需求自定义标签",
        "同步测试": "isSynTest",
        "是否大小远期同步测试": "isSynTest",
    }
    
    field_name = FIELD_ALIASES.get(field_name_raw, field_name_raw)
    
    print(f"\n{'='*50}")
    print(f"  修改需求属性要素 (增强版)")
    print(f"  目标 ID: {target_id}")
    print(f"  输入字段: {field_name_raw} -> 实际定位字段: {field_name}")
    print(f"  修改目标: {target_value}")
    print(f"{'='*50}")
    
    asyncio.run(run(target_id, field_name, target_value, args.headed))

if __name__ == "__main__":
    main()
