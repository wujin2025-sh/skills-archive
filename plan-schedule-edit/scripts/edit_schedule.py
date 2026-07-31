#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
计划生产排期修改工具（异步并发版）
==========================================
打开「交易结算核心系统需求集合」大宽表，支持两种模式：
1. 单笔修改模式：通过参数传入需求编号和目标日期。
2. 批量修改模式：通过 --excel 参数传入 Excel 文件路径，自动提取：
   - C 列 (第 3 列)：需求编号 (形如 R2603310051)
   - L 列 (第 12 列)：拟调整版本 (形如 20260724)
   
优化策略：
- 使用 Playwright 异步 API 并行执行多个页面，分片处理不同的需求编号，极大地提升批量更新的效率。
- 提供统一并发度参数 `--concurrency`，默认并发度为 3。
- 启动前统一通过单个 bootstrap page 预登录，避免并发登录冲突。
- 提供了可选的批量持久化校验选项（--verify），在批处理完成后使用并发 worker 重新加载页面进行校验。
"""

import sys
import os
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
# 配置
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
    elif sys.platform == "win32":
        try:
            output = subprocess.check_output("wmic csproduct get uuid", shell=True)
            uuid_str = output.decode('utf-8').split('\n')[1].strip()
            if uuid_str:
                identifiers.append(uuid_str)
        except Exception:
            try:
                output = subprocess.check_output("powershell Get-CimInstance -ClassName Win32_ComputerSystemProduct | Select-Object -ExpandProperty UUID", shell=True)
                uuid_str = output.decode('utf-8').strip()
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

# 优先从环境变量读取敏感凭据 (PLATFORM_USERNAME, PLATFORM_PASSWORD)
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


if not USERNAME or not PASSWORD:
    print("\n" + "=" * 75, file=sys.stderr)
    print("❌ [配置缺失错误] 未找到有效的登录凭据 (USERNAME / PASSWORD)", file=sys.stderr)
    print("-" * 75, file=sys.stderr)
    print("💡 建议通过环境变量配置（最安全）：", file=sys.stderr)
    print("   export PLATFORM_USERNAME=\"你的工号\"", file=sys.stderr)
    print("   export PLATFORM_PASSWORD=\"你的密码\"", file=sys.stderr)
    print(f"👉 或编辑配置文件 {os.path.join(SKILL_ROOT, 'config.json')} 注入：", file=sys.stderr)
    print("   {", file=sys.stderr)
    print('     "username": "125360",', file=sys.stderr)
    print('     "password": "您的密码",', file=sys.stderr)
    print('     "platform_url": "https://fintech.gtht.com.cn",', file=sys.stderr)
    print('     "target_assignee": "吴进"', file=sys.stderr)
    print("   }", file=sys.stderr)
    print("=" * 75 + "\n", file=sys.stderr)
    sys.exit(1)

LOGIN_URL = "https://fintech.gtht.com.cn/kjpt/user/login"

TABLE_URL = (
    "https://fintech.gtht.com.cn/kjpt/OnlineGrid"
    "?tableId=1597051499572236288"
    "&tableName=%E4%BA%A4%E6%98%93%E7%BB%93%E7%AE%97%E6%A0%B8%E5%BF%83%E7%B3%BB%E7%BB%9F%E9%9C%80%E6%B1%82%E9%9B%86%E5%90%88"
)

# 动态解析 Session 与缓存路径，杜绝绝对硬编码
SESSION_FILE = os.path.abspath(os.path.join(os.getcwd(), ".fintech_session.json"))
CACHE_FILE = os.path.abspath(os.path.join(os.getcwd(), ".table_cache.json"))
CACHE_TTL = 14400  # 4 hours (optimized for read-heavy query performance)
CACHE_TTL = 14400  # 4 hours (optimized for read-heavy query performance)

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
# 日期格式化与转换
# ============================================================
def parse_date(val):
    if not val:
        return None
    import datetime
    # 如果是 datetime/date 对象
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.strftime("%Y-%m-%d")
    
    # 清理并尝试解析字符串形式的日期
    s = str(val).strip()
    s_clean = re.sub(r"[-/\.\s]", "", s)
    if re.match(r"^\d{8}$", s_clean):
        return f"{s_clean[0:4]}-{s_clean[4:6]}-{s_clean[6:8]}"
    elif re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    return None

def format_demand_link(demand_id):
    if not demand_id or str(demand_id).strip().upper() in ("N/A", "空", ""):
        return "N/A"
    did = str(demand_id).strip()
    if did.startswith("R") or did.startswith("r"):
        return f"[{did}](https://fintech.gtht.com.cn/kjpt/DemandManage/details?demandId={did}&templateId=8888&flag=1)"
    return did

# ============================================================
# 从 Excel 中读取修改记录
# ============================================================
def read_excel_records(filepath, target_assignee=None):
    from openpyxl import load_workbook
    wb = load_workbook(filepath, read_only=True, data_only=True)
    ws = wb.active

    if not target_assignee:
        target_assignee = CONFIG_TARGET_ASSIGNEE or "吴进"

    records = []
    for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if row_idx == 1:
            # 跳过第一行表头
            continue
        # C列 = index 2, L列 = index 11, Q列 = index 16
        if not row or len(row) < 17:
            continue
        
        req_id_raw = row[2]  # C列
        date_raw = row[11]   # L列
        assignee_raw = row[16] # Q列
        
        req_id = str(req_id_raw or "").strip()
        if not req_id:
            continue
            
        # 筛选 Q 列包含指定受理人的需求，其他不更新 (为 ALL 时不进行过滤)
        assignee = str(assignee_raw or "").strip()
        if target_assignee and target_assignee.upper() != "ALL" and target_assignee not in assignee:
            print(f"⚠️ [Excel] 行 {row_idx}: 需求号 {req_id} 受理人为 '{assignee}'，不包含授权目标人 '{target_assignee}'，已跳过")
            continue
            
        # 验证需求号格式是否合理 (R/PG/E开头)
        if not re.match(r"^(R|PG|E)", req_id, re.IGNORECASE):
            continue
            
        if not date_raw:
            print(f"⚠️ [Excel] 行 {row_idx}: 需求号 {req_id} 对应的调整日期为空，跳过")
            continue
            
        target_date = parse_date(date_raw)
        if not target_date:
            print(f"⚠️ [Excel] 行 {row_idx}: 需求号 {req_id} 对应的调整日期 '{date_raw}' 格式无效，跳过")
            continue
            
        records.append({
            "row_idx": row_idx,
            "req_id": req_id,
            "target_date": target_date
        })
    
    return records

def partition_list(lst, num_chunks):
    """将列表 lst 分成最多 num_chunks 个分片。"""
    chunks = [[] for _ in range(num_chunks)]
    for idx, item in enumerate(lst):
        chunks[idx % num_chunks].append(item)
    return [c for c in chunks if c]

# ============================================================
# 登录（Session 复用）
# ============================================================
async def ensure_login(context, page):
    """确保登录态有效。"""
    print("[登录]", end=" ", flush=True)
    t0 = time.time()

    try:
        await page.goto(TABLE_URL, wait_until="commit", timeout=25000)
        # 智能等待：要么加载成功出现了数据行（已有登录态），要么重定向到了登录页（出现工号输入框）
        for _ in range(25): # 最多等待 5 秒
            if await page.evaluate("() => !!document.querySelector('input[placeholder*=\"工号\"]')"):
                break
            if await page.evaluate(_JS_ROWS_VISIBLE):
                print(f"已有登录态（{time.time() - t0:.1f}s）")
                return
            await page.wait_for_timeout(200)
    except Exception:
        pass

    print("登录中...", end=" ", flush=True)
    await page.goto(LOGIN_URL, wait_until="commit", timeout=30000)
    await page.wait_for_selector('input[placeholder*="工号"]', timeout=15000)
    await page.locator('input[placeholder*="工号"]').fill(USERNAME)
    await page.locator('input[placeholder*="密码"]').fill(PASSWORD)
    await page.locator('button:has-text("提 交")').click()
    await page.wait_for_load_state("domcontentloaded", timeout=60000)
    try:
        await page.wait_for_url("**/OnlineGrid**", timeout=15000)
    except PWTimeout:
        pass
    
    # 登录成功后，必须导航回目标 TABLE_URL
    print("导航至目标大宽表...", end=" ", flush=True)
    await page.goto(TABLE_URL, wait_until="commit", timeout=30000)
    await page.wait_for_timeout(1000)

    try:
        await context.storage_state(path=SESSION_FILE)
        print(f"完成（{time.time() - t0:.1f}s）")
    except Exception as e:
        print(f"完成（session 保存失败: {e}）")

# ============================================================
# 搜索并展开
# ============================================================
async def search_and_expand(page, req_id):
    print(f"[搜索] 过滤需求: {req_id}...")
    t0 = time.time()

    # 0. 确保 ag-Grid 数据已加载
    try:
        await page.wait_for_function("""() => {
            const el = document.querySelector('.ag-root-wrapper');
            if (!el) return false;
            const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber'));
            let current = el[fiberKey];
            let api = null;
            while (current) {
                const node = current.stateNode;
                if (node && (node.gridApi || node.api || node.gridOptions)) {
                    api = node.gridApi || node.api || (node.gridOptions && node.gridOptions.api);
                    break;
                }
                current = current.return;
            }
            return api && api.getModel() && api.getModel().getRowCount() > 100;
        }""", timeout=30000)
    except Exception:
        pass

    # 1. 填入搜索框触发 ag-Grid DOM 过滤
    try:
        search_box = page.locator("#filter-text-box")
        await search_box.wait_for(state="visible", timeout=15000)
        try:
            await page.wait_for_selector(".ant-spin-spinning", state="detached", timeout=30000)
        except Exception:
            pass
        await search_box.click(force=True)
        await search_box.fill(req_id)
        await page.wait_for_timeout(500)
    except Exception as e:
        print(f"[搜索] ⚠️ 填入搜索框异常: {e}")

    # 2. 点击一键展开
    await page.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const btn of btns) {
            if (btn.textContent.trim() === '一键展开') {
                btn.click();
                return true;
            }
        }
        return false;
    }""")
    await page.wait_for_timeout(300)

    # 3. 快速轮询等待目标数据行渲染完成
    try:
        await page.wait_for_function("""() => {
            const leftContainer = document.querySelector('.ag-pinned-left-cols-container');
            if (!leftContainer) return false;
            return leftContainer.querySelectorAll('.ag-row:not(.ag-row-group)').length > 0;
        }""", polling=100, timeout=5000)
    except PWTimeout:
        pass

    print(f"[搜索] 过滤和展开完成（{time.time() - t0:.2f}s）")


# ============================================================
# 获取当前匹配的所有 Story 列表及其 row-id 和 Story编号
# ============================================================
async def get_story_rows(page, req_id):
    return await page.evaluate("""(reqId) => {
        const el = document.querySelector('.ag-root-wrapper');
        if (el) {
            const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber'));
            if (fiberKey) {
                let current = el[fiberKey];
                let api = null;
                while (current) {
                    const node = current.stateNode;
                    if (node && (node.gridApi || node.api || node.gridOptions)) {
                        api = node.gridApi || node.api || (node.gridOptions && node.gridOptions.api);
                        break;
                    }
                    current = current.return;
                }
                if (api && typeof api.forEachNode === 'function') {
                    const isEpic = reqId.startsWith('E') || reqId.startsWith('PG');
                    const results = [];
                    api.forEachNode(n => {
                        if (!n.data) return;
                        let match = false;
                        if (isEpic) {
                            const epicCode = String(n.data.epicCode || '');
                            const epicConcat = String(n.data.epicConcat || '');
                            if (epicCode.includes(reqId) || epicConcat.includes(reqId)) match = true;
                        } else {
                            const demandId = String(n.data.demandId || '');
                            if (demandId === reqId) match = true;
                        }
                        if (match) {
                            results.push({
                                rowId: n.id,
                                storyCode: n.data.storyCode || 'Story',
                                demandId: n.data.demandId || reqId
                            });
                        }
                    });
                    if (results.length > 0) return results;
                }
            }
        }
        
        // DOM 兜底
        const leftContainer = document.querySelector('.ag-pinned-left-cols-container');
        const results = [];
        if (leftContainer) {
            const rows = leftContainer.querySelectorAll('.ag-row');
            for (const row of rows) {
                const rowId = row.getAttribute('row-id');
                if (rowId) {
                    results.push({ rowId, storyCode: 'Story', demandId: reqId });
                }
            }
        }
        return results;
    }""", req_id)

# ============================================================
# 修改单行日期（极速 API 版）
# ============================================================
async def edit_row_date(page, row_id, story_code, target_date_str, wait_sec=0):
    print(f"[无头极速模式] 正在更新 Story [{story_code}] (rowId: {row_id}) 的计划生产排期为 {target_date_str}...")
    
    update_res = await page.evaluate("""({ rowId, colKey, targetVal }) => {
        const el = document.querySelector('.ag-root-wrapper');
        if (!el) return { error: 'no ag-root-wrapper' };
        const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber'));
        let current = el[fiberKey];
        let api = null, gridOptions = null, reactComp = null;
        while (current) {
            const node = current.stateNode;
            if (node && (node.sendRowData || node.gridApi || node.api || node.gridOptions)) {
                api = api || node.gridApi || node.api || (node.gridOptions && node.gridOptions.api);
                gridOptions = gridOptions || node.gridOptions || (api && api.gridOptions);
                if (node.sendRowData) reactComp = node;
                if (api && reactComp) break;
            }
            current = current.return;
        }
        if (!api) return { error: 'no ag-grid api' };
        const rowNode = api.getRowNode(rowId);
        if (!rowNode) return { error: 'rowNode not found' };
        
        const oldVal = rowNode.data ? (rowNode.data[colKey] || '') : '';
        if (oldVal === targetVal) {
            return { ok: true, beforeVal: oldVal, afterVal: targetVal, skipped: true };
        }
        
        // 1. 更新内部数据结构
        if (rowNode.data) {
            rowNode.data[colKey] = targetVal;
        }
        
        // 2. 调用 reactComp.sendRowData 真实触发出库 WebSocket 持久化落库
        if (reactComp && typeof reactComp.sendRowData === 'function') {
            const payload = Object.assign({ sheetId: (reactComp.props && reactComp.props.sheetId) || '1597051509256884224' }, rowNode.data);
            reactComp.sendRowData(payload);
        } else if (gridOptions && typeof gridOptions.onCellValueChanged === 'function') {
            const eventObj = {
                node: rowNode,
                data: rowNode.data,
                oldValue: oldVal,
                newValue: targetVal,
                value: targetVal,
                source: 'paste',
                colDef: { field: colKey },
                column: (typeof api.getColumn === 'function' ? api.getColumn(colKey) : null),
                api: api,
                columnApi: api.columnModel || api.columnApi
            };
            gridOptions.onCellValueChanged(eventObj);
        }
        
        // 3. 强制刷新单元格 DOM
        if (typeof api.refreshCells === 'function') {
            api.refreshCells({ rowNodes: [rowNode], columns: [colKey], force: true });
        }
        return { ok: true, beforeVal: oldVal, afterVal: targetVal, skipped: false };
    }""", {"rowId": row_id, "colKey": "planProdLineDate", "targetVal": target_date_str})

    if not isinstance(update_res, dict) or not update_res.get("ok"):
        print(f"[修改] ⚠️ 单元格更新处理异常 ({update_res})")
        return "N/A", "N/A", False

    before_val = str(update_res.get("beforeVal") or "").strip()
    after_val = str(update_res.get("afterVal") or "").strip()
    print(f"[修改] 极速模式更新完成: '{before_val}' -> '{after_val}'")
    return before_val, after_val, True





# ============================================================
# 并发 Worker 协程
# ============================================================
async def run_worker(worker_id, chunk, context, results, existing_page=None):
    """工作协程：处理当前分片的所有记录。"""
    print(f"[Worker-{worker_id}] 启动，分片大小: {len(chunk)}")
    if existing_page:
        page = existing_page
        print(f"[Worker-{worker_id}] 复用已有页面")
    else:
        page = await context.new_page()
    try:
        if not existing_page:
            # 导航到表格页面
            await page.goto(TABLE_URL, wait_until="commit", timeout=45000)
        
        any_modified = False
        for rec in chunk:
            rec_req_id = rec["req_id"]
            rec_target_date = rec["target_date"]
            
            print(f"\n[Worker-{worker_id}] 开始处理: {rec_req_id} -> {rec_target_date}")
            
            # 过滤并展开
            await search_and_expand(page, rec_req_id)
            
            # 获取匹配 of Story 行
            stories = await get_story_rows(page, rec_req_id)
            if not stories:
                print(f"❌ [Worker-{worker_id}] 警告: 未能在表格中找到属于需求 '{rec_req_id}' 的 Story 行。已跳过。")
                results.append({
                    "req_id": rec_req_id,
                    "target_date": rec_target_date,
                    "storyCode": "未找到 Story",
                    "before": "N/A",
                    "after": "N/A",
                    "persisted": "未校验",
                    "status": "❌ 未找到 Story 行"
                })
                continue
            
            print(f"[Worker-{worker_id}][定位] 该需求下共找到 {len(stories)} 个关联 Story，开始修改...")
            for s in stories:
                before, after, ok = await edit_row_date(
                    page, s['rowId'], s['storyCode'], rec_target_date,
                    wait_sec=0.5
                )
                await asyncio.sleep(0.8)
                if before != after:
                    any_modified = True
                results.append({
                    "req_id": rec_req_id,
                    "demand_id": s.get('demandId') or rec_req_id,
                    "target_date": rec_target_date,
                    "storyCode": s['storyCode'],
                    "before": before,
                    "after": after,
                    "rowId": s['rowId'],
                    "persisted": "未校验"
                })
        
        if any_modified:
            print(f"\n[Worker-{worker_id}] 检测到有修改，等待 10 秒以确保全部 15+ 条 WebSocket 消息完成落库...")
            await asyncio.sleep(10)
            
    except Exception as e:
        print(f"❌ [Worker-{worker_id}] 运行中发生异常: {e}")
        # 将出错的需求和Story状态标记为错误
        for rec in chunk:
            results.append({
                "req_id": rec["req_id"],
                "target_date": rec["target_date"],
                "storyCode": "运行异常",
                "before": "N/A",
                "after": "N/A",
                "persisted": "未校验",
                "status": f"❌ 异常: {e}"
            })
    finally:
        await page.close()
        print(f"[Worker-{worker_id}] 已关闭页面")

async def run_verifier(verifier_id, req_ids_chunk, context, verification_map):
    """验证协程：优先通过 API 极速验证，失败则降级通过无头浏览器验证。"""
    print(f"[Verifier-{verifier_id}] 启动，待验证需求数: {len(req_ids_chunk)}")
    
    # 1. 尝试通过 API 进行极速校验 (<300ms)
    unverified = []
    for v_req_id in req_ids_chunk:
        api_results, err, _ = query_schedule_via_api(v_req_id, no_cache=True)
        if api_results and not err:
            for item in api_results:
                if item.get("rowId"):
                    verification_map[item["rowId"]] = item.get("planDate", "")
        else:
            unverified.append(v_req_id)
            
    if not unverified:
        print(f"[Verifier-{verifier_id}] 极速 API 校验全部成功完成！")
        return

    # 2. 浏览器降级校验
    page = await context.new_page()
    try:
        await page.goto(TABLE_URL, wait_until="commit", timeout=45000)
        for v_req_id in unverified:
            print(f"[Verifier-{verifier_id}] 浏览器降级验证需求: {v_req_id}...")
            await search_and_expand(page, v_req_id)
            stories_after_reload = await get_story_rows(page, v_req_id)
            for s in stories_after_reload:
                cell_selector = f'.ag-center-cols-container .ag-row[row-id="{s["rowId"]}"] .ag-cell[col-id="planProdLineDate"]'
                val_after_reload = await page.evaluate("""(selector) => {
                    const el = document.querySelector(selector);
                    return el ? el.textContent.trim() : '';
                }""", cell_selector)
                verification_map[s["rowId"]] = val_after_reload
    except Exception as e:
        print(f"❌ [Verifier-{verifier_id}] 验证中发生异常: {e}")
    finally:
        await page.close()
        print(f"[Verifier-{verifier_id}] 已关闭页面")

# ============================================================
# 仅查询不修改逻辑
# ============================================================
async def query_requirement_schedule(page, req_id):
    """仅查询当前需求的计划生产排期，不做任何修改。"""
    print(f"==================================================")
    print(f"  计划生产排期查询（只读查询模式）")
    print(f"  需求编号: {req_id}")
    print(f"==================================================")
    
    await search_and_expand(page, req_id)
    stories = await get_story_rows(page, req_id)
    if not stories:
        print(f"❌ 未能在表格中找到属于需求 '{req_id}' 的 Story 行。")
        return []
        
    results = []
    print(f"[定位] 该需求下共找到 {len(stories)} 个关联 Story，开始读取计划生产排期...")
    for s in stories:
        cell_selector = f'.ag-center-cols-container .ag-row[row-id="{s["rowId"]}"] .ag-cell[col-id="planProdLineDate"]'
        val = await page.evaluate("""(selector) => {
            const el = document.querySelector(selector);
            return el ? el.textContent.trim() : '';
        }""", cell_selector)
        results.append({
            "req_id": s.get('demandId') or req_id,
            "storyCode": s['storyCode'],
            "planDate": val
        })
    return results

def query_schedule_via_api(req_id, no_cache=False):
    """尝试通过 HTTP API 直接获取表格数据并过滤需求排期（支持本地缓存）。"""
    # 尝试读取缓存
    if not no_cache and os.path.exists(CACHE_FILE):
        try:
            age = time.time() - os.path.getmtime(CACHE_FILE)
            if age < CACHE_TTL:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    rows = json.load(f)
                if rows:
                    results = []
                    is_epic = req_id.startswith("E") or req_id.startswith("PG")
                    for row in rows:
                        match = False
                        if is_epic:
                            epic_code = str(row.get("epicCode") or "").strip()
                            epic_concat = str(row.get("epicConcat") or "").strip()
                            epic_id = epic_concat.split("+")[0].strip() if epic_concat else epic_code
                            if epic_code == req_id or epic_id == req_id or epic_concat.startswith(req_id + "+") or epic_concat == req_id:
                                match = True
                        else:
                            if str(row.get("demandId") or "").strip() == req_id:
                                match = True
                                
                        if match:
                            results.append({
                                "req_id": row.get("demandId") or "未知需求",
                                "storyCode": row.get("storyCode") or "未知Story",
                                "planDate": (row.get("planProdLineDate") or "").strip(),
                                "rowId": str(row.get("rowId") or "")
                            })
                    return results, None, int(age)
        except Exception as e:
            print(f"[API] 读取缓存失败: {e}")

    # 缓存不可用或过期，重新请求 API
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
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://fintech.gtht.com.cn/kjpt/OnlineGrid?tableId=1597051499572236288",
            "accept": "application/json",
            "content-type": "application/json",
        }
        if token:
            headers["token"] = token
            
        CONTENT_URL = "https://fintech.gtht.com.cn/api/table-service/table/row/getSheetContent?sheetId=1597051509256884224"
        r = requests.get(CONTENT_URL, cookies=cookies, headers=headers, timeout=60)
        if r.status_code != 200:
            return None, f"HTTP error {r.status_code}", 0
            
        resp_json = r.json()
        if resp_json.get("code") != 200:
            return None, f"API error: {resp_json.get('message') or resp_json.get('msg')}", 0
            
        rows = resp_json.get("data", {}).get("data", [])
        if not rows:
            return None, "Empty data returned from API", 0
            
        # 写入缓存
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[API] 写入缓存失败: {e}")
            
        # 过滤需求或史诗行
        results = []
        is_epic = req_id.startswith("E") or req_id.startswith("PG")
        for row in rows:
            # 准确性优先：过滤已终止、已作废、已关闭或已删除的废弃 Story 节点
            status_name = str(row.get("storyStatusName") or row.get("statusName") or "").strip()
            if status_name in ("终止", "已作废", "已取消", "已关闭", "删除") or str(row.get("delFlag")) == "1" or str(row.get("isDelete")) == "1":
                continue

            match = False
            if is_epic:
                epic_code = str(row.get("epicCode") or "").strip()
                epic_concat = str(row.get("epicConcat") or "").strip()
                epic_id = epic_concat.split("+")[0].strip() if epic_concat else epic_code
                if epic_code == req_id or epic_id == req_id or epic_concat.startswith(req_id + "+") or epic_concat == req_id:
                    match = True
            else:
                if str(row.get("demandId") or "").strip() == req_id:
                    match = True
                    
            if match:
                results.append({
                    "req_id": row.get("demandId") or "未知需求",
                    "storyCode": row.get("storyCode") or "未知Story",
                    "planDate": (row.get("planProdLineDate") or "").strip(),
                    "rowId": str(row.get("rowId") or "")
                })
        return results, None, 0
    except Exception as e:
        return None, str(e), 0

# ============================================================
# 主逻辑
# ============================================================
async def main_async():
    parser = argparse.ArgumentParser(description="计划生产排期修改工具（支持单笔及 Excel 批量修改 - 异步并发版）")
    parser.add_argument("req_id", nargs="?", help="需求编号（单笔修改模式）")
    parser.add_argument("new_date", nargs="?", help="目标排期日期（单笔修改模式）")
    parser.add_argument("--excel", help="Excel 文件路径（批量修改模式）")
    parser.add_argument("--headed", action="store_true", help="是否以 headed 模式运行浏览器")
    parser.add_argument("--verify", action="store_true", help="是否在全部修改完成后重新加载页面进行持久化校验")
    parser.add_argument("-c", "--concurrency", type=int, default=3, help="批量修改并发度（默认为 3）")
    parser.add_argument("--no-cache", action="store_true", help="强制不使用缓存，直接请求接口")
    args = parser.parse_args()

    # 模式选择与参数校验
    is_batch_mode = args.excel is not None
    is_query_mode = False

    if not is_batch_mode:
        if not args.req_id:
            parser.error("单笔模式下，必须提供 'req_id'。")
        
        req_id = args.req_id.strip()
        if args.new_date:
            raw_date = args.new_date.strip()
            target_date = parse_date(raw_date)
            if not target_date:
                print(f"❌ 错误: 日期格式无效 '{raw_date}'，支持 YYYYMMDD 或 YYYY-MM-DD")
                sys.exit(1)
            
            records = [{
                "row_idx": 1,
                "req_id": req_id,
                "target_date": target_date
            }]
            print(f"==================================================")
            print(f"  计划生产排期修改（单笔修改模式）")
            print(f"  需求编号: {req_id}")
            print(f"  修改目标: {target_date}")
            print(f"==================================================")
            concurrency = 1
        else:
            is_query_mode = True
            records = []
            concurrency = 1
    else:
        excel_path = os.path.abspath(args.excel)
        if not os.path.exists(excel_path):
            print(f"❌ 错误: 指定的 Excel 文件不存在 '{excel_path}'")
            sys.exit(1)
            
        print(f"==================================================")
        print(f"  计划生产排期修改（批量修改模式）")
        print(f"  Excel 路径: {excel_path}")
        print(f"  目标并发度: {args.concurrency}")
        print(f"==================================================")
        
        try:
            records = read_excel_records(excel_path)
        except Exception as err:
            print(f"❌ 读取 Excel 发生异常: {err}")
            sys.exit(1)
            
        if not records:
            print("❌ 错误: 未能在 Excel 中解析出任何有效的需求修改记录（C列需求号，L列日期）")
            sys.exit(1)
            
        print(f"[读取] 解析成功，共找到 {len(records)} 条有效待修改记录。")
        concurrency = max(1, args.concurrency)

    if is_query_mode:
        print(f"[API] 正在尝试通过直接在线接口获取最新数据...")
        # 查询模式默认强制拉取最新在线 API 数据 (no_cache=True)，彻底避免误读本地过期缓存文件
        api_results, err, cache_age = query_schedule_via_api(req_id, no_cache=True)
        if err is None:
            if api_results:
                mode_str = "极速在线接口模式"
                print(f"[API] 查询成功 ({mode_str})")
                is_epic_query = req_id.startswith("E") or req_id.startswith("PG")
                print("\nRESULT_MARKDOWN_START")
                print(f"### 计划生产排期查询结果")
                title_label = "史诗编号" if is_epic_query else "需求编号"
                print(f"{title_label}: **{req_id}**\n")
                if is_epic_query:
                    print("| 序号 | 史诗编号 | 需求编号 | Story 编号 | 当前计划生产排期 |")
                    print("| :--- | :--- | :--- | :--- | :--- |")
                    for idx, r in enumerate(api_results, 1):
                        print(f"| {idx} | {req_id} | {format_demand_link(r['req_id'])} | {r['storyCode']} | {r['planDate'] or '空'} |")
                else:
                    print("| 序号 | 需求编号 | Story 编号 | 当前计划生产排期 |")
                    print("| :--- | :--- | :--- | :--- |")
                    for idx, r in enumerate(api_results, 1):
                        print(f"| {idx} | {format_demand_link(r['req_id'])} | {r['storyCode']} | {r['planDate'] or '空'} |")
                print("RESULT_MARKDOWN_END")
                return
            else:
                print(f"[API] 警告: 未在在线数据中找到需求 '{req_id}' 的 Story 行。将通过浏览器模式二次确认...")
        else:
            print(f"[API] 接口查询不可用 ({err})，正在启动无头浏览器进行准确查询...")


    overall_t0 = time.time()

    from playwright.async_api import async_playwright
    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=not args.headed,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            storage_state=SESSION_FILE if os.path.exists(SESSION_FILE) else None,
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )

        # 拦截媒体、字体及第三方分析/追踪资源以极速加载
        async def block_resources(route):
            url = route.request.url
            if route.request.resource_type in ["image", "media", "font"] or any(x in url for x in ["sa.gif", "sentry", "gtjadev", "sensorsdata", "umeng", "analytics", "hm.js"]):
                await route.abort()
            else:
                await route.continue_()
        await context.route("**/*", block_resources)

        try:
            # 1. 预登录检验 (Bootstrap)
            bootstrap_page = await context.new_page()
            await ensure_login(context, bootstrap_page)

            if is_query_mode:
                # 只读查询模式 - 直接复用已打开并且加载好 TABLE_URL 的 bootstrap_page
                try:
                    # 确保页面在 TABLE_URL 且 DOM 稳定
                    if not bootstrap_page.url.startswith("https://fintech.gtht.com.cn/kjpt/OnlineGrid"):
                        await bootstrap_page.goto(TABLE_URL, wait_until="commit", timeout=45000)
                    
                    query_results = await query_requirement_schedule(bootstrap_page, req_id)
                    
                    is_epic_query = req_id.startswith("E") or req_id.startswith("PG")
                    print("\nRESULT_MARKDOWN_START")
                    print(f"### 计划生产排期查询结果")
                    title_label = "史诗编号" if is_epic_query else "需求编号"
                    print(f"{title_label}: **{req_id}**\n")
                    if is_epic_query:
                        print("| 序号 | 史诗编号 | 需求编号 | Story 编号 | 当前计划生产排期 |")
                        print("| :--- | :--- | :--- | :--- | :--- |")
                        for idx, r in enumerate(query_results, 1):
                            print(f"| {idx} | {req_id} | {format_demand_link(r['req_id'])} | {r['storyCode']} | {r['planDate'] or '空'} |")
                    else:
                        print("| 序号 | 需求编号 | Story 编号 | 当前计划生产排期 |")
                        print("| :--- | :--- | :--- | :--- |")
                        for idx, r in enumerate(query_results, 1):
                            print(f"| {idx} | {format_demand_link(r['req_id'])} | {r['storyCode']} | {r['planDate'] or '空'} |")
                    print("RESULT_MARKDOWN_END")
                finally:
                    await bootstrap_page.close()
                return

            # 2. 分片并行处理
            chunks = partition_list(records, concurrency)
            print(f"[调度] 已将 {len(records)} 条需求划分为 {len(chunks)} 个并行任务组...")
            
            results = []
            tasks = []
            for i, chunk in enumerate(chunks, 1):
                if i == 1:
                    # 第一个 worker 复用已登录并加载好网格的 bootstrap_page
                    tasks.append(run_worker(i, chunk, context, results, existing_page=bootstrap_page))
                else:
                    tasks.append(run_worker(i, chunk, context, results))
            
            await asyncio.gather(*tasks)

            # 更新缓存文件以保持其有效且包含最新数据，而不是直接删除它（避免下次查询需要重新下载数兆字节的数据）
            if os.path.exists(CACHE_FILE):
                try:
                    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                        cache_rows = json.load(f)
                    
                    updated_count = 0
                    for r in results:
                        if r.get("storyCode") in ("未找到 Story", "运行异常"):
                            continue
                        row_id = r.get("rowId")
                        if row_id:
                            for crow in cache_rows:
                                if str(crow.get("rowId")) == str(row_id):
                                    crow["planProdLineDate"] = r["target_date"]
                                    updated_count += 1
                                
                    if updated_count > 0:
                        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                            json.dump(cache_rows, f, ensure_ascii=False, indent=2)
                        print(f"[API] 检测到修改操作，已成功在本地缓存中更新了 {updated_count} 条记录，避免下次查询重载大宽表数据。")
                    else:
                        os.remove(CACHE_FILE)
                        print("[API] 检测到修改操作，但本地缓存未匹配到对应行，已清除本地缓存文件以确保下次拉取最新数据。")
                except Exception as e:
                    try:
                        os.remove(CACHE_FILE)
                    except Exception:
                        pass
                    print(f"[API] 更新本地缓存时发生异常 ({e})，已清除本地缓存以确保数据准确性。")

            # 保存 session 状态
            try:
                await context.storage_state(path=SESSION_FILE)
            except Exception:
                pass

            # 3. 批量持久化校验 (一次性并行重载比对)
            all_success = True
            if args.verify and results:
                print("\n[校验] 对所有已修改记录进行批量并发持久化校验...")
                
                # 获取需要验证的去重需求号列表
                unique_req_ids = list(set(r["req_id"] for r in results if r["storyCode"] not in ("未找到 Story", "运行异常")))
                
                if unique_req_ids:
                    # 优先尝试通过直接接口极速校验，失败则降级为浏览器校验
                    print("[校验] 正在尝试通过直接接口进行极速校验...")
                    api_verified = True
                    verification_map_api = {}
                    for v_req_id in unique_req_ids:
                        api_results, err, _ = query_schedule_via_api(v_req_id, no_cache=True)
                        if err is None and api_results is not None:
                            for r_api in api_results:
                                if r_api.get("rowId"):
                                    verification_map_api[r_api["rowId"]] = {
                                        "planDate": r_api["planDate"],
                                        "storyCode": r_api["storyCode"]
                                    }
                        else:
                            print(f"[校验] 极速接口校验不可用 ({err or '未返回数据'})，将使用浏览器模式降级校验...")
                            api_verified = False
                            break
                            
                    if api_verified:
                        print("[校验] 极速接口校验完成。")
                        
                        # 尝试最多 3 次拉取（应对后台数据库同步延迟）
                        for attempt in range(1, 4):
                            all_success = True
                            for r in results:
                                if r["storyCode"] in ("未找到 Story", "运行异常"):
                                    continue
                                matched_info = None
                                # 优先根据 storyCode 匹配，其次根据 rowId 匹配
                                for k, v in verification_map_api.items():
                                    if v.get("storyCode") == r["storyCode"] or str(k) == str(r.get("rowId")):
                                        matched_info = v
                                        break
                                if matched_info:
                                    r["persisted"] = matched_info["planDate"]
                                    if matched_info.get("storyCode") and r["storyCode"] in ("未知Story", "Story"):
                                        r["storyCode"] = matched_info["storyCode"]
                                    if r["persisted"] == r["target_date"]:
                                        r["verify_ok"] = True
                                    else:
                                        r["verify_ok"] = False
                                        all_success = False
                                else:
                                    r["verify_ok"] = False
                                    all_success = False
                                    
                            if all_success or attempt == 3:
                                break
                                
                            print(f"[校验] ⚠️ 检测到部分修改尚未同步至 API (尝试 {attempt}/3)，等待 4 秒后重试...")
                            await asyncio.sleep(4)
                            
                            # 重新抓取
                            verification_map_api = {}
                            for v_req_id in unique_req_ids:
                                api_results, err, _ = query_schedule_via_api(v_req_id, no_cache=True)
                                if err is None and api_results is not None:
                                    for r_api in api_results:
                                        if r_api.get("rowId"):
                                            verification_map_api[r_api["rowId"]] = {
                                                "planDate": r_api["planDate"],
                                                "storyCode": r_api["storyCode"]
                                            }

                        print("\n[结果校验]")
                        for r in results:
                            if r["storyCode"] in ("未找到 Story", "运行异常"):
                                continue
                            matched_info = None
                            for k, v in verification_map_api.items():
                                if v.get("storyCode") == r["storyCode"] or str(k) == str(r.get("rowId")):
                                    matched_info = v
                                    break
                            if matched_info:
                                r["persisted"] = matched_info["planDate"]
                                if matched_info.get("storyCode") and r["storyCode"] in ("未知Story", "Story"):
                                    r["storyCode"] = matched_info["storyCode"]
                                if r["persisted"] == r["target_date"]:
                                    print(f"  - 需求 {r['req_id']} | Story {r['storyCode']}: ✅ 校验成功 (数据库值: {r['persisted']})")
                                else:
                                    print(f"  - 需求 {r['req_id']} | Story {r['storyCode']}: ❌ 校验失败 (期望: {r['target_date']}, 数据库值: {r['persisted']})")
                                    all_success = False
                            else:
                                r["persisted"] = "数据库未找到"
                                print(f"  - 需求 {r['req_id']} | Story {r['storyCode']}: ❌ 校验失败 (数据库中未找到该 Story)")
                                all_success = False
                    else:
                        # 降级：启动浏览器并发重载校验
                        verification_map = {}
                        verifier_chunks = partition_list(unique_req_ids, concurrency)
                        
                        verifier_tasks = []
                        for i, v_chunk in enumerate(verifier_chunks, 1):
                            verifier_tasks.append(run_verifier(i, v_chunk, context, verification_map))
                        
                        await asyncio.gather(*verifier_tasks)
                        
                        print("\n[结果校验 (浏览器降级模式)]")
                        for r in results:
                            if r["storyCode"] in ("未找到 Story", "运行异常"):
                                continue
                            key = r.get("rowId")
                            if key in verification_map:
                                r["persisted"] = verification_map[key]
                                if r["persisted"] == r["target_date"]:
                                    print(f"  - 需求 {r['req_id']} | Story {r['storyCode']}: ✅ 校验成功 (数据库值: {r['persisted']})")
                                else:
                                    print(f"  - 需求 {r['req_id']} | Story {r['storyCode']}: ❌ 校验失败 (期望: {r['target_date']}, 数据库值: {r['persisted']})")
                                    all_success = False
                            else:
                                r["persisted"] = "重载未找到"
                                print(f"  - 需求 {r['req_id']} | Story {r['storyCode']}: ❌ 校验失败 (重新加载后未找到对应 Story 行)")
                                all_success = False
                else:
                    print("\n[校验] 没有需要验证的有效记录。")
            else:
                if not args.verify:
                    print("\n[提示] 未开启持久化校验（可添加 --verify 参数启用）。")

            # 输出总结
            elapsed = time.time() - overall_t0
            print(f"\n==================================================")
            if not args.verify:
                print(f"  🎉 修改批处理已完成！(总耗时 {elapsed:.1f}s)")
            elif all_success:
                print(f"  🎉 修改批处理完成且校验全部成功！(总耗时 {elapsed:.1f}s)")
            else:
                print(f"  ⚠️ 修改批处理完成，但部分记录校验未通过，请检查日志 (总耗时 {elapsed:.1f}s)")
            print(f"==================================================")
            
            # 以 markdown 格式输出，方便主 Agent 呈现
            print("\nRESULT_MARKDOWN_START")
            print(f"### 计划生产排期修改结果汇总")
            if is_batch_mode:
                print(f"数据来源: Excel 批量修改 | 目标并发度: **{concurrency}** | 修改记录数: **{len(results)}** 条\n")
            else:
                title_label = "史诗编号" if (req_id.startswith("E") or req_id.startswith("PG")) else "需求编号"
                print(f"单笔修改模式 | {title_label}: **{records[0]['req_id']}** | 目标日期: **{records[0]['target_date']}**\n")
                
            is_epic_run = any((r.get("req_id", "").startswith("E") or r.get("req_id", "").startswith("PG")) for r in results)
            if is_epic_run:
                print("| 序号 | 史诗编号 | 需求编号 | Story 编号 | 修改前排期 | 修改后 (内存) | 持久化校验 | 状态 |")
                print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
                for idx, r in enumerate(results, 1):
                    if r["storyCode"] in ("未找到 Story", "运行异常"):
                        status_icon = r.get("status", "❌ 失败")
                    elif not args.verify:
                        status_icon = "✅ 已更新"
                    else:
                        status_icon = "✅ 成功" if r.get("persisted") == r["target_date"] else "❌ 失败"
                    print(f"| {idx} | {r['req_id']} | {format_demand_link(r.get('demand_id'))} | {r['storyCode']} | {r['before'] or '空'} | {r['after'] or '空'} | {r['persisted'] or '空'} | {status_icon} |")
            else:
                print("| 序号 | 需求编号 | Story 编号 | 修改前排期 | 修改后 (内存) | 持久化校验 | 状态 |")
                print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
                for idx, r in enumerate(results, 1):
                    if r["storyCode"] in ("未找到 Story", "运行异常"):
                        status_icon = r.get("status", "❌ 失败")
                    elif not args.verify:
                        status_icon = "✅ 已更新"
                    else:
                        status_icon = "✅ 成功" if r.get("persisted") == r["target_date"] else "❌ 失败"
                    print(f"| {idx} | {format_demand_link(r['req_id'])} | {r['storyCode']} | {r['before'] or '空'} | {r['after'] or '空'} | {r['persisted'] or '空'} | {status_icon} |")
            print("RESULT_MARKDOWN_END")

        except Exception as e:
            print(f"\n❌ 执行过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            await browser.close()

def main():
    try:
        asyncio.run(main_async())
    except SystemExit:
        pass
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # 显式刷新标准输出与错误日志缓冲区
        sys.stdout.flush()
        sys.stderr.flush()
        # 强制调用 os._exit(0) 彻底杀掉后台 Python 进程及 Playwright 异步线程，防止任务卡在后台
        os._exit(0)

if __name__ == "__main__":
    main()

