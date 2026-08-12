#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
filter_demand.py — Fintech 需求管理页面筛选工具 v4
筛选条件：我受理的 + 状态排除已上线/终止 + 已提交OA=未提交 + 按状态排序
用法：python filter_demand.py [--output result.md]
"""

import argparse
import os
import time
import json
import re
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

import sys

def decrypt_password(enc_str, key_path='~/.workbuddy/.meeting_skill_key'):
    """解密存储在代码中的加密密码"""
    if not enc_str or not isinstance(enc_str, str):
        return ""
    if not enc_str.startswith('ENC:'):
        return enc_str
    kp = os.path.expanduser(key_path)
    if not os.path.exists(kp):
        return enc_str
    try:
        from cryptography.fernet import Fernet
        with open(kp, 'rb') as f:
            key = f.read()
        fern = Fernet(key)
        return fern.decrypt(enc_str[4:].encode('utf-8')).decode('utf-8')
    except Exception:
        return enc_str

def load_credentials():
    username = os.environ.get("PLATFORM_USERNAME") or os.environ.get("FINTECH_USERNAME") or ""
    password = os.environ.get("PLATFORM_PASSWORD") or os.environ.get("FINTECH_PASSWORD") or ""
    platform_url = os.environ.get("PLATFORM_URL") or "https://fintech.gtht.com.cn"

    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_root = os.path.dirname(script_dir)

    config_paths = [
        os.path.join(os.getcwd(), "config.json"),
        os.path.join(skill_root, "config.json"),
        os.path.join(script_dir, "config.json"),
        "/Volumes/Macintosh HD_Data/WorkBuddy/需求管理/config.json",
        os.path.expanduser("~/.workbuddy/config.json"),
    ]

    for p in config_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    creds = json.load(f)
                    u = str(creds.get("username", "")).strip()
                    p_plain = str(creds.get("password", "")).strip()
                    p_enc = str(creds.get("password_encrypted", "")).strip()
                    url_val = str(creds.get("platform_url", "")).strip()

                    if url_val:
                        platform_url = url_val.rstrip("/")
                    if u and u not in ("YOUR_USERNAME", "你的工号") and not username:
                        username = u

                    if not password:
                        if p_plain and p_plain not in ("YOUR_PASSWORD", "YOUR_PLAIN_PASSWORD", "你的登录密码", "密码"):
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
LOGIN_URL = f"{PLATFORM_URL}/kjpt/user/login"
DEMAND_URL = f"{PLATFORM_URL}/kjpt/DemandManage/main"
BASE = PLATFORM_URL
SESSION_FILE = "/Volumes/Macintosh HD_Data/WorkBuddy/需求管理/.fintech_session.json"


def ensure_login(context, page):
    """确保登录态有效。已有 session 则复用，否则执行登录并保存"""
    print("[登录]", end=" ", flush=True)

    # 尝试加载已有 session
    if os.path.exists(SESSION_FILE):
        try:
            page.goto(DEMAND_URL, wait_until="domcontentloaded", timeout=15000)
            # 动态等待，检查是否加载了需求管理页面，或者跳转到了登录页面
            page.wait_for_selector('input[placeholder*="工号"], .ant-table-tbody, label:has-text("受理人"), .selectInputStyle___3Nayz', timeout=10000)
            if page.locator('label:has-text("受理人"), .selectInputStyle___3Nayz').first.count() > 0:
                print("已有登录态，跳过")
                return
        except Exception:
            pass

    # 需要登录
    print("登录中...", end=" ", flush=True)
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector('input[placeholder*="工号"]', timeout=8000)
    except PWTimeout:
        pass
    page.locator('input[placeholder*="工号"]').fill(USERNAME)
    page.locator('input[placeholder*="密码"]').fill(PASSWORD)
    page.locator('button:has-text("提 交")').click()
    
    # 动态等待，直到成功进入需求管理页面
    try:
        page.wait_for_selector('label:has-text("受理人"), .selectInputStyle___3Nayz', timeout=20000)
    except Exception:
        pass

    # 保存 session
    try:
        context.storage_state(path=SESSION_FILE)
        print("完成（session 已保存）")
    except Exception as e:
        print(f"完成（session 保存失败: {e}）")


def apply_all_filters(page):
    """
    v6: 优化性能与可靠性。使用动态等待替换固定 time.sleep，精细化筛选“待受理”、“待拆分”、“技术评估”。
    """
    print("[筛选]")

    # 只有当当前 URL 不是 DEMAND_URL 且页面上没有“受理人”或“更多”等页面特征元素时，才进行导航以节省时间
    if "DemandManage/main" not in page.url or page.locator('label:has-text("受理人"), .selectInputStyle___3Nayz').count() == 0:
        page.goto(DEMAND_URL, wait_until="domcontentloaded", timeout=60000)
    
    # 动态等待页面主要元素加载
    try:
        page.wait_for_selector('label:has-text("受理人"), .selectInputStyle___3Nayz', timeout=10000)
    except Exception:
        pass

    # 1. 选择「我受理的」范围下拉框
    scope_select = None
    selects = page.locator('.ant-select')
    select_count = selects.count()
    for i in range(select_count):
        try:
            sel = selects.nth(i)
            txt = sel.inner_text().strip()
            if any(keyword in txt for keyword in ['我受理的', '我部门提出的', '我提出的', '全部']):
                scope_select = sel
                break
        except Exception:
            pass
            
    if not scope_select:
        # 兜底：使用原来的 selectInputStyle___3Nayz 第一项
        scope_select = page.locator('.selectInputStyle___3Nayz').first
        
    try:
        current_val = scope_select.inner_text().strip()
        if "我受理的" not in current_val:
            scope_select.click()
            dd = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)')
            dd.wait_for(state='visible', timeout=5000)
            dd.locator('.ant-select-item-option', has_text='我受理的').first.click()
            dd.wait_for(state='hidden', timeout=3000)
            print("  1. 选择「我受理的」范围 ✓")
        else:
            print("  1. 范围已是「我受理的」 ✓")
    except Exception as e:
        print(f"  1. 选择「我受理的」异常: {e}，将通过后处理兜底")
        
    # 动态等待可能产生的 loading 消失
    try:
        page.wait_for_selector('.ant-spin-spinning', state='hidden', timeout=5000)
    except Exception:
        pass

    # 2. 清空所有已填写的 input（关键：上次残留的 R2605250074 等）
    inputs = page.locator('.ant-form-item input.ant-input')
    count = inputs.count()
    for i in range(count):
        try:
            inp = inputs.nth(i)
            inp.click()
            inp.fill("")
        except Exception:
            pass
    print(f"  2. 清空 {count} 个输入框")

    # 3. 展开"更多"面板
    oa_label = page.locator('label:has-text("已提交OA")').first
    is_expanded = oa_label.count() > 0 and oa_label.is_visible()
    
    if not is_expanded:
        more_buttons = page.locator('button:has-text("更多")')
        btn_count = more_buttons.count()
        print(f"  找到 {btn_count} 个 '更多' 按钮，尝试展开面板...")
        for i in range(btn_count):
            try:
                more_buttons.nth(i).click()
                time.sleep(1.5)
                if oa_label.count() > 0 and oa_label.is_visible():
                    print(f"  3. 更多面板已展开 (点击第 {i} 个按钮成功) ✓")
                    is_expanded = True
                    break
                else:
                    # 恢复状态
                    more_buttons.nth(i).click()
                    time.sleep(0.5)
            except Exception:
                pass
        if not is_expanded:
            print("  3. 更多展开状态不确定，继续...")
    else:
        print("  3. 更多面板已处于展开状态 ✓")

    # 4. 状态筛选：选择 "待受理", "待拆分", "技术评估"
    try:
        # 使用 placeholder 定位状态下拉框
        status_select = page.locator('.ant-select').filter(has=page.locator('.ant-select-selection-placeholder:has-text("请选择状态")')).first
        status_select.scroll_into_view_if_needed()
        
        # 如果有清除按钮则清除已有选项
        clear_btn = status_select.locator('.ant-select-clear')
        if clear_btn.count() > 0 and clear_btn.is_visible():
            clear_btn.click()
            time.sleep(0.3)
            
        status_select.click()
        dd = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)')
        dd.wait_for(state='visible', timeout=3000)

        # 依次点击选择目标状态
        for name in ['待受理', '待拆分', '技术评估', '讨论中']:
            try:
                option = dd.locator('.ant-select-item-option').filter(has_text=name).first
                option.scroll_into_view_if_needed(timeout=2000)
                option.click(timeout=2000)
                time.sleep(0.1)
                print(f"    选择状态: {name} ✓")
            except Exception as e:
                print(f"    选择状态: {name} 失败: {e}")

        # Close dropdown
        try:
            page.keyboard.press("Escape")
            page.locator('label').first.click(timeout=1000)
        except Exception:
            pass
        try:
            dd.wait_for(state='hidden', timeout=2000)
        except Exception:
            pass
        print("  4. 状态筛选完成（待受理、待拆分、技术评估、讨论中）")
    except Exception as e:
        print(f"  4. 状态筛选异常: {e}，将通过后处理兜底")

    # 5. 已提交OA
    print("  5. 跳过 OA 筛选（不限制 OA 状态，以确保待拆分和技术评估能完整输出） ✓")

    # 6. 收起「更多」面板（避免遮挡）
    try:
        oa_label = page.locator('label:has-text("已提交OA")').first
        if oa_label.count() > 0 and oa_label.is_visible():
            more_buttons = page.locator('button:has-text("更多")')
            btn_count = more_buttons.count()
            for i in range(btn_count):
                try:
                    more_buttons.nth(i).click()
                    time.sleep(1)
                    if oa_label.count() == 0 or not oa_label.is_visible():
                        print("  6. 更多面板已收起 ✓")
                        break
                    else:
                        more_buttons.nth(i).click()
                        time.sleep(0.5)
                except Exception:
                    pass
    except Exception:
        pass

    # 7. 查询
    page.locator('button:has-text("查 询")').first.click()
    
    # 动态等待表格数据加载完成
    try:
        page.wait_for_selector('.ant-spin-spinning', state='hidden', timeout=10000)
    except Exception:
        pass
    try:
        page.wait_for_selector('.ant-table-tbody tr.ant-table-row, .ant-table-placeholder, .ant-empty', timeout=5000)
    except Exception:
        pass
    print("  7. 查询完成")


def extract_raw_rows(page):
    """提取所有表格行原始数据"""
    js = """
    () => {
        const rows = document.querySelectorAll('.ant-table-tbody tr.ant-table-row');
        const data = [];
        rows.forEach(row => {
            const cells = row.querySelectorAll('td');
            const rowData = [];
            cells.forEach(cell => {
                const link = cell.querySelector('a');
                rowData.push({
                    text: (cell.textContent || '').trim(),
                    href: link ? link.href : ''
                });
            });
            data.push(rowData);
        });
        return JSON.stringify(data);
    }
    """
    raw = page.evaluate(js)
    return json.loads(raw)


def parse_demand_row(row_cells):
    """
    智能解析一行数据：通过内容模式识别各列。
    Ant Design表格列顺序在不同视图中可能不同。
    使用模式匹配而非固定索引。
    """
    result = {
        '需求编号': '',
        '需求名称': '',
        '状态': '',
        '受理进度': '',
        '优先级': '',
        '提交人': '',
        '受理部门': '',
        '需求类型': '',
        '创建日期': '',
        '期望日期': '',
        '计划上线日期': '',
        '处理人': '',
        '受理人': '',
        '提交OA': '',
        'OA状态': '',
        '链接': '',
    }

    texts = [c['text'] for c in row_cells]
    hrefs = [c['href'] for c in row_cells]
    demand_id_idx = -1

    for i, (txt, href) in enumerate(zip(texts, hrefs)):
        # 需求编号：R开头+数字
        if re.match(r'^R\d{8,12}$', txt):
            result['需求编号'] = txt
            result['链接'] = href or f"{BASE}/kjpt/DemandManage/details?demandId={txt}"
            demand_id_idx = i

        # 日期格式
        elif re.match(r'^\d{4}-\d{2}-\d{2}$', txt):
            if not result['创建日期']:
                result['创建日期'] = txt
            elif not result['期望日期']:
                result['期望日期'] = txt

        # OA状态
        elif txt in ('未提交', '已提交', '审批中', '已审批', '已驳回'):
            result['OA状态'] = txt

        # 状态值
        elif txt in ('待受理', '处理中', '暂存中', '已上线', '终止',
                     '待开发', '开发中', 'SIT测试中', 'UAT测试中', '验收中',
                     '待SIT测试', '待UAT测试', '待验收', '已完成', '上线中',
                     'SIT测试完成', 'UAT测试完成', '验收完成',
                     '待提测', '提测中', '待拆分', '讨论中', '技术评估'):
            if not result['状态']:
                result['状态'] = txt
            elif not result['受理进度']:
                result['受理进度'] = txt
            elif result['提交OA'] and not txt:
                pass
            else:
                result['受理进度'] = txt

        # 受理进度（与状态可能相同）
        elif txt in ('不统计', '/'):
            result['计划上线日期'] = txt

        # 优先级
        elif re.match(r'^P[0-4]$', txt):
            result['优先级'] = txt

        # 需求类型
        elif txt in ('标准需求', '设计需求', 'Story需求', 'Task需求', 'Bug需求'):
            result['需求类型'] = txt

        # 受理人（姓名-工号格式）
        elif re.match(r'.+-\d+$', txt) and len(txt) < 20:
            result['受理人'] = txt
            if not result['处理人']:
                result['处理人'] = txt

        # 提交人/部门：2-4个中文名
        elif re.match(r'^[\u4e00-\u9fff]{2,4}$', txt) and len(txt) <= 4:
            if not result['提交人']:
                result['提交人'] = txt
            else:
                result['处理人'] = txt

        # 部门：以"部"结尾
        elif txt.endswith('部') and len(txt) <= 10:
            if not result['受理部门']:
                result['受理部门'] = txt

        # 提交OA状态值
        elif txt in ('待受理', '处理中', '已处理'):
            if not result['提交OA']:
                result['提交OA'] = txt

    # 状态优先使用"状态"字段，如果没有则用"受理进度"
    if not result['状态'] and result['受理进度']:
        result['状态'] = result['受理进度']

    # 需求名称：取需求编号下一个未知的、较长的文本
    if demand_id_idx >= 0 and demand_id_idx + 1 < len(texts):
        next_txt = texts[demand_id_idx + 1]
        if next_txt and len(next_txt) > 4 and not re.match(r'^(R\d+|P\d|待|已|终|开|SIT|UAT|验收|上|完成|不统|/\s*$)', next_txt):
            result['需求名称'] = next_txt
        elif demand_id_idx + 2 < len(texts):
            # 可能中间隔了一个空列
            next_txt2 = texts[demand_id_idx + 2]
            if next_txt2 and len(next_txt2) > 4 and not re.match(r'^(R\d+|P\d|待|已|终|开|SIT|UAT|验收|上|完成|不统|/\s*$)', next_txt2):
                result['需求名称'] = next_txt2

    return result


def extract_and_parse(page):
    """提取并解析所有行"""
    rows = extract_raw_rows(page)
    print(f"[提取] 原始行数: {len(rows)}")

    results = []
    for row_data in rows:
        parsed = parse_demand_row(row_data)
        if parsed['需求编号']:
            results.append(parsed)

    print(f"[提取] 解析得: {len(results)} 条")
    return results


def apply_post_filters(results):
    """后处理筛选：只保留状态是 待受理、待拆分、技术评估、讨论中"""
    target_statuses = ('待受理', '待拆分', '技术评估', '讨论中')
    filtered = [r for r in results if r['状态'] in target_statuses]
    print(f"[筛选] 保留指定状态后: {len(filtered)} 条")

    # 按状态优先级排序 (待受理 -> 讨论中 -> 待拆分 -> 技术评估)，组内按需求编号升序
    status_order = {
        '待受理': 0,
        '讨论中': 1,
        '待拆分': 2,
        '技术评估': 3,
    }
    
    def get_sort_key(item):
        status = item.get('状态', '')
        s_val = status_order.get(status, 99)
        
        id_str = item.get('需求编号', '')
        match = re.search(r'\d+', id_str)
        id_val = int(match.group()) if match else 9999999999
        
        return (s_val, id_val)
        
    filtered.sort(key=get_sort_key)
    return filtered


def format_output(results):
    lines = []
    lines.append("")
    lines.append("=" * 80)
    lines.append("  Fintech 需求管理 — 筛选结果")
    lines.append("  条件：我受理的 | 状态是「待受理」「待拆分」「技术评估」「讨论中」 | 按状态分类排序（待受理->讨论中->待拆分->技术评估，组内升序）")
    lines.append("=" * 80)
    lines.append("")

    if not results:
        lines.append("  **无匹配结果**")
        return "\n".join(lines)

    # 分布统计
    status_dist = {}
    for r in results:
        s = r['状态'] or '未知状态'
        status_dist[s] = status_dist.get(s, 0) + 1

    lines.append(f"  **共 {len(results)} 条需求**")
    lines.append("")
    if status_dist:
        lines.append("  按状态分布：")
        for s, c in sorted(status_dist.items()):
            lines.append(f"    {s}: {c}条")
    lines.append("")
    lines.append("-" * 80)
    lines.append("")

    for i, r in enumerate(results, 1):
        lines.append(f"  **{i}. [{r['需求编号']}]({r['链接']}) {r['需求名称']}**")
        lines.append(f"    　状态：{r['状态']}　|　优先级：{r['优先级']}　|　类型：{r['受理部门'] or r['需求类型']}")
        lines.append(f"    　提交人：{r['提交人']}　|　创建日期：{r['创建日期']}")
        lines.append(f"    　受理人/处理人：{r['受理人'] or r['处理人']}")
        lines.append(f"    　OA状态：{r['OA状态']}")
        lines.append(f"    　链接：{r['链接']}")
        lines.append("")

    lines.append("-" * 80)
    lines.append(f"  **总计：{len(results)} 条需求**")
    lines.append("=" * 80)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Fintech 需求筛选工具")
    parser.add_argument("--output", default="filter_results.md", help="输出文件路径")
    parser.add_argument("--browser", default="firefox", choices=["firefox", "chromium"],
                        help="浏览器引擎（默认 firefox，macOS Sequoia Sandbox 下 chromium 不可用）")
    parser.add_argument("--cdp", default=None, metavar="URL",
                        help="CDP 连接地址（如 http://localhost:9222），连接已运行的 Chrome")
    parser.add_argument("--headed", action="store_true", help="是否以有界面模式运行（默认无界面）")
    args = parser.parse_args()

    print("=" * 50)
    mode_label = f"CDP ({args.cdp})" if args.cdp else f"{args.browser} ({'有界面' if args.headed else '无界面'})"
    print(f"  Fintech 需求筛选工具 v5 ({mode_label})")
    print("=" * 50)

    with sync_playwright() as p:
        browser = None
        try:
            if args.cdp:
                browser = p.chromium.connect_over_cdp(args.cdp)
                context = browser.contexts[0] if browser.contexts else browser.new_context(
                    viewport={"width": 1440, "height": 900},
                    locale="zh-CN"
                )
                page = context.new_page() if not context.pages else context.pages[0]
            elif args.browser == "firefox":
                browser = p.firefox.launch(headless=not args.headed)
                context = browser.new_context(
                    viewport={"width": 1440, "height": 900},
                    locale="zh-CN",
                    storage_state=SESSION_FILE if os.path.exists(SESSION_FILE) else None
                )
                page = context.new_page()
            else:
                browser = p.chromium.launch(
                    headless=not args.headed,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                context = browser.new_context(
                    viewport={"width": 1440, "height": 900},
                    locale="zh-CN",
                    storage_state=SESSION_FILE if os.path.exists(SESSION_FILE) else None
                )
                page = context.new_page()

            ensure_login(context, page)
            apply_all_filters(page)
            results = extract_and_parse(page)
            results = apply_post_filters(results)
            output = format_output(results)

            print(output)

            # 保存
            out_file = args.output
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"\n[完成] 结果: {out_file}")

        except Exception as e:
            print(f"\n[错误] {e}")
            import traceback
            traceback.print_exc()
        finally:
            if browser:
                browser.close()


if __name__ == "__main__":
    main()
