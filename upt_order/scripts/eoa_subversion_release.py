# -*- coding: utf-8 -*-
# EOA117 子版本上线发布 - 通用自动填报 v17.0
# 支持系统：集中交易系统 (jzjy)、交易参数管理后台 (cszx)、95信创域 (95xinchuang)、98创新域 (98chuangxin) 等

import json, time as real_time, traceback, sys, os, re, io, argparse
from datetime import date, datetime, timedelta
from playwright.sync_api import sync_playwright

# Override time.sleep dynamically to scale down static delays safely
def custom_sleep(seconds):
    if seconds >= 4.0:
        real_time.sleep(seconds * 0.6)  # Scale down long redirect/login waits
    elif seconds >= 2.0:
        real_time.sleep(seconds * 0.75) # Scale down popup opening waits
    else:
        real_time.sleep(seconds * 0.85) # Very safe delay for input/click state sync

class TimeWrapper:
    def __getattr__(self, name):
        if name == 'sleep':
            return custom_sleep
        return getattr(real_time, name)

time = TimeWrapper()

# 强制 UTF-8 编码，且开启行缓冲，确保后台执行时输出实时刷新
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

USERNAME = config["account"]["username"]
PASSWORD = config["account"].get("PASSWORD", config["account"].get("password", ""))
VIEWPORT = config["browser"]["viewport"]

# 引入公共 SDK
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COMMON_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', 'common'))
if COMMON_DIR not in sys.path:
    sys.path.append(COMMON_DIR)

try:
    from workbuddy_vault import decrypt_secret
except ImportError:
    def decrypt_secret(s): return s

PASSWORD = decrypt_secret(PASSWORD)

# 加载声明式系统模式配置
PRESETS_FILE = os.path.join(SCRIPT_DIR, "system_presets.json")
SYSTEM_PRESETS = {}
if os.path.exists(PRESETS_FILE):
    try:
        with open(PRESETS_FILE, "r", encoding="utf-8") as f:
            SYSTEM_PRESETS = json.load(f)
    except Exception as e:
        print(f"[WARNING] 无法加载 system_presets.json: {e}")

# Session 复用
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_FILE = os.path.join(SCRIPT_DIR, ".fintech_session.json")
KEYWORD_SIGNAL_FILE = os.path.join(SCRIPT_DIR, "eoa117_keyword_signal.json")

today = date.today()
friday = today + timedelta(days=(4 - today.weekday()) % 7)
SAT_Y, SAT_M, SAT_D = friday.year, friday.month, str(friday.day)
SAT_STR = friday.strftime("%Y-%m-%d")
print(f"[INFO] 目标日期: {SAT_STR} 17:00~20:00")

def safe_wait(p, t=3000):
    try: p.wait_for_load_state("networkidle", timeout=t)
    except: time.sleep(2)

def close_any_dropdown(page):
    """关闭任何打开的下拉/弹窗面板"""
    page.keyboard.press("Escape")
    time.sleep(0.3)


def _ensure_login_v2(page):
    """直开EOA117页面，检测登录状态，未登录则自动登录"""
    EOA_URL = "https://www.gtht.com.cn/flowweb/EOA/EOA117?first=A0001&second=B0005"
    
    # 监听 401/403 错误以判断会话是否已失效
    has_auth_error = []
    def log_response(res):
        if res.status in [401, 403] and "gtht.com.cn" in res.url:
            print(f"  [AuthCheck] 接口返回 {res.status}: {res.url}")
            has_auth_error.append(res.url)
            
    page.on("response", log_response)
    
    page.goto(EOA_URL, timeout=30000)
    
    # Wait for the page to stabilize and handle redirection
    print("[登录] 等待页面加载与权限校验...")
    time.sleep(4)
    safe_wait(page, 5000)

    # Detect page state
    needs_login = False
    reason = "form_page"
    
    for check_i in range(10):
        url = page.url
        has_pwd = page.evaluate("() => !!document.querySelector('input[type=\"password\"]')")
        has_user = page.evaluate("""() => {
            return !![...document.querySelectorAll('input')]
                .find(el => (el.placeholder||'').includes('工号') || (el.placeholder||'').includes('账号') || (el.placeholder||'').includes('125360'));
        }""")
        
        if "login" in url or has_pwd or has_user:
            needs_login = True
            reason = "login_page_detected"
            break
            
        if has_auth_error:
            needs_login = True
            reason = "auth_error_403_detected"
            break
            
        # Verify if form fields are rendered (indicating we are successfully authenticated and on the form page)
        has_form = page.evaluate("() => document.querySelectorAll('.formfield, .ant-form-item').length > 5")
        if has_form:
            needs_login = False
            reason = "form_page_loaded"
            break
            
        time.sleep(1.0)
        
    print(f"[登录] 页面检测结果: needs_login={needs_login}, reason={reason}, URL={page.url}")

    if not needs_login:
        print("[登录] Session有效，已进入表单页面")
        # 移除监听器以节省资源
        try:
            page.remove_listener("response", log_response)
        except:
            pass
        return

    # 需要登录，清理旧的会话和 Cookie 确保登录干净
    print(f"[登录] 需要重新登录，清理旧的会话和 Cookie... (原因: {reason})")
    try:
        page.context.clear_cookies()
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
            print(f"  [Session] 已删除失效的本地会话文件: {SESSION_FILE}")
    except Exception as e:
        print(f"  [Session] 清除旧会话失败: {e}")

    # 执行登录
    print("[登录] 执行自动登录流程...")
    
    # Wait for input fields to be visible
    try:
        page.wait_for_selector('input[type="password"]', timeout=10000)
    except:
        pass
    
    # Fill username
    username_input = page.locator('input[placeholder*="工号"], input[placeholder*="账号"], input[placeholder*="125360"]')
    if username_input.count() == 0:
        username_input = page.locator('input').first
    try:
        username_input.fill(USERNAME)
    except:
        page.keyboard.press("Tab")
        page.keyboard.type(USERNAME)
    time.sleep(0.3)
    
    # Fill password
    try:
        page.locator('input[type="password"]').fill(PASSWORD)
    except:
        page.keyboard.press("Tab")
        page.keyboard.type(PASSWORD)
    time.sleep(0.3)
    
    # Click login button
    for bs in ['button:has-text("登 录")', 'button:has-text("登录")', 'button[type="submit"]']:
        if page.locator(bs).count() > 0:
            page.locator(bs).first.click(timeout=5000)
            break
    else:
        page.keyboard.press("Enter")
        
    time.sleep(4)
    safe_wait(page, 5000)
    time.sleep(1)
    print(f"[登录] 完成 → {page.url}")
    
    # Save login status screenshot
    page.screenshot(path=os.path.join(SCRIPT_DIR, "login_status.png"))
    
    # 移除监听器
    try:
        page.remove_listener("response", log_response)
    except:
        pass
    
    if "login" in page.url:
        print("[登录] 依然在登录页面，尝试获取页面提示信息...")
        err_msg = page.evaluate("""() => {
            const errEl = document.querySelector('.error, [class*="error"], .ant-alert-error, .tips, .message, .ant-message, [role="alert"]');
            return errEl ? errEl.innerText.trim() : '未找到明显报错信息';
        }""")
        print(f"[登录] 页面提示: {err_msg}")


# ============================================================
# 步骤A: 日历选日期 + 键盘输入修正时间
# ============================================================
def fill_datetime_v9(page, picker, field_name, target_time):
    """极速版: force-click → Ctrl+A → 键盘输入 → Tab (跳过日历)"""
    print(f"\n--- {field_name}: {SAT_STR} {target_time} ---")
    try:
        picker.scroll_into_view_if_needed(timeout=2000); time.sleep(0.1)
        picker.click(force=True, timeout=3000)
        time.sleep(0.1)
        page.keyboard.press("Control+a")
        time.sleep(0.05)
        page.keyboard.type(f"{SAT_STR} {target_time}", delay=10)
        time.sleep(0.1)
        page.keyboard.press("Tab")
        time.sleep(0.2)

        val = ""
        try: val = picker.input_value(timeout=1000) or ""
        except: pass
        ok = target_time in val and SAT_STR in val
        print(f"  结果: '{val}' {'✅'if ok else '⚠️'}")
        return ok

    except Exception as e:
        print(f"  ERROR: {e}"); traceback.print_exc(); return False


# ============================================================
# 步骤B: 下拉选择 (增强版)
# ============================================================
def select_option_v9(page, trigger_locator, search_text, option_text,
                     desc="", is_search_filter=False, use_force=False):
    """增强版下拉选择"""
    print(f"\n--- 下拉: {desc} ---")
    try:
        page.keyboard.press("Escape"); time.sleep(0.3)
        trigger_locator.scroll_into_view_if_needed(timeout=2000); time.sleep(0.3)
        if use_force:
            trigger_locator.click(force=True, timeout=4000)
        else:
            trigger_locator.click(timeout=4000)
        print(f"  打开[{desc}]")
        time.sleep(1.0)

        if is_search_filter and search_text:
            si_selectors = [
                ".ant-select-search__field:focus",
                ".ant-cascader-input:focus",
                "input.ant-input:focus",
            ]
            typed = False
            for ss in si_selectors:
                si = page.locator(ss)
                if si.count() > 0 and si.first.is_visible():
                    si.first.fill(""); time.sleep(0.1)
                    si.first.type(search_text, delay=20)
                    typed = True; print(f"  输入: {search_text}")
                    break
            if not typed:
                page.keyboard.type(search_text, delay=20)
                print(f"  键盘输入: {search_text}")
            time.sleep(1.2)

        clicked = False
        if option_text:
            opt_selectors = [
                f"[role='option']:text('{option_text}')",
                f"[role='listbox'] [role='option']:text('{option_text}')",
                f".ant-select-dropdown-option:text('{option_text}')",
                f".ant-cascader-menu-item:text('{option_text}')",
                f"li[role='menuitem']:text('{option_text}')",
                f"text='{option_text}'",
            ]
            for o_sel in opt_selectors:
                opt = page.locator(o_sel).first
                if opt.count() > 0:
                    try:
                        opt.scroll_into_view_if_needed(timeout=1000); time.sleep(0.15)
                        opt.click(force=True, timeout=3000)
                        clicked = True; print(f"  选中: {option_text} ({o_sel[:30]})"); break
                    except:
                        try:
                            opt.evaluate("el => el.click()")
                            clicked = True; print(f"  JS选中: {option_text}"); break
                        except:
                            pass

        if not clicked:
            visible_opts = page.locator(
                "[role='option']:visible, "
                "[class*='dropdown']:visible [class*='option']:visible, "
                "[class*='cascader-menu-item']:visible"
            )
            voc = visible_opts.count()
            print(f"  可见选项数: {voc}")
            if voc > 0:
                try:
                    visible_opts.first.click(force=True, timeout=3000)
                    clicked = True; print(f"  选中第1个可见选项")
                except:
                    try:
                        visible_opts.first.evaluate("el => el.click()")
                        clicked = True; print(f"  JS点第1个可见选项")
                    except:
                        pass

        time.sleep(0.5)
        return clicked

    except Exception as e:
        print(f"  失败: {e}")
        traceback.print_exc()
        return False


# ============================================================
# 步骤C: 变更系统交互式选择
# ============================================================

def search_system_options(page, search_keyword):
    """
    阶段1 - 搜索变更系统并提取选项列表
    """
    print(f"\n{'='*55}")
    print(f'[8] 变更系统搜索: "{search_keyword}" ...')
    print('='*55)

    # C1: 关闭残留面板, 找到变更系统Cascader并点击
    page.keyboard.press("Escape"); time.sleep(0.5)

    sys_result = page.evaluate("""() => {
        const items = document.querySelectorAll('.formfield');
        for(const item of items){
            const lbl = item.querySelector('.fieldlabel');
            if(lbl){
                const txt = lbl.textContent.trim();
                if(txt === '变更系统' || (txt.includes('变更系统') && !txt.includes('分类'))){
                    const casInput = item.querySelector('.ant-cascader-input[placeholder*="搜索"]');
                    if(casInput){ casInput.click(); return 'clicked_cascader_search'; }
                    const casInput2 = item.querySelector('.ant-cascader-input');
                    if(casInput2 && !casInput2.readOnly){ casInput2.click(); return 'clicked_cascader_input'; }
                    const cas = item.querySelector('.ant-cascader-picker');
                    if(cas){ cas.click(); return 'clicked_cascader_picker'; }
                    return 'found_no_clickable';
                }
            }
        }
        return 'not_found';
    }""")
    print(f"  触发变更系统Cascader: {sys_result}")

    if 'clicked' not in str(sys_result):
        print("  ❌ 无法找到变更系统字段!")
        return None, None

    time.sleep(1.5)

    # C2: 在cascader搜索框中输入关键词
    type_result = page.evaluate("""() => {
        const panelSearch = document.querySelector('.ant-cascader-input[placeholder*="搜索"]');
        if(panelSearch && panelSearch.offsetParent !== null){
            panelSearch.focus(); panelSearch.select();
            return {ok:true, source:'panel_search', ph:panelSearch.placeholder};
        }
        const allCasInputs = document.querySelectorAll('.ant-cascader-input');
        for(const inp of allCasInputs){
            if(inp.offsetParent !== null && !inp.readOnly && inp.offsetWidth > 0){
                inp.focus(); inp.select();
                return {ok:true, source:'visible_cascader', ph:(inp.placeholder||'')};
            }
        }
        const focused = document.activeElement;
        if(focused && focused.tagName === 'INPUT' && focused.offsetParent !== null){
            return {ok:true, source:'current_focus', ph:(focused.placeholder||'')};
        }
        return {ok:false, error:'未找到可用的cascader输入框'};
    }""")
    print(f"  搜索框定位: source={type_result.get('source','?')}")

    if type_result.get('ok'):
        page.keyboard.type(search_keyword, delay=50)
        print(f"  ✓ 已输入关键词: '{search_keyword}'")
    else:
        cas_input_locator = page.locator('.ant-cascader-input:visible').first
        if cas_input_locator.count() > 0:
            cas_input_locator.click(timeout=2000)
            time.sleep(0.3)
            page.keyboard.type(search_keyword, delay=50)
            print(f"  ✓ locator备用方案已输入: '{search_keyword}'")
        else:
            print("  ❌ 未找到可输入的搜索框!")
            return None, None

    time.sleep(1.5)

    # C3: 提取所有可见的菜单选项
    options_data = page.evaluate("""() => {
        const results = [];
        const menus = document.querySelectorAll('.ant-cascader-menu');
        menus.forEach((menu, menuIdx) => {
            const items = menu.querySelectorAll('.ant-cascader-menu-item');
            items.forEach((item, itemIdx) => {
                const vis = item.offsetParent !== null;
                const dis = item.classList.contains('ant-cascader-menu-item-disabled');
                const text = (item.textContent || '').trim();
                if(vis && !dis && text){
                    results.push({col: menuIdx, idx: itemIdx, text: text,
                        active: item.classList.contains('ant-cascader-menu-item-active')});
                }
            });
        });
        if(results.length === 0){
            const opts = document.querySelectorAll('[role="option"], [role="treeitem"], li[role="menuitem"]');
            opts.forEach((o, i) => {
                if(o.offsetParent !== null){
                    const t = (o.textContent || '').trim();
                    if(t) results.push({col: 0, idx: i, text: t, active: false});
                }
            });
        }
        return results;
    }""")

    print(f"\n  🔍 搜索 '{search_keyword}' 共找到 {len(options_data)} 个选项")

    if len(options_data) == 0:
        print("  ⚠️ 未找到匹配的变更系统选项!")
        return None, None

    cols_data = {}
    for opt in options_data:
        col = opt['col']
        if col not in cols_data:
            cols_data[col] = []
        cols_data[col].append(opt)

    for col_idx in sorted(cols_data.keys()):
        items = cols_data[col_idx]
        col_name = f"第{col_idx+1}级" if len(cols_data) > 1 else "可选系统"
        print(f"  ── {col_name} ({len(items)}项) ──")
        for i, opt in enumerate(items):
            marker = "▶ " if opt['active'] else "  "
            print(f"    {marker}[{i}] {opt['text']}")

    return cols_data, options_data


def click_system_choice(page, choice_index, first_col_items):
    """阶段2 - 点击第一级用户选择的选项"""
    if choice_index < 0 or choice_index >= len(first_col_items):
        print(f"  ❌ 无效选择: {choice_index}")
        return None

    chosen = first_col_items[choice_index]
    click_result = page.evaluate("""(params) => {
        const colIdx = params.col;
        const itemIdx = params.idx;
        const targetText = params.text;
        const menus = document.querySelectorAll('.ant-cascader-menu');
        if(colIdx < menus.length){
            const menu = menus[colIdx];
            const items = menu.querySelectorAll('.ant-cascader-menu-item');
            if(itemIdx < items.length){
                const target = items[itemIdx];
                target.scrollIntoView({block: 'nearest'});
                target.click();
                return 'clicked:' + target.textContent.trim();
            }
        }
        const allItems = document.querySelectorAll('.ant-cascader-menu-item');
        for(const item of allItems){
            if(item.offsetParent !== null && item.textContent.trim() === targetText){
                item.scrollIntoView({block: 'nearest'});
                item.click(); return 'clicked_text:' + targetText;
            }
        }
        return 'fail';
    }""", {'col': chosen['col'], 'idx': chosen['idx'], 'text': chosen['text']})
    print(f"  ✓ 已点击: {click_result}")
    return click_result


def handle_cascade_selection(page, chosen_text):
    """阶段3 - 处理级联选择(第2级/第3级)"""
    time.sleep(1.5)
    final_selection = chosen_text

    col2_check = page.evaluate("""() => {
        const menus = document.querySelectorAll('.ant-cascader-menu');
        if(menus.length >= 2){
            const col2 = menus[1];
            const items = col2.querySelectorAll('.ant-cascader-menu-item');
            const visibleItems = [];
            items.forEach((item, i) => {
                if(item.offsetParent !== null && !item.classList.contains('ant-cascader-menu-item-disabled')){
                    visibleItems.push({idx: i, text: item.textContent.trim(),
                        active: item.classList.contains('ant-cascader-menu-item-active')});
                }
            });
            return {colCount: menus.length, items: visibleItems};
        }
        return {colCount: menus.length, items: []};
    }""")

    if col2_check['items']:
        col2_items = col2_check['items']
        print(f"\n  ── 第2级选项 ({len(col2_items)}项) ──")
        for i, ci in enumerate(col2_items):
            marker = "▶ " if ci['active'] else "  "
            print(f"    {marker}[{i}] {ci['text']}")
        return {'needs_choice': True, 'level': 2, 'items': col2_items,
                'parent_text': chosen_text, 'final_so_far': chosen_text}

    col3_check = page.evaluate("""() => {
        const menus = document.querySelectorAll('.ant-cascader-menu');
        if(menus.length >= 3){
            const col3 = menus[2];
            const items = col3.querySelectorAll('.ant-cascader-menu-item');
            const vis = [];
            items.forEach((item, i) => {
                if(item.offsetParent !== null && !item.classList.contains('ant-cascader-menu-item-disabled')){
                    vis.push({idx: i, text: item.textContent.trim()});
                }
            });
            return vis;
        }
        return [];
    }""")

    if col3_check:
        print(f"\n  ── 第3级选项 ({len(col3_check)}项) ──")
        for i, ci in enumerate(col3_check):
            print(f"    [{i}] {ci['text']}")
        return {'needs_choice': True, 'level': 3, 'items': col3_check,
                'parent_text': chosen_text, 'final_so_far': final_selection}

    return {'needs_choice': False, 'final_text': final_selection}


def click_cascade_option(page, level, choice_index, cascade_items, current_text):
    """点击级联选项(第2级或第3级)"""
    if choice_index < 0 or choice_index >= len(cascade_items):
        choice_index = 0

    chosen_item = cascade_items[choice_index]

    if level == 2:
        result = page.evaluate("""(params) => {
            const idx = params.idx;
            const menus = document.querySelectorAll('.ant-cascader-menu');
            if(menus.length >= 2){
                const items = menus[1].querySelectorAll('.ant-cascader-menu-item');
                if(idx < items.length){
                    items[idx].scrollIntoView({block: 'nearest'});
                    items[idx].click();
                    return 'col2_clicked:' + items[idx].textContent.trim();
                }
            }
            return 'fail';
        }""", {'idx': chosen_item['idx']})
        print(f"  ✓ 二级已选: {result}")
        new_final = f"{current_text} / {chosen_item['text']}"
    else:
        result = page.evaluate("""(idx) => {
            const menus = document.querySelectorAll('.ant-cascader-menu');
            if(menus.length >= 3){
                const items = menus[2].querySelectorAll('.ant-cascader-menu-item');
                if(idx < items.length){ items[idx].click(); return 'ok'; }
            }
            return 'fail';
        }""", chosen_item['idx'])
        print(f"  ✓ 三级已选: {chosen_item['text']}")
        new_final = f"{current_text} / {chosen_item['text']}"

    time.sleep(1.0)
    next_level = handle_cascade_selection(page, new_final)
    return next_level


# ============================================================
# 步骤D: 下拉/radio/checkbox/文本 字段通用填写 (按fieldlabel定位)
# ============================================================
def fill_dropdown_by_label(page, label_keyword, target_value, desc=""):
    """通过 fieldlabel 定位并选择下拉选项"""
    print(f"\n--- {desc or label_keyword} → {target_value} ---")
    page.keyboard.press("Escape"); time.sleep(0.3)

    click_r = page.evaluate("""(kw) => {
        const items = document.querySelectorAll('.formfield');
        for(const item of items){
            const lbl = item.querySelector('.fieldlabel');
            if(lbl && lbl.textContent.includes(kw)){
                const sel = item.querySelector('.ant-select');
                if(sel){ sel.click(); return 'select_clicked'; }
                const inp = item.querySelector('input:not([type="hidden"])');
                if(inp){ inp.click(); return 'input_clicked'; }
                return 'found_no_action';
            }
        }
        return 'not_found';
    }""", label_keyword)
    print(f"  触发: {click_r}")

    if 'clicked' not in str(click_r):
        print(f"  ⚠ 未找到字段: {label_keyword}")
        return False

    time.sleep(0.8)

    select_r = page.evaluate("""(targetVal) => {
        const opts = document.querySelectorAll(
            '[role="option"], .ant-select-dropdown-menu-item, .ant-select-dropdown li, li[role="menuitem"]'
        );
        const visible = Array.from(opts).filter(o => o.offsetParent !== null);
        // 1. 精确匹配
        for(const o of visible){
            const t = (o.textContent || '').trim();
            if(t === targetVal){ o.click(); return 'exact:' + t; }
        }
        // 2. 包含匹配 (排除否定前缀: 不/非/无)
        const negPrefixes = ['不','非','无','未'];
        for(const o of visible){
            const t = (o.textContent || '').trim();
            if(t.includes(targetVal)){
                const shortText = t.substring(0, 5);
                const isNegated = negPrefixes.some(p => shortText.startsWith(p));
                if(!isNegated){ o.click(); return 'contains:' + t; }
            }
        }
        // 3. 否定项也包含目标词 (兜底, 仅当没有非否定项时)
        for(const o of visible){
            const t = (o.textContent || '').trim();
            if(t.includes(targetVal)){ o.click(); return 'negated_fallback:' + t; }
        }
        // 4. 第一个可见选项
        for(const o of visible){
            o.click();
            return 'first:' + (o.textContent||'').trim().substring(0,30);
        }
        return 'no_option';
    }""", target_value)
    print(f"  选择: {select_r}")
    time.sleep(0.4)
    return 'selected' in str(select_r) or 'first' in str(select_r)


def fill_radio_by_label(page, label_keyword, target_value, desc=""):
    """通过 fieldlabel 定位并选择 radio 选项 (增强版v15)"""
    print(f"\n--- {desc or label_keyword} → {target_value} ---")
    page.keyboard.press("Escape"); time.sleep(0.2)

    diag = page.evaluate("""(kw) => {
        const items = document.querySelectorAll('.formfield');
        for(const item of items){
            const lbl = item.querySelector('.fieldlabel');
            if(lbl && lbl.textContent.includes(kw)){
                const content = item.querySelector('.fieldcontent');
                const radios = item.querySelectorAll('.ant-radio-wrapper');
                const radioTexts = Array.from(radios).map(r => ({
                    text: (r.textContent||'').trim(),
                    vis: r.offsetParent !== null
                }));
                const btnRadios = item.querySelectorAll('.ant-radio-button-wrapper');
                const btnTexts = Array.from(btnRadios).map(r => ({
                    text: (r.textContent||'').trim(),
                    vis: r.offsetParent !== null
                }));
                const sel = item.querySelector('.ant-select');
                return {found: true, label: lbl.textContent.trim(),
                        radioCount: radios.length, radioTexts: radioTexts,
                        btnRadioCount: btnRadios.length, btnTexts: btnTexts,
                        hasSelect: !!sel, hasContent: !!content};
            }
        }
        return {found: false};
    }""", label_keyword)
    print(f"  诊断: {diag}")

    if not diag.get('found'):
        print(f"  ⚠ 未找到含'{label_keyword}'的字段")
        return False

    result = page.evaluate("""(params) => {
        const kw = params.kw;
        const val = params.val;
        const items = document.querySelectorAll('.formfield');
        for(const item of items){
            const lbl = item.querySelector('.fieldlabel');
            if(lbl && lbl.textContent.includes(kw)){
                const radios = item.querySelectorAll('.ant-radio-wrapper');
                for(const r of radios){
                    const t = (r.textContent||'').trim();
                    if(t === val){ r.click(); return 'radio_exact:'+t; }
                }
                const negPrefixes = ['不','非','无'];
                for(const r of radios){
                    const t = (r.textContent||'').trim();
                    if(t.includes(val)){
                        const isNeg = negPrefixes.some(p => t.startsWith(p));
                        if(!isNeg){ r.click(); return 'radio_contains:'+t; }
                    }
                }
                for(const r of radios){
                    const t = (r.textContent||'').trim();
                    if(t.includes(val)){ r.click(); return 'radio_negated:'+t; }
                }

                const btnRadios = item.querySelectorAll('.ant-radio-button-wrapper');
                for(const r of btnRadios){
                    const t = (r.textContent||'').trim();
                    if(t === val || t.includes(val)){ r.click(); return 'btn_radio:'+t; }
                }

                const radioInputs = item.querySelectorAll('.ant-radio input[type="radio"]');
                for(const inp of radioInputs){
                    const parent = inp.closest('.ant-radio-wrapper') || inp.parentElement;
                    const sibling = parent ? parent.querySelector('span:last-child') : null;
                    const t = sibling ? sibling.textContent.trim() : '';
                    if(t === val || t.includes(val)){
                        inp.click(); return 'radio_input:'+t;
                    }
                }

                const sel = item.querySelector('.ant-select');
                if(sel){
                    sel.click();
                    return 'is_select_clicked';
                }

                if(radios.length > 0){
                    radios[0].click(); return 'radio_first:'+radios[0].textContent.trim();
                }
                if(btnRadios.length > 0){
                    btnRadios[0].click(); return 'btn_first:'+btnRadios[0].textContent.trim();
                }
                return 'no_radio';
            }
        }
        return 'label_not_found';
    }""", {'kw': label_keyword, 'val': target_value})
    print(f"  选择: {result}")

    if result == 'is_select_clicked':
        time.sleep(0.8)
        sel_result = page.evaluate("""(val) => {
            const opts = document.querySelectorAll(
                '[role="option"], .ant-select-dropdown-menu-item, .ant-select-dropdown li, li[role="menuitem"]'
            );
            const visible = Array.from(opts).filter(o => o.offsetParent !== null);
            for(const o of visible){
                const t = (o.textContent||'').trim();
                if(t === val || t.includes(val)){ o.click(); return 'selected:'+t; }
            }
            if(visible.length > 0){ visible[0].click(); return 'first:'+visible[0].textContent.trim().substring(0,30); }
            return 'no_option';
        }""", target_value)
        print(f"  下拉选择: {sel_result}")
        time.sleep(0.4)
        return 'selected' in str(sel_result) or 'first' in str(sel_result)

    time.sleep(0.3)
    return 'radio' in str(result) or 'btn' in str(result) or 'selected' in str(result)


def fill_checkbox_by_label(page, label_keyword, target_values_list, desc=""):
    """通过 fieldlabel 定位并勾选多个 checkbox 选项"""
    print(f"\n--- {desc or label_keyword} → {target_values_list} ---")
    page.keyboard.press("Escape"); time.sleep(0.2)

    diag = page.evaluate("""(kw) => {
        const items = document.querySelectorAll('.formfield');
        for(const item of items){
            const lbl = item.querySelector('.fieldlabel');
            if(lbl && lbl.textContent.includes(kw)){
                const cbs = item.querySelectorAll('.ant-checkbox-wrapper');
                const texts = Array.from(cbs).map(c => ({
                    text: (c.textContent||'').trim(),
                    vis: c.offsetParent !== null
                }));
                const sel = item.querySelector('.ant-select');
                const selMode = sel ? (sel.className.includes('ant-select-multi') || sel.querySelector('.ant-select-selection--multiple') ? 'multi' : 'single') : null;
                return {found: true, checkboxCount: cbs.length, texts: texts,
                        hasSelect: !!sel, selectMode: selMode};
            }
        }
        return {found: false};
    }""", label_keyword)
    print(f"  诊断: {diag}")

    result = page.evaluate("""(params) => {
        const kw = params.kw;
        const targets = params.targets;
        const items = document.querySelectorAll('.formfield');
        for(const item of items){
            const lbl = item.querySelector('.fieldlabel');
            if(lbl && lbl.textContent.includes(kw)){
                const cbs = item.querySelectorAll('.ant-checkbox-wrapper');
                const clicked = [];
                for(const target of targets){
                    for(const cb of cbs){
                        const txt = (cb.textContent||'').trim();
                        if(txt === target || txt.includes(target)){
                            const cbInput = cb.querySelector('input[type="checkbox"]');
                            if(cbInput && !cbInput.checked){
                                cb.click();
                                clicked.push('clicked:'+txt);
                            } else if(cbInput && cbInput.checked){
                                clicked.push('already:'+txt);
                            } else {
                                cb.click();
                                clicked.push('js:'+txt);
                            }
                            break;
                        }
                    }
                }
                if(clicked.length > 0) return clicked.join('; ');

                const sel = item.querySelector('.ant-select');
                if(sel){
                    sel.click();
                    return 'is_select_multi';
                }
                return 'no_match_found';
            }
        }
        return 'label_not_found';
    }""", {'kw': label_keyword, 'targets': target_values_list})
    print(f"  勾选: {result}")

    if result == 'is_select_multi':
        time.sleep(0.8)
        try:
            visible_opts = page.evaluate("""() => {
                const opts = document.querySelectorAll('[role="option"], .ant-select-dropdown-menu-item, .ant-select-dropdown li, li[role="menuitem"]');
                return Array.from(opts).filter(o => o.offsetParent !== null).map(o => (o.textContent||'').trim());
            }""")
            print(f"      [DEBUG] Visible dropdown options: {visible_opts}")
        except Exception as de:
            print(f"      [DEBUG] Options query failed: {de}")
            
        for target in target_values_list:
            sel_result = page.evaluate("""(val) => {
                const opts = document.querySelectorAll('[role="option"], .ant-select-dropdown-menu-item, .ant-select-dropdown li, li[role="menuitem"]');
                const visible = Array.from(opts).filter(o => o.offsetParent !== null);
                for(const o of visible){
                    const t = (o.textContent||'').trim();
                    if(t === val || t.includes(val)){
                        o.click();
                        return 'selected:' + t;
                    }
                }
                return 'not_found:' + val;
            }""", target)
            print(f"  多选下拉: {sel_result}")
            time.sleep(0.3)
        time.sleep(0.4)
        return True

    time.sleep(0.4)
    return 'not_found' not in str(result)


def fill_input_by_label(page, label_keyword, value, desc=""):
    """通过 fieldlabel 定位并填写文本输入框"""
    print(f"\n--- {desc or label_keyword} → {value} ---")
    page.keyboard.press("Escape"); time.sleep(0.2)

    diag = page.evaluate("""(kw) => {
        const items = document.querySelectorAll('.formfield');
        for(const item of items){
            const lbl = item.querySelector('.fieldlabel');
            if(lbl && lbl.textContent.includes(kw)){
                const content = item.querySelector('.fieldcontent');
                if(!content) return {found: true, hasContent: false, label: lbl.textContent.trim()};
                const els = Array.from(content.querySelectorAll('*')).filter(e => e.offsetParent !== null).slice(0, 15);
                const elInfo = els.map(e => ({
                    tag: e.tagName,
                    cls: String(e.className).substring(0, 50),
                    type: e.getAttribute('type') || '',
                    placeholder: e.getAttribute('placeholder') || '',
                    ro: e.readOnly,
                    txt: (e.textContent||'').trim().substring(0, 30)
                }));
                const textareas = content.querySelectorAll('textarea');
                const inputs = content.querySelectorAll('input:not([type="hidden"])');
                const selects = content.querySelectorAll('.ant-select');
                const checkboxes = content.querySelectorAll('.ant-checkbox-wrapper');
                const radios = content.querySelectorAll('.ant-radio-wrapper');
                const editables = content.querySelectorAll('[contenteditable="true"], [contenteditable=""]');
                return {found: true, label: lbl.textContent.trim(),
                        hasContent: true,
                        textareaCount: textareas.length,
                        inputCount: inputs.length,
                        selectCount: selects.length,
                        checkboxCount: checkboxes.length,
                        radioCount: radios.length,
                        editableCount: editables.length,
                        elements: elInfo};
            }
        }
        return {found: false};
    }""", label_keyword)
    print(f"  诊断: {diag}")

    result = page.evaluate("""(params) => {
        const kw = params.kw;
        const val = params.val;
        const items = document.querySelectorAll('.formfield');
        for(const item of items){
            const lbl = item.querySelector('.fieldlabel');
            if(lbl && lbl.textContent.includes(kw)){
                const content = item.querySelector('.fieldcontent');
                if(!content) return 'no_content';

                const ta = content.querySelector('textarea');
                if(ta){
                    ta.focus();
                    ta.value = val;
                    ta.dispatchEvent(new Event('input', {bubbles: true}));
                    ta.dispatchEvent(new Event('change', {bubbles: true}));
                    return 'ok_textarea:' + val.substring(0, 30);
                }

                const textInputs = content.querySelectorAll('input[type="text"]:not([readonly]), input:not([type]):not([readonly])');
                for(const inp of textInputs){
                    if(inp.offsetParent !== null){
                        inp.focus();
                        inp.value = val;
                        inp.dispatchEvent(new Event('input', {bubbles: true}));
                        inp.dispatchEvent(new Event('change', {bubbles: true}));
                        return 'ok_input:' + val.substring(0, 30);
                    }
                }

                const sel = content.querySelector('.ant-select');
                if(sel){
                    sel.click();
                    return 'is_select:' + val;
                }

                const editable = content.querySelector('[contenteditable="true"], [contenteditable=""]');
                if(editable){
                    editable.focus();
                    editable.innerHTML = val;
                    editable.dispatchEvent(new Event('input', {bubbles: true}));
                    return 'ok_editable:' + val.substring(0, 30);
                }

                const anyInput = content.querySelector('input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"])');
                if(anyInput && anyInput.offsetParent !== null){
                    anyInput.focus();
                    try { anyInput.removeAttribute('readonly'); } catch(e){}
                    anyInput.value = val;
                    anyInput.dispatchEvent(new Event('input', {bubbles: true}));
                    anyInput.dispatchEvent(new Event('change', {bubbles: true}));
                    return 'ok_forced_input:' + val.substring(0, 30);
                }

                const rendered = content.querySelector('.ant-select-selection__rendered');
                if(rendered){
                    return 'has_rendered_select';
                }

                return 'no_input_found';
            }
        }
        return 'label_not_found';
    }""", {'kw': label_keyword, 'val': value})
    print(f"  填写: {result}")

    if str(result).startswith('is_select:'):
        time.sleep(0.8)
        sel_result = page.evaluate("""(val) => {
            const opts = document.querySelectorAll(
                '[role="option"], .ant-select-dropdown-menu-item, .ant-select-dropdown li, li[role="menuitem"]'
            );
            const visible = Array.from(opts).filter(o => o.offsetParent !== null);
            for(const o of visible){
                const t = (o.textContent||'').trim();
                if(t === val || t.includes(val)){ o.click(); return 'selected:'+t; }
            }
            if(visible.length > 0){ visible[0].click(); return 'first:'+visible[0].textContent.trim().substring(0,30); }
            return 'no_option';
        }""", value)
        print(f"  下拉选择: {sel_result}")
        time.sleep(0.4)
        return 'selected' in str(sel_result) or 'first' in str(sel_result)

    time.sleep(0.3)
    return 'ok' in str(result)


# ============================================================
# 步骤E: 点击保存按钮
# ============================================================
def click_submit_btn_in_toolbar(page, btn_text="保存"):
    """点击页面底部工具栏的「保存」按钮"""
    print(f"\n{'='*55}")
    print(f"[保存] 点击底部「{btn_text}」按钮...")
    print("="*55)

    save_info = page.evaluate("""(btnText) => {
        const walker = document.createTreeWalker(
            document.body,
            NodeFilter.SHOW_TEXT,
            null, false
        );
        const candidates = [];
        let node;
        while(node = walker.nextNode()){
            if(node.textContent.trim() === btnText){
                const parent = node.parentElement;
                if(parent && parent.offsetParent !== null){
                    const rect = parent.getBoundingClientRect();
                    candidates.push({
                        x: rect.left + rect.width / 2,
                        y: rect.top + rect.height / 2,
                        top: rect.top,
                        tag: parent.tagName,
                        cls: parent.className.substring(0, 50)
                    });
                }
            }
        }
        const bottom = candidates.filter(c => c.top > 400);
        if(bottom.length > 0) return bottom[0];
        if(candidates.length > 0) return candidates[0];
        return null;
    }""", btn_text)

    if save_info:
        print(f"  方法1-TreeWalker: 找到按钮 tag={save_info['tag']} y={save_info['top']:.0f}")
        try:
            page.mouse.click(save_info['x'], save_info['y'])
            print(f"  ✅ 方法1 mouse.click 成功!")
            time.sleep(1.0)
            return True
        except Exception as e:
            print(f"  ⚠ 方法1 mouse.click 失败: {e}")

    print("  方法2-JS事件链...")
    result2 = page.evaluate("""(btnText) => {
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
        let node;
        while(node = walker.nextNode()){
            if(node.textContent.trim() === btnText){
                const el = node.parentElement;
                if(el && el.offsetParent !== null){
                    const rect = el.getBoundingClientRect();
                    if(rect.top > 400){
                        ['mousedown','mouseup','click'].forEach(evt => {
                            el.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true}));
                        });
                        return 'js_events_sent:' + el.tagName;
                    }
                }
            }
        }
        return 'not_found';
    }""", btn_text)
    print(f"  方法2结果: {result2}")
    if 'not_found' not in str(result2):
        time.sleep(1.0)
        return True

    print("  方法3-Playwright选择器...")
    selectors = [
        f"text='{btn_text}'",
        f"span:text-is('{btn_text}')",
        f"div:text-is('{btn_text}')",
        f"button:has-text('{btn_text}')",
    ]
    for sel in selectors:
        try:
            locs = page.locator(sel)
            count = locs.count()
            if count > 0:
                for i in range(count):
                    loc = locs.nth(i)
                    if loc.is_visible():
                        bbox = loc.bounding_box()
                        if bbox and bbox['y'] > 400:
                            loc.click(force=True, timeout=3000)
                            print(f"  ✅ 方法3 ({sel}) 成功!")
                            time.sleep(1.0)
                            return True
        except:
            pass

    print(f"  ❌ 所有方法均未能找到「{btn_text}」按钮")
    return False


# ============================================================
# 子表格弹窗辅助函数
# ============================================================
def fill_section_add_popup(page, section_keyword, fill_actions, desc=""):
    """在指定区域点击「新增」按钮 → 填写弹窗字段 → 确定"""
    print(f"\n  🪟 {desc or section_keyword}: 查找「新增」按钮...")
    page.keyboard.press("Escape"); time.sleep(0.3)

    add_clicked = page.evaluate("""(kw) => {
        function norm(t) { return (t||'').replace(/[\\s\\u00a0\\u3000]+/g, ''); }
        function isAddBtn(t) {
            const n = norm(t);
            return n === '\\u65b0\\u589e' || n === '+\\u65b0\\u589e' ||
                   n === '\\u6dfb\\u52a0' || n === '+\\u6dfb\\u52a0';
        }
        function isNoiseNode(el) {
            while (el) {
                const cls = String(el.className || '').toLowerCase();
                const id = String(el.id || '').toLowerCase();
                const tag = String(el.tagName || '').toLowerCase();
                if (cls.includes('anchor') || 
                    cls.includes('menu') || 
                    cls.includes('sidebar') || 
                    cls.includes('sider') || 
                    cls.includes('navbar') || 
                    cls.includes('ant-tabs-nav') || 
                    cls.includes('ant-tabs-tab-btn') || 
                    tag === 'nav' || 
                    id.includes('anchor') || 
                    id.includes('menu') || 
                    id.includes('sidebar')) {
                    return true;
                }
                el = el.parentElement;
            }
            return false;
        }

        const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let kwNode = null, tn;
        while(tn = tw.nextNode()){
            if(tn.textContent.includes(kw) && tn.parentElement){
                const pe = tn.parentElement;
                if(pe.offsetParent !== null && !isNoiseNode(pe)){
                    kwNode = pe;
                    pe.scrollIntoView({block: 'center', behavior: 'instant'});
                    break;
                }
            }
        }
        if(!kwNode){ return 'kw_not_found:' + kw; }

        const kwRect = kwNode.getBoundingClientRect();
        const kwY = kwRect.top + kwRect.height / 2;

        const allBtns = document.querySelectorAll('button, .ant-btn, span[role="button"], a');
        let bestBtn = null, bestDist = Infinity, bestInfo = '';

        for(const btn of allBtns){
            if(btn.offsetParent === null) continue;
            if(!isAddBtn(btn.textContent)) continue;
            const btnRect = btn.getBoundingClientRect();
            const btnY = btnRect.top + btnRect.height / 2;
            let vertDist = btnY - kwY;
            if(vertDist < 0) vertDist = Math.abs(vertDist) * 3;
            const horizDist = Math.abs(btnRect.left + btnRect.width/2 - kwRect.left - kwRect.width/2);
            const dist = vertDist + horizDist * 0.3;
            if(dist < bestDist){
                bestDist = dist;
                bestBtn = btn;
                bestInfo = 'proximity:vert=' + vertDist.toFixed(0) + ' horiz=' + horizDist.toFixed(0) + ' btn=' + norm(btn.textContent);
            }
        }

        if(bestBtn){
            bestBtn.click();
            return bestInfo;
        }

        bestBtn = null; bestDist = Infinity; bestInfo = '';
        for(const btn of allBtns){
            if(btn.offsetParent === null) continue;
            const t = norm(btn.textContent);
            if(!t.includes('\\u589e') || t.length > 8) continue;
            const btnRect = btn.getBoundingClientRect();
            const btnY = btnRect.top + btnRect.height / 2;
            let vertDist = btnY - kwY;
            if(vertDist < 0) vertDist = Math.abs(vertDist) * 3;
            const horizDist = Math.abs(btnRect.left + btnRect.width/2 - kwRect.left - kwRect.width/2);
            const dist = vertDist + horizDist * 0.3;
            if(dist < bestDist){
                bestDist = dist;
                bestBtn = btn;
                bestInfo = 'fuzzy_proximity:vert=' + vertDist.toFixed(0) + ' btn=' + t;
            }
        }
        if(bestBtn){
            bestBtn.click();
            return bestInfo;
        }

        const allAddBtns = Array.from(allBtns).filter(x => x.offsetParent !== null && isAddBtn(x.textContent));
        const addInfo = allAddBtns.map(b => {
            const r = b.getBoundingClientRect();
            const v = r.top + r.height/2 - kwY;
            return norm(b.textContent) + '@y' + v.toFixed(0);
        });
        return 'no_add_btn|kw=' + kw + '|kwY=' + kwY.toFixed(0) + '|addBtns=' + JSON.stringify(addInfo);
    }""", section_keyword)
    print(f"    按钮搜索: {add_clicked}")

    if 'no_add_btn' in str(add_clicked):
        print(f"    ⚠ 未找到「新增」按钮，跳过")
        return False

    time.sleep(1.5)

    modal_diag = page.evaluate("""() => {
        function isVis(el) {
            if (!el) return false;
            const s = window.getComputedStyle(el);
            return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
        }
        function getActiveModal() {
            const modals = Array.from(document.querySelectorAll('.ant-modal-wrap, .ant-drawer'))
                .filter(el => {
                    if (!isVis(el)) return false;
                    if (el.classList.contains('ant-modal-wrap-hidden')) return false;
                    if (el.classList.contains('ant-drawer') && !el.classList.contains('ant-drawer-open')) return false;
                    return true;
                });
            if (modals.length === 0) return null;
            modals.sort((a, b) => {
                const za = parseInt(window.getComputedStyle(a).zIndex) || 0;
                const zb = parseInt(window.getComputedStyle(b).zIndex) || 0;
                return zb - za;
            });
            return modals[0];
        }
        const modalEl = getActiveModal();
        if(!modalEl) return 'no_modal';
        const labels = modalEl.querySelectorAll('.ant-form-item-label, label, .fieldlabel, [class*="label"], th, .ant-form-item-required');
        const visible = Array.from(labels).filter(l => l.offsetParent !== null && (l.textContent||'').trim());
        const labelTexts = visible.map(l => (l.textContent||'').trim().replace(/\\s+/g,' ')).slice(0, 20);
        const ths = modalEl.querySelectorAll('th');
        const thTexts = Array.from(ths).filter(t => t.offsetParent !== null).map(t => (t.textContent||'').trim()).filter(t => t).slice(0, 10);
        return JSON.stringify({labels: labelTexts, ths: thTexts, hasTable: modalEl.querySelectorAll('table').length});
    }""")
    print(f"    弹窗诊断: {modal_diag}")

    if 'no_modal' in str(modal_diag):
        print("    ⚠ 弹窗未打开，跳过填写")
        return False

    for i, action in enumerate(fill_actions):
        act_type = action.get('type', 'input')
        field_label = action.get('label', '')
        field_value = action.get('value', '')

        if act_type == 'input':
            print(f"    弹窗字段[{i}] {field_label} -> {field_value}")
            focus_result = page.evaluate("""(params) => {
                function isVis(el) {
                    if (!el) return false;
                    const s = window.getComputedStyle(el);
                    return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
                }
                function getActiveModal() {
                    const modals = Array.from(document.querySelectorAll('.ant-modal-wrap, .ant-drawer'))
                        .filter(el => {
                            if (!isVis(el)) return false;
                            if (el.classList.contains('ant-modal-wrap-hidden')) return false;
                            if (el.classList.contains('ant-drawer') && !el.classList.contains('ant-drawer-open')) return false;
                            return true;
                        });
                    if (modals.length === 0) return null;
                    modals.sort((a, b) => {
                        const za = parseInt(window.getComputedStyle(a).zIndex) || 0;
                        const zb = parseInt(window.getComputedStyle(b).zIndex) || 0;
                        return zb - za;
                    });
                    return modals[0];
                }
                const modalEl = getActiveModal();
                if(!modalEl) return 'no_modal';
                const kw = params.kw;

                const labels = modalEl.querySelectorAll('.ant-form-item-label, label, .fieldlabel, [class*="label"]');
                let bestLabel = null;
                let bestMatchLen = Infinity;
                for(const lbl of labels){
                    const lt = lbl.textContent.trim();
                    if(lt.includes(kw)){
                        if(lt.length < bestMatchLen){
                            bestMatchLen = lt.length;
                            bestLabel = lbl;
                        }
                    }
                }
                let bestMatch = bestLabel;
                while(bestMatch && bestMatch !== modalEl){
                    const input = bestMatch.querySelector('textarea, input[type="text"]:not([readonly]), input[type="number"]:not([readonly]), input:not([type]):not([readonly]), [contenteditable="true"], .ant-select-selection-search input');
                    if(input) break;
                    bestMatch = bestMatch.parentElement;
                }
                if(bestMatch){
                    let input = bestMatch.querySelector('textarea');
                    if(!input) input = bestMatch.querySelector('input[type="text"]:not([readonly])');
                    if(!input) input = bestMatch.querySelector('input[type="number"]:not([readonly])');
                    if(!input) input = bestMatch.querySelector('input:not([type]):not([readonly])');
                    if(!input) input = bestMatch.querySelector('[contenteditable="true"], [contenteditable=""]');
                    if(!input) input = bestMatch.querySelector('.ant-select-selection-search input');
                    if(input){
                        input.focus();
                        input.click();
                        try {
                            if (typeof input.select === 'function') {
                                input.select();
                            }
                        } catch(e) {}
                        return 'focused_formitem';
                    }
                }

                const rows = modalEl.querySelectorAll('tr, .ant-table-row');
                for(const row of rows){
                    const th = row.querySelector('th');
                    if(!th || !th.textContent.includes(kw)) continue;
                    const td = row.querySelector('td');
                    if(!td) continue;
                    const input = td.querySelector('textarea, input[type="text"]:not([readonly]), input[type="number"]:not([readonly]), input:not([type]):not([readonly]), [contenteditable]');
                    if(input){
                        input.focus();
                        input.click();
                        try {
                            if (typeof input.select === 'function') {
                                input.select();
                            }
                        } catch(e) {}
                        return 'focused_th';
                    }
                }

                for(const item of items){
                    const lbl = item.querySelector('.ant-form-item-label, label, .fieldlabel, [class*="label"]');
                    if(lbl){
                        const lt = lbl.textContent.trim();
                        if(lt.includes(kw.substring(0,2)) || kw.includes(lt.substring(0,2))){
                            const input = item.querySelector('textarea, input[type="text"]:not([readonly]), input[type="number"]:not([readonly]), input:not([type]):not([readonly]), [contenteditable]');
                            if(input){
                                input.focus();
                                input.click();
                                try {
                                    if (typeof input.select === 'function') {
                                        input.select();
                                    }
                                } catch(e) {}
                                return 'focused_fuzzy';
                            }
                        }
                    }
                }

                const allInputs = modalEl.querySelectorAll('textarea, input[type="text"]:not([readonly]), input[type="number"]:not([readonly]), input:not([type]):not([readonly]), [contenteditable]');
                const visibleInputs = Array.from(allInputs).filter(inp => inp.offsetParent !== null);
                if(params.idx < visibleInputs.length){
                    const inp = visibleInputs[params.idx];
                    inp.focus();
                    inp.click();
                    try {
                        if (typeof inp.select === 'function') {
                            inp.select();
                        }
                    } catch(e) {}
                    return 'focused_fallback';
                }
                return 'label_not_found_in_modal';
            }""", {'kw': field_label, 'idx': i})
            
            print(f"      定位输入框: {focus_result}")
            if 'focused' in str(focus_result):
                time.sleep(0.1)
                page.keyboard.press("Backspace")
                time.sleep(0.1)
                page.keyboard.type(str(field_value), delay=50)
                time.sleep(0.1)
                
                # Hybrid programmatic dispatch to guarantee React state synchronization
                page.evaluate("""(params) => {
                    function isVis(el) {
                        if (!el) return false;
                        const s = window.getComputedStyle(el);
                        return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
                    }
                    function getActiveModal() {
                        const modals = Array.from(document.querySelectorAll('.ant-modal-wrap, .ant-drawer'))
                            .filter(el => {
                                if (!isVis(el)) return false;
                                if (el.classList.contains('ant-modal-wrap-hidden')) return false;
                                if (el.classList.contains('ant-drawer') && !el.classList.contains('ant-drawer-open')) return false;
                                return true;
                            });
                        if (modals.length === 0) return null;
                        modals.sort((a, b) => {
                            const za = parseInt(window.getComputedStyle(a).zIndex) || 0;
                            const zb = parseInt(window.getComputedStyle(b).zIndex) || 0;
                            return zb - za;
                        });
                        return modals[0];
                    }
                    const modalEl = getActiveModal();
                    if(!modalEl) return;
                    const kw = params.kw;
                    const val = params.val;
                    
                    const labels = modalEl.querySelectorAll('.ant-form-item-label, label, .fieldlabel, [class*="label"]');
                    let bestLabel = null;
                    let bestMatchLen = Infinity;
                    for(const lbl of labels){
                        const lt = lbl.textContent.trim();
                        if(lt.includes(kw)){
                            if(lt.length < bestMatchLen){
                                bestMatchLen = lt.length;
                                bestLabel = lbl;
                            }
                        }
                    }
                    let item = bestLabel;
                    while(item && item !== modalEl){
                        const inp = item.querySelector('input, textarea');
                        if(inp) break;
                        item = item.parentElement;
                    }
                    if(item){
                        const inp = item.querySelector('input, textarea');
                        if(inp){
                            inp.value = val;
                            inp.dispatchEvent(new Event('input', {bubbles: true}));
                            inp.dispatchEvent(new Event('change', {bubbles: true}));
                        }
                    }
                }""", {'kw': field_label, 'val': field_value})
                
                page.keyboard.press("Tab")
                print(f"      已通过键盘与JS混合键入值: '{field_value}'")
            else:
                print(f"      ❌ 无法聚焦输入框 '{field_label}'")
            time.sleep(0.3)

        elif act_type == 'select':
            search_val = action.get('search', '')
            print(f"    弹窗字段[{i}] {field_label} -> 选择 {field_value}" + (f" (搜索: {search_val})" if search_val else ""))
            sel_clicked = page.evaluate("""(params) => {
                function isVis(el) {
                    if (!el) return false;
                    const s = window.getComputedStyle(el);
                    return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
                }
                function getActiveModal() {
                    const modals = Array.from(document.querySelectorAll('.ant-modal-wrap, .ant-drawer'))
                        .filter(el => {
                            if (!isVis(el)) return false;
                            if (el.classList.contains('ant-modal-wrap-hidden')) return false;
                            if (el.classList.contains('ant-drawer') && !el.classList.contains('ant-drawer-open')) return false;
                            return true;
                        });
                    if (modals.length === 0) return null;
                    modals.sort((a, b) => {
                        const za = parseInt(window.getComputedStyle(a).zIndex) || 0;
                        const zb = parseInt(window.getComputedStyle(b).zIndex) || 0;
                        return zb - za;
                    });
                    return modals[0];
                }
                const modalEl = getActiveModal();
                if(!modalEl) return 'no_modal';
                const kw = params.kw;

                const labels = modalEl.querySelectorAll('.ant-form-item-label, label, .fieldlabel, [class*="label"]');
                let bestLabel = null;
                let bestMatchLen = Infinity;
                for(const lbl of labels){
                    const lt = lbl.textContent.trim();
                    if(lt.includes(kw)){
                        if(lt.length < bestMatchLen){
                            bestMatchLen = lt.length;
                            bestLabel = lbl;
                        }
                    }
                }
                let item = bestLabel;
                while(item && item !== modalEl){
                    const sel = item.querySelector('.ant-select');
                    if(sel) break;
                    item = item.parentElement;
                }
                if(item){
                    const sel = item.querySelector('.ant-select');
                    if(sel){ sel.click(); return 'select_clicked'; }
                }

                const rows = modalEl.querySelectorAll('tr, .ant-table-row');
                for(const row of rows){
                    const th = row.querySelector('th');
                    if(!th || !th.textContent.includes(kw)) continue;
                    const td = row.querySelector('td');
                    if(!td) continue;
                    const sel = td.querySelector('.ant-select');
                    if(sel){ sel.click(); return 'select_clicked_th'; }
                }

                for(const item of items){
                    const lbl = item.querySelector('.ant-form-item-label, label, .fieldlabel, [class*="label"]');
                    if(lbl){
                        const lt = lbl.textContent.trim();
                        if(lt.includes(kw.substring(0,2)) || kw.includes(lt.substring(0,2))){
                            const sel = item.querySelector('.ant-select');
                            if(sel){ sel.click(); return 'select_clicked_fuzzy'; }
                        }
                    }
                }

                const allSelects = modalEl.querySelectorAll('.ant-select');
                const visible = Array.from(allSelects).filter(s => s.offsetParent !== null);
                if(visible.length > 0){
                    visible[0].click();
                    return 'clicked_first_select/' + visible.length;
                }

                return 'no_select (selects=' + allSelects.length + ')';
            }""", {'kw': field_label})
            print(f"      触发: {sel_clicked}")
            if sel_clicked and 'no_select' not in str(sel_clicked) and 'no_modal' not in str(sel_clicked):
                time.sleep(0.8)
                if search_val:
                    focus_r = page.evaluate("""() => {
                        const inputs = document.querySelectorAll(
                            '.ant-select-open input, .ant-select-focused input, input.ant-select-search__field, input.ant-select-selection-search-input'
                        );
                        let targetInput = null;
                        for(const inp of inputs){
                            if(inp.offsetParent !== null){ targetInput = inp; break; }
                        }
                        if(targetInput){
                            targetInput.focus();
                            targetInput.click();
                            targetInput.value = '';
                            targetInput.dispatchEvent(new Event('input', {bubbles: true}));
                            targetInput.dispatchEvent(new Event('change', {bubbles: true}));
                            return 'focused_and_cleared';
                        }
                        return 'no_visible_search_input';
                    }""")
                    print(f"      聚焦搜索输入框: {focus_r}")
                    time.sleep(0.3)
                    page.keyboard.type(search_val, delay=50)
                    print(f"      键盘输入搜索值: {search_val}")
                    time.sleep(1.5)
                opt_result = page.evaluate("""(val) => {
                    const opts = document.querySelectorAll('[role="option"], .ant-select-dropdown-menu-item, .ant-select-dropdown li, li[role="menuitem"], .ant-select-item-option');
                    for(const o of opts){
                        if(o.offsetParent === null) continue;
                        const t = (o.textContent||'').trim();
                        if(t === val || t.includes(val)){ o.click(); return 'selected:'+t; }
                    }
                    for(const o of opts){
                        if(o.offsetParent === null) continue;
                        const t = (o.textContent||'').trim();
                        if(t.includes(val)){ o.click(); return 'fuzzy_selected:'+t; }
                    }
                    return 'no_option_matched:' + val;
                }""", field_value)
                print(f"      选择: {opt_result}")
            time.sleep(0.3)

        elif act_type == 'tree_select':
            search_val = action.get('search', '')
            target_val = action.get('value', '')
            print(f"    弹窗字段[{i}] {field_label} -> 树选择 {target_val} (搜索: {search_val})")
            
            click_select = page.evaluate("""(kw) => {
                function isVis(el) {
                    if (!el) return false;
                    const s = window.getComputedStyle(el);
                    return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
                }
                function getActiveModal() {
                    const modals = Array.from(document.querySelectorAll('.ant-modal-wrap, .ant-drawer'))
                        .filter(el => {
                            if (!isVis(el)) return false;
                            if (el.classList.contains('ant-modal-wrap-hidden')) return false;
                            if (el.classList.contains('ant-drawer') && !el.classList.contains('ant-drawer-open')) return false;
                            return true;
                        });
                    if (modals.length === 0) return null;
                    modals.sort((a, b) => {
                        const za = parseInt(window.getComputedStyle(a).zIndex) || 0;
                        const zb = parseInt(window.getComputedStyle(b).zIndex) || 0;
                        return zb - za;
                    });
                    return modals[0];
                }
                const modalEl = getActiveModal();
                if(!modalEl) return 'no_modal';
                
                const labels = modalEl.querySelectorAll('.ant-form-item-label, label, .fieldlabel, [class*="label"]');
                let bestLabel = null;
                let bestMatchLen = Infinity;
                for(const lbl of labels){
                    const lt = lbl.textContent.trim();
                    if(lt.includes(kw)){
                        if(lt.length < bestMatchLen){
                            bestMatchLen = lt.length;
                            bestLabel = lbl;
                        }
                    }
                }
                let item = bestLabel;
                while(item && item !== modalEl){
                    const sel = item.querySelector('.ant-select');
                    if(sel) break;
                    item = item.parentElement;
                }
                if(item){
                    const sel = item.querySelector('.ant-select');
                    if(sel){ sel.click(); return 'clicked'; }
                }
                return 'not_found';
            }""", field_label)
            print(f"      触发选择器: {click_select}")
            time.sleep(1.0)
            
            if 'clicked' in str(click_select):
                focus_r = page.evaluate("""() => {
                    const inputs = document.querySelectorAll(
                        '.ant-select-open input, .ant-select-focused input, input.ant-select-search__field, input.ant-select-selection-search-input, .ant-modal-body input.ant-input, .ant-modal-content input, .ant-drawer input'
                    );
                    let targetInput = null;
                    for(const inp of inputs){
                        if(inp.offsetParent !== null){ targetInput = inp; break; }
                    }
                    if(targetInput){
                        targetInput.focus();
                        targetInput.click();
                        targetInput.value = '';
                        targetInput.dispatchEvent(new Event('input', {bubbles: true}));
                        targetInput.dispatchEvent(new Event('change', {bubbles: true}));
                        return 'focused_and_cleared';
                    }
                    return 'no_visible_search_input';
                }""")
                print(f"      聚焦搜索框: {focus_r}")
                time.sleep(0.3)
                page.keyboard.type(search_val, delay=50)
                time.sleep(0.5)
                page.keyboard.press("Enter")
                print(f"      键盘输入并回车: {search_val}")
                time.sleep(2.0)
                
                modal_check = page.evaluate("""() => {
                    function isVis(el){
                        if(!el) return false;
                        const s = window.getComputedStyle(el);
                        return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
                    }
                    const modals = document.querySelectorAll('.ant-modal-wrap');
                    let modalBody = null;
                    const visibleModals = Array.from(modals).filter(m => isVis(m) && !m.classList.contains('ant-modal-wrap-hidden'));
                    if(visibleModals.length === 0) return {found: false};
                    const m = visibleModals[visibleModals.length - 1];
                    const body = m.querySelector('.ant-modal-body');
                    if(!body) return {found: false};
                    const input = body.querySelector('.ant-input-affix-wrapper input.ant-input, input.ant-input');
                    if(!input) return {found: true, hasInput: false, treeChildCount: body.querySelectorAll('.ant-tree-treenode').length};
                    input.focus();
                    return {found: true, hasInput: true, treeChildCount: body.querySelectorAll('.ant-tree-treenode').length};
                }""")
                print(f"      树选择弹窗检查: {modal_check}")
                
                if modal_check.get('found') and modal_check.get('hasInput'):
                    search_modal = page.evaluate("""(keyword) => {
                        function isVis(el){
                            if(!el) return false;
                            const s = window.getComputedStyle(el);
                            return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
                        }
                        const modals = document.querySelectorAll('.ant-modal-wrap');
                        const visibleModals = Array.from(modals).filter(m => isVis(m) && !m.classList.contains('ant-modal-wrap-hidden'));
                        if(visibleModals.length === 0) return {ok: false};
                        const m = visibleModals[visibleModals.length - 1];
                        const body = m.querySelector('.ant-modal-body');
                        const input = body.querySelector('.ant-input-affix-wrapper input.ant-input, input.ant-input');
                        if(!input) return {ok: false, reason: 'no_input'};
                        input.focus();
                        input.value = '';
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        nativeInputValueSetter.call(input, keyword);
                        input.dispatchEvent(new Event('keydown', {bubbles: true}));
                        input.dispatchEvent(new Event('input', {bubbles: true}));
                        input.dispatchEvent(new Event('keyup', {bubbles: true}));
                        input.dispatchEvent(new Event('change', {bubbles: true}));
                        const enterEvent = new KeyboardEvent('keydown', {
                            key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
                        });
                        input.dispatchEvent(enterEvent);
                        input.dispatchEvent(new KeyboardEvent('keyup', {
                            key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
                        }));
                        return {ok: true};
                    }""", search_val)
                    print(f"      弹窗内二次输入(含Enter): {search_modal}")
                    time.sleep(2.0)
                
                # Use JS evaluate directly for tree node selection to ensure React state updates correctly (matching step 13.5)
                tree_result = {"status": "not_found"}
                for tree_attempt in range(5):
                    tree_result = page.evaluate("""(keyword) => {
                        function isVis(el){
                            if(!el) return false;
                            const s = window.getComputedStyle(el);
                            return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
                        }
                        const modals = document.querySelectorAll('.ant-modal-wrap');
                        const visibleModals = Array.from(modals).filter(m => isVis(m) && !m.classList.contains('ant-modal-wrap-hidden'));
                        if(visibleModals.length === 0) return {status: 'no_modal'};
                        const m = visibleModals[visibleModals.length - 1];
                        const body = m.querySelector('.ant-modal-body');
                        if(!body) return {status: 'no_body'};
                        
                        const allTitles = body.querySelectorAll('.ant-tree-title, .ant-select-tree-title, .ant-tree-node-content-wrapper, .ant-select-tree-node-content-wrapper');
                        for(const t of allTitles){
                            if(!isVis(t)) continue;
                            const txt = (t.textContent || '').trim();
                            if(txt.includes(keyword)){
                                const nodeEl = t.closest('.ant-tree-treenode, .ant-select-tree-treenode, li');
                                let cb = null;
                                if(nodeEl){
                                    cb = nodeEl.querySelector('.ant-tree-checkbox, .ant-select-tree-checkbox');
                                }
                                if(cb && isVis(cb)){
                                    if(!cb.classList.contains('ant-tree-checkbox-checked') && !cb.classList.contains('ant-select-tree-checkbox-checked')){
                                        cb.click();
                                        return {status: 'checked_only', text: txt};
                                    } else {
                                        return {status: 'already_checked', text: txt};
                                    }
                                } else {
                                    const wrapper = (t.classList.contains('ant-tree-node-content-wrapper') || t.classList.contains('ant-select-tree-node-content-wrapper')) ? t : t.closest('.ant-tree-node-content-wrapper, .ant-select-tree-node-content-wrapper');
                                    if(wrapper && isVis(wrapper)){
                                        wrapper.click();
                                        return {status: 'clicked_wrapper', text: txt};
                                    } else {
                                        t.click();
                                        return {status: 'clicked_title_direct', text: txt};
                                    }
                                }
                            }
                        }
                        return {status: 'not_found'};
                    }""", target_val)
                    if tree_result.get("status") != "not_found":
                        break
                    print(f"      [树选择] 第 {tree_attempt + 1} 次尝试未找到节点，等待 1.5 秒重试...")
                    time.sleep(1.5)
                print(f"      树节点勾选: {tree_result}")
                time.sleep(0.8)
                try:
                    page.screenshot(path="/Users/wujin/.gemini/antigravity/brain/3138581a-0a89-42a7-926f-3e1503cd1c2a/tree_select_open.png")
                    print("      [DEBUG]已截取树选择弹窗状态图: tree_select_open.png")
                except Exception as e:
                    print(f"      [DEBUG]截图失败: {e}")
                
                try:
                    # Blur search input inside the active tree-select modal to commit its text
                    page.evaluate("""() => {
                        function isVis(el){
                            if(!el) return false;
                            const s = window.getComputedStyle(el);
                            return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
                        }
                        const modals = document.querySelectorAll('.ant-modal-wrap');
                        const visibleModals = Array.from(modals).filter(m => isVis(m) && !m.classList.contains('ant-modal-wrap-hidden'));
                        if(visibleModals.length > 0){
                            const m = visibleModals[visibleModals.length - 1];
                            const input = m.querySelector('input');
                            if(input) input.blur();
                        }
                    }""")
                    time.sleep(0.3)
                    
                    # Natively click confirm button via Playwright to ensure blur/focus and sync React state
                    confirm_btn = page.locator(".ant-modal-wrap:not(.ant-modal-wrap-hidden) .ant-modal-footer button.ant-btn-primary, .ant-modal-wrap:not(.ant-modal-wrap-hidden) .ant-modal-footer button").last
                    if confirm_btn.is_visible():
                        confirm_btn.click()
                        print("      [Native Click] 成功物理点击树选择弹窗确定按钮")
                        time.sleep(0.5)
                except Exception as e:
                    print(f"      [Native Click] 物理点击失败: {e}")
                
                confirm_modal = page.evaluate("""() => {
                    function isVis(el){
                        if(!el) return false;
                        const s = window.getComputedStyle(el);
                        return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
                    }
                    const modals = document.querySelectorAll('.ant-modal-wrap');
                    const visibleModals = Array.from(modals).filter(m => isVis(m) && !m.classList.contains('ant-modal-wrap-hidden'));
                    if(visibleModals.length === 0) return {status: 'no_modal'};
                    const m = visibleModals[visibleModals.length - 1];
                    const footer = m.querySelector('.ant-modal-footer');
                    if(!footer) return {status: 'no_footer'};
                    
                    for(const btn of footer.querySelectorAll('button, .ant-btn')){
                        if(!isVis(btn)) continue;
                        const bt = (btn.textContent || '').trim();
                        if(bt === '确 定' || bt === '确定' || bt === '确认'){
                            btn.click(); return {status: 'confirmed', btnText: bt};
                        }
                    }
                    for(const btn of footer.querySelectorAll('.ant-btn-primary')){
                        if(isVis(btn)){ btn.click(); return {status: 'confirmed_primary'}; }
                    }
                    return {status: 'no_confirm_btn'};
                }""")
                print(f"      树选择确定: {confirm_modal}")
                time.sleep(1.0)
                
                print("      等待树选择弹窗关闭...")
                for _ in range(20):
                    vis_modals = page.evaluate("""() => {
                        function isVis(el){
                            if(!el) return false;
                            const s = window.getComputedStyle(el);
                            return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
                        }
                        const modals = document.querySelectorAll('.ant-modal-wrap, .ant-drawer');
                        return Array.from(modals).filter(m => isVis(m) && !m.classList.contains('ant-modal-wrap-hidden') && (!m.classList.contains('ant-drawer') || m.classList.contains('ant-drawer-open'))).length;
                    }""")
                    if vis_modals <= 1:
                        break
                    time.sleep(0.25)
                print("      树选择弹窗已关闭")
            time.sleep(0.3)

        elif act_type == 'multi_select':
            values = action.get('values', [])
            for vi, fv in enumerate(values):
                print(f"    弹窗字段[{i}] {field_label} -> 选择 {fv} ({vi+1}/{len(values)})")
                ms_clicked = page.evaluate("""(params) => {
                    function isVis(el) {
                        if (!el) return false;
                        const s = window.getComputedStyle(el);
                        return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
                    }
                    function getActiveModal() {
                        const modals = Array.from(document.querySelectorAll('.ant-modal-wrap, .ant-drawer'))
                            .filter(el => {
                                if (!isVis(el)) return false;
                                if (el.classList.contains('ant-modal-wrap-hidden')) return false;
                                if (el.classList.contains('ant-drawer') && !el.classList.contains('ant-drawer-open')) return false;
                                return true;
                            });
                        if (modals.length === 0) return null;
                        modals.sort((a, b) => {
                            const za = parseInt(window.getComputedStyle(a).zIndex) || 0;
                            const zb = parseInt(window.getComputedStyle(b).zIndex) || 0;
                            return zb - za;
                        });
                        return modals[0];
                    }
                    const modalEl = getActiveModal();
                    if(!modalEl) return 'no_modal';
                    const kw = params.kw;
                    const labels = modalEl.querySelectorAll('.ant-form-item-label, label, .fieldlabel, [class*="label"]');
                    let bestLabel = null;
                    let bestMatchLen = Infinity;
                    for(const lbl of labels){
                        const lt = lbl.textContent.trim();
                        if(lt.includes(kw)){
                            if(lt.length < bestMatchLen){
                                bestMatchLen = lt.length;
                                bestLabel = lbl;
                            }
                        }
                    }
                    let item = bestLabel;
                    while(item && item !== modalEl){
                        const sel = item.querySelector('.ant-select');
                        if(sel) break;
                        item = item.parentElement;
                    }
                    if(item){
                        const sel = item.querySelector('.ant-select');
                        if(sel){ sel.click(); return 'select_clicked'; }
                    }
                    return 'no_select';
                }""", {'kw': field_label})
                print(f"      触发: {ms_clicked}")
                if ms_clicked and 'no_select' not in str(ms_clicked) and 'no_modal' not in str(ms_clicked):
                    time.sleep(0.8)
                    mo_result = page.evaluate("""(val) => {
                        const opts = document.querySelectorAll('[role="option"], .ant-select-dropdown-menu-item, .ant-select-dropdown li, li[role="menuitem"], .ant-select-item-option');
                        for(const o of opts){
                            if(o.offsetParent === null) continue;
                            const t = (o.textContent||'').trim();
                            if(t === val || t.includes(val)){ o.click(); return 'selected:'+t; }
                        }
                        for(const o of opts){
                            if(o.offsetParent === null) continue;
                            const t = (o.textContent||'').trim();
                            if(t.includes(val)){ o.click(); return 'fuzzy_selected:'+t; }
                        }
                        return 'no_option_matched:' + val;
                    }""", fv)
                    print(f"      选择: {mo_result}")
                    time.sleep(0.5)
                page.keyboard.press("Escape")
                time.sleep(0.3)

    time.sleep(2.5)

    # Debug: print the values of all fields inside the active modal!
    form_values = page.evaluate("""() => {
        function isVis(el) {
            if (!el) return false;
            const s = window.getComputedStyle(el);
            return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
        }
        function getActiveModal() {
            const modals = Array.from(document.querySelectorAll('.ant-modal-wrap, .ant-drawer'))
                .filter(el => {
                    if (!isVis(el)) return false;
                    if (el.classList.contains('ant-modal-wrap-hidden')) return false;
                    if (el.classList.contains('ant-drawer') && !el.classList.contains('ant-drawer-open')) return false;
                    return true;
                });
            if (modals.length === 0) return null;
            modals.sort((a, b) => {
                const za = parseInt(window.getComputedStyle(a).zIndex) || 0;
                const zb = parseInt(window.getComputedStyle(b).zIndex) || 0;
                return zb - za;
            });
            return modals[0];
        }
        const modalEl = getActiveModal();
        if(!modalEl) return 'no_modal';
        
        const results = [];
        const items = modalEl.querySelectorAll('.ant-form-item, .ant-row, [class*="form-item"]');
        for(const item of items){
            const lblEl = item.querySelector('.ant-form-item-label, label, .fieldlabel, [class*="label"]');
            if(!lblEl) continue;
            const lbl = lblEl.textContent.trim();
            
            // Get value of input/textarea
            let val = '';
            const input = item.querySelector('input, textarea');
            if(input) val = input.value;
            
            // Get value of ant-select
            const selectValEl = item.querySelector('.ant-select-selection-selected-value, .ant-select-selection-item');
            if(selectValEl) val = selectValEl.textContent.trim();
            
            results.push(lbl + ': ' + val);
        }
        return results;
    }""")
    print(f"    [DEBUG] 弹窗表单当前值: {form_values}")

    confirm_result = page.evaluate("""() => {
        function isVis(el) {
            if (!el) return false;
            const s = window.getComputedStyle(el);
            return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
        }
        function getActiveModal() {
            const modals = Array.from(document.querySelectorAll('.ant-modal-wrap, .ant-drawer'))
                .filter(el => {
                    if (!isVis(el)) return false;
                    if (el.classList.contains('ant-modal-wrap-hidden')) return false;
                    if (el.classList.contains('ant-drawer') && !el.classList.contains('ant-drawer-open')) return false;
                    return true;
                });
            if (modals.length === 0) return null;
            modals.sort((a, b) => {
                const za = parseInt(window.getComputedStyle(a).zIndex) || 0;
                const zb = parseInt(window.getComputedStyle(b).zIndex) || 0;
                return zb - za;
            });
            return modals[0];
        }
        const modalEl = getActiveModal();
        if(!modalEl) return 'no_modal';
        const btns = modalEl.querySelectorAll('button, .ant-btn, span[role="button"]');
        for(const btn of btns){
            if(btn.offsetParent === null) continue;
            const t = (btn.textContent||'').trim();
            if(t === '\u786e\u5b9a' || t === '\u786e \u5b9a' || t === '\u786e\u8ba4' || t === 'OK'){
                btn.click(); return 'confirmed:' + t;
            }
        }
        for(const btn of modalEl.querySelectorAll('.ant-btn-primary')){
            if(btn.offsetParent !== null){ btn.click(); return 'primary'; }
        }
        return 'no_confirm_btn';
    }""")
    print(f"    确定: {confirm_result}")

    # Wait for the modal to close after clicking confirm
    print("    等待新增弹窗关闭...")
    modal_closed = False
    for _ in range(12):
        vis_modals = page.evaluate("""() => {
            function isVis(el){
                if(!el) return false;
                const s = window.getComputedStyle(el);
                return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
            }
            const modals = document.querySelectorAll('.ant-modal-wrap, .ant-drawer');
            return Array.from(modals).filter(m => isVis(m) && !m.classList.contains('ant-modal-wrap-hidden') && (!m.classList.contains('ant-drawer') || m.classList.contains('ant-drawer-open'))).length;
        }""")
        if vis_modals == 0:
            modal_closed = True
            break
        time.sleep(0.5)

    if modal_closed:
        print("    [OK] 弹窗已成功关闭并保存")
        time.sleep(1.0)
    else:
        print("    ❌ 确定按钮已点击，但弹窗未关闭（可能是表单验证失败或未加载完成）！")
        # Let's log the details of the modal for troubleshooting
        form_values_fail = page.evaluate("""() => {
            function isVis(el) {
                if (!el) return false;
                const s = window.getComputedStyle(el);
                return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
            }
            function getActiveModal() {
                const modals = Array.from(document.querySelectorAll('.ant-modal-wrap, .ant-drawer'))
                    .filter(el => {
                        if (!isVis(el)) return false;
                        if (el.classList.contains('ant-modal-wrap-hidden')) return false;
                        if (el.classList.contains('ant-drawer') && !el.classList.contains('ant-drawer-open')) return false;
                        return true;
                    });
                if (modals.length === 0) return null;
                modals.sort((a, b) => {
                    const za = parseInt(window.getComputedStyle(a).zIndex) || 0;
                    const zb = parseInt(window.getComputedStyle(b).zIndex) || 0;
                    return zb - za;
                });
                return modals[0];
            }
            const modalEl = getActiveModal();
            if(!modalEl) return 'no_modal';
            const results = [];
            const items = modalEl.querySelectorAll('.ant-form-item, .ant-row, [class*="form-item"]');
            for(const item of items){
                const lblEl = item.querySelector('.ant-form-item-label, label, .fieldlabel, [class*="label"]');
                if(!lblEl) continue;
                const lbl = lblEl.textContent.trim();
                let val = '';
                const input = item.querySelector('input, textarea');
                if(input) val = input.value;
                const selectValEl = item.querySelector('.ant-select-selection-selected-value, .ant-select-selection-item');
                if(selectValEl) val = selectValEl.textContent.trim();
                results.push(lbl + ': ' + val);
            }
            return results;
        }""")
        print(f"    [WARNING] 未关闭时弹窗表单状态: {form_values_fail}")
        page.keyboard.press("Escape")
        time.sleep(0.5)

    return modal_closed or 'confirmed' in str(confirm_result) or 'primary' in str(confirm_result)


class AuthExpiredException(Exception):
    """Custom exception raised when EOA session invalidation or 403 Forbidden is detected during execution"""
    pass

def check_auth_status(page, has_mid_auth_error):
    if has_mid_auth_error[0]:
        raise AuthExpiredException("Detected 403/401 network response from EOA server")
    if "login" in page.url:
        raise AuthExpiredException("Detected page redirection to EOA login page")


active_playwright = None
active_browser = None

# ============================================================
# 主流程
# ============================================================
def main():
    print("\n" + "=" * 55)
    print("IT运维申请单 - 子版本上线发布通用自动填报 (EOA117) v17.0")
    print("=" * 55)

    parser = argparse.ArgumentParser(description='IT运维申请单 - 子版本上线发布通用版')
    parser.add_argument('变更系统', nargs='?', default=None)
    args = parser.parse_args()
    raw_kw = args.变更系统

    # 优先清空残留信号文件
    if os.path.exists(KEYWORD_SIGNAL_FILE):
        os.remove(KEYWORD_SIGNAL_FILE)

    if raw_kw and raw_kw.strip():
        SEARCH_KEYWORD = raw_kw.strip()
        print(f"\n[参数] 收到变更系统搜索关键词: '{SEARCH_KEYWORD}'")
    else:
        with open(KEYWORD_SIGNAL_FILE, "w", encoding="utf-8") as f:
            json.dump({"status": "waiting_for_keyword", "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "default": ""}, f, ensure_ascii=False)
        print("\n[交互] 等待在 WorkBuddy 界面输入变更系统搜索关键词...")
        start_time = time.time()
        SEARCH_KEYWORD = None
        while time.time() - start_time < 30:
            if os.path.exists(KEYWORD_SIGNAL_FILE):
                try:
                    with open(KEYWORD_SIGNAL_FILE, "r", encoding="utf-8") as f:
                        kw_data = json.load(f)
                    if kw_data.get("status") == "keyword_received" and kw_data.get("keyword"):
                        SEARCH_KEYWORD = kw_data["keyword"]
                        os.remove(KEYWORD_SIGNAL_FILE)
                        print(f"  ✓ 收到关键词: '{SEARCH_KEYWORD}'")
                        break
                except: pass
            time.sleep(1.0)
        if not SEARCH_KEYWORD:
            SEARCH_KEYWORD = "集中交易系统"
            print(f"  ⏳ 交互超时，默认使用: '{SEARCH_KEYWORD}'")

    # ==================== 模式及配置映射 ====================
    MODE = "jzjy"
    kw_lower = SEARCH_KEYWORD.lower().strip()
    if any(x in kw_lower for x in ["95", "信创", "xinchuang", "信创域"]):
        MODE = "95xinchuang"
    elif any(x in kw_lower for x in ["98", "创新", "chuangxin", "创新域"]):
        MODE = "98chuangxin"
    elif any(x in kw_lower for x in ["参数", "cszx", "交易参数"]):
        MODE = "cszx"
    elif any(x in kw_lower for x in ["集中交易", "jzjy"]):
        MODE = "jzjy"
    else:
        MODE = "dynamic"

    print(f"[模式] 识别为：{MODE}")

    SYSTEM_CONFIGS = {
        "95xinchuang": {
            "search_keyword": "信创",
            "system_path": ["应用", "全业务交易平台", "低延时交易系统(虚拟)", "低延时交易系统(大集中-信创域)"],
            "title_format": "低延时交易系统95信创域{date_compact}版本运维服务变更单",
            "start_time": "17:00",
            "end_time": "20:00",
            "owner": "程海涛",
            "owner_name": "程海涛",
            "engineering_search": "NGTP持续建设",
            "version_url": "http://10.120.188.223:8082/artifactory/jyxt-NGTP-Generic-Prod-Local/PROD/2026XXXX",
            "version_cascader_path": ["应用", "全业务交易平台", "低延时交易系统(虚拟)", "低延时交易系统(大集中-信创域)"],
            "components": ["核心交易组件", "BOS相关组件"],
            "business_functions": ["信息查看", "其他", "非交易业务办理等业务功能"],
            "user_range": ["1万人以下投资者,多个部门"],
            "system_info_actions": [
                {"type": "select", "label": "主系统/灾备", "value": "主系统"},
                {"type": "select", "label": "CMDB维护组名称", "value": "低延时交易系统(信创域)"},
                {"type": "input", "label": "变更文件", "value": "见制品信息"},
                {"type": "select", "label": "cmdb变更部位", "value": "不适用"},
                {"type": "input", "label": "变更部位", "value": "见制品信息包名"},
                {"type": "multi_select", "label": "变更方式", "values": ["新增", "替换"]},
            ]
        },
        "98chuangxin": {
            "search_keyword": "创新",
            "system_path": ["应用", "全业务交易平台", "低延时交易系统(虚拟)", "低延时交易系统(创新域)"],
            "title_format": "低延时交易系统98创新域{date_compact}版本运维服务变更单",
            "start_time": "17:00",
            "end_time": "20:00",
            "owner": "108728",
            "owner_name": "张永军",
            "engineering_search": "NGTP持续建设",
            "version_url": "http://10.120.188.223:8082/artifactory/jyxt-NGTP-Generic-Prod-Local/PROD/2026XXXX",
            "version_cascader_path": ["应用", "全业务交易平台", "低延时交易系统(虚拟)", "低延时交易系统(创新域)"],
            "components": ["核心交易组件", "BOS相关组件"],
            "business_functions": ["信息查看", "其他", "非交易业务办理等业务功能"],
            "user_range": ["1万人以下投资者,多个部门"],
            "system_info_actions": [
                {"type": "select", "label": "主系统/灾备", "value": "主系统"},
                {"type": "select", "label": "CMDB维护组名称", "value": "低延时交易系统(创新域)"},
                {"type": "input", "label": "变更文件", "value": "见制品信息"},
                {"type": "select", "label": "cmdb变更部位", "value": "不适用"},
                {"type": "input", "label": "变更部位", "value": "见制品信息包名"},
                {"type": "multi_select", "label": "变更方式", "values": ["新增", "替换"]},
            ]
        },
        "jzjy": {
            "search_keyword": "集中交易系统",
            "system_path": None,
            "title_format": "关于{SAT_STR}集中交易系统的升级",
            "start_time": "17:30",
            "end_time": "23:30",
            "owner": "111483",
            "owner_name": "张博闻",
            "engineering_search": "集中交易",
            "version_url": "https://yunpan.gtht.com.cn/l/XXXX",
            "version_cascader_path": ["应用", "业务营运平台", "集中交易系统"],
            "components": ["数据库", "核心交易组件"],
            "business_functions": ["信息查看", "其他", "非交易业务办理等业务功能"],
            "user_range": ["1万人以下投资者,多个部门"],
            "system_info_actions": [
                {"type": "select", "label": "主系统/灾备", "value": "主系统"},
                {"type": "select", "label": "CMDB维护组名称", "value": "集中交易系统"},
                {"type": "input", "label": "变更文件", "value": "见制品信息"},
                {"type": "select", "label": "cmdb变更部位", "value": "不适用"},
                {"type": "input", "label": "变更部位", "value": "见制品信息包名"},
                {"type": "multi_select", "label": "变更方式", "values": ["新增", "替换"]},
            ]
        },
        "cszx": {
            "search_keyword": "交易参数管理后台",
            "system_path": None,
            "title_format": "关于{SAT_STR}交易参数管理后台系统的升级",
            "start_time": "17:30",
            "end_time": "23:30",
            "owner": "116748",
            "owner_name": "张颖",
            "engineering_search": "参数中心",
            "version_url": "https://yunpan.gtht.com.cn/l/XXXX",
            "version_cascader_path": ["应用", "业务营运平台", "交易参数管理后台系统"],
            "components": ["数据库", "核心交易组件"],
            "business_functions": ["信息查看", "其他", "非交易业务办理等业务功能"],
            "user_range": ["1万人以下投资者,多个部门"],
            "system_info_actions": [
                {"type": "select", "label": "主系统/灾备", "value": "主系统"},
                {"type": "select", "label": "CMDB维护组名称", "value": "交易参数管理后台系统"},
                {"type": "input", "label": "变更文件", "value": "见制品信息"},
                {"type": "select", "label": "cmdb变更部位", "value": "不适用"},
                {"type": "input", "label": "变更部位", "value": "见制品信息包名"},
                {"type": "multi_select", "label": "变更方式", "values": ["新增", "替换"]},
            ]
        },
        "dynamic": {
            "search_keyword": SEARCH_KEYWORD,
            "system_path": None,
            "title_format": "关于{SAT_STR}" + SEARCH_KEYWORD + "的升级",
            "start_time": "17:30",
            "end_time": "23:30",
            "owner": "111483",
            "owner_name": "张博闻",
            "engineering_search": SEARCH_KEYWORD[:4] if len(SEARCH_KEYWORD) >= 4 else SEARCH_KEYWORD,
            "version_url": "https://yunpan.gtht.com.cn/l/XXXX",
            "version_cascader_path": ["应用", "业务营运平台", SEARCH_KEYWORD],
            "components": ["数据库", "核心交易组件"],
            "business_functions": ["信息查看", "其他", "非交易业务办理等业务功能"],
            "user_range": ["1万人以下投资者,多个部门"],
            "system_info_actions": [
                {"type": "select", "label": "主系统/灾备", "value": "主系统"},
                {"type": "select", "label": "CMDB维护组名称", "value": SEARCH_KEYWORD},
                {"type": "input", "label": "变更文件", "value": "见制品信息"},
                {"type": "select", "label": "cmdb变更部位", "value": "不适用"},
                {"type": "input", "label": "变更部位", "value": "见制品信息包名"},
                {"type": "multi_select", "label": "变更方式", "values": ["新增", "替换"]},
            ]
        }
    }

    active_cfg = SYSTEM_CONFIGS[MODE]

    # ==================== 启动浏览器 ====================
    # 读取 config.json 中的浏览器配置
    channel = config.get("browser", {}).get("channel", None)
    headless = config.get("browser", {}).get("headless", False)
    slow_mo = config.get("browser", {}).get("slow_mo", 50)
    
    launch_kwargs = {
        "headless": headless,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--remote-debugging-port=9222",
            "--disable-blink-features=AutomationControlled",
            "--disable-extensions",
        ],
        "slow_mo": slow_mo,
    }
    if channel:
        launch_kwargs["channel"] = channel

    global active_playwright, active_browser
    active_playwright = sync_playwright().start()
    active_browser = active_playwright.chromium.launch(**launch_kwargs)
    context_kwargs = {
        "viewport": VIEWPORT,
        "locale": "zh-CN",
    }
    if os.path.exists(SESSION_FILE):
        context_kwargs["storage_state"] = SESSION_FILE
        print(f"  [Session] 已载入: {SESSION_FILE}")
    ctx = active_browser.new_context(**context_kwargs)
    pg = ctx.new_page()

    has_mid_auth_error = [False]
    def log_any_response(res):
        if res.status in [401, 403] and "gtht.com.cn" in res.url:
            print(f"  [NetworkError] 运行中接口返回 {res.status}: {res.url}")
            has_mid_auth_error[0] = True
            
    pg.on("response", log_any_response)

    # 注册控制台监听器，便于在无头模式或后台运行时捕获错误
    pg.on("console", lambda msg: print(f"[CONSOLE] {msg.type}: {msg.text}"))
    pg.on("pageerror", lambda err: print(f"[PAGE ERROR] {err}"))

    # ==================== [1] 打开申请单 (自动检测登录) ====================
    print("\n" + "=" * 55)
    print("[1] 打开申请单 (自动检测登录)...")
    _ensure_login_v2(pg)
    ep = pg  # 复用同一个页面
    print(f"[OK] {ep.url}")
    # Reset mid-flight auth error flag after login check stabilizes session
    has_mid_auth_error[0] = False

    # ==================== [3] 升级时间 ====================
    print("\n" + "=" * 55)
    print("[3] 升级时间...")
    pk = ep.locator("input.ant-calendar-picker-input")
    npk = pk.count(); print(f"  {npk}个日期控件")

    r3 = {}
    if npk >= 1:
        r3["开始"] = fill_datetime_v9(ep, pk.nth(0), "开始时间", active_cfg["start_time"]); time.sleep(0.15)
    if npk >= 2:
        r3["结束"] = fill_datetime_v9(ep, pk.nth(1), "结束时间", active_cfg["end_time"])

    # ==================== [4] 紧急度 → 非紧急 ====================
    print("\n" + "=" * 55)
    print("[4] 紧急度 → 非紧急...")
    ep.keyboard.press("Escape"); time.sleep(0.3)

    urgency_result = ep.evaluate("""() => {
        const items = document.querySelectorAll('.formfield');
        for(const item of items){
            const lbl = item.querySelector('.fieldlabel');
            if(lbl && lbl.textContent.includes('紧急度')){
                const sel = item.querySelector('.ant-select');
                if(sel){ sel.click(); return 'clicked'; }
            }
        }
        return 'not_found';
    }""")
    print(f"  紧急度触发: {urgency_result}")
    time.sleep(1.0)

    if urgency_result == 'clicked':
        opt_result = ep.evaluate("""() => {
            const opts = document.querySelectorAll('[role="option"], .ant-select-dropdown-menu-item, .ant-select-dropdown li');
            for(const o of opts){
                const t = o.textContent || '';
                if(t.trim() === '非紧急' || t.includes('非紧急')){ o.click(); return 'selected:'+t.trim(); }
            }
            for(const o of opts){
                if(o.offsetParent !== null){ o.click(); return 'first:'+o.textContent.trim().substring(0,20); }
            }
            return 'no_option';
        }""")
        print(f"  选择: {opt_result}")
    time.sleep(0.5)
    print("  ✓ 紧急度已处理")

    # ==================== [5] 是否补单 → 否 ====================
    print("\n" + "=" * 55)
    print("[5] 是否补单 → 否...")
    ep.keyboard.press("Escape"); time.sleep(0.3)

    patch_result = ep.evaluate("""() => {
        const items = document.querySelectorAll('.formfield');
        for(const item of items){
            const lbl = item.querySelector('.fieldlabel');
            if(lbl && lbl.textContent.includes('是否补单') && !lbl.textContent.includes('补单理由')){
                const radios = item.querySelectorAll('.ant-radio-wrapper');
                if(radios.length > 0){ radios[0].click(); return 'radio:'+radios[0].textContent.trim(); }
                const sel = item.querySelector('.ant-select');
                if(sel){ sel.click(); return 'select_clicked'; }
                return 'found_no_action';
            }
        }
        return 'not_found';
    }""")
    print(f"  是否补单: {patch_result}")

    if patch_result == 'select_clicked':
        time.sleep(0.8)
        po = ep.evaluate("""() => {
            const opts = document.querySelectorAll('[role="option"], .ant-select-dropdown-menu-item, li');
            for(const o of opts){
                if((o.textContent||'').trim()==='否' || (o.textContent||'').includes('否')){ o.click(); return 'ok'; }
            }
            const vis = [];
            document.querySelectorAll('[role="option"], li').forEach(o => { if(o.offsetParent!==null) vis.push(o); });
            if(vis.length>0){ vis[0].click(); return 'first'; }
            return 'fail';
        }""")
        print(f"  补单选择: {po}")
    time.sleep(0.5)

    # ==================== [6] 标题 (延迟到变更系统选完后填) ====================
    title_text = None
    print("\n" + "=" * 55)
    print("[6] 标题 → (待变更系统选定后填写)...")
    print("  ⏳ 标题将在变更系统选择后自动填写")

    # ==================== [7] 变更实施目标/事由 ====================
    print("\n" + "=" * 55)
    print("[7] 变更事由 → '常规版本升级'...")

    r7 = ep.evaluate("""(txt) => {
        const items = document.querySelectorAll('.formfield');
        for(const item of items){
            const lbl = item.querySelector('.fieldlabel');
            if(lbl && (lbl.textContent.includes('事由') || lbl.textContent.includes('变更实施目标'))){
                const ta = item.querySelector('textarea, input[type="text"]');
                if(ta){ ta.focus(); ta.value=txt; ta.dispatchEvent(new Event('input',{bubbles:true})); ta.dispatchEvent(new Event('change',{bubbles:true})); return 'ok'; }
            }
        }
        return 'not_found';
    }""", "常规版本升级")
    print(f"  事由: {r7}")
    time.sleep(0.3)

    # ==================== [7.5] 变更分类保护确认 ====================
    print("\n" + "=" * 55)
    print("[7.5] ⚡ 变更分类保护检查 (不做任何修改)...")

    protect_check = ep.evaluate("""() => {
        const items = document.querySelectorAll('.formfield');
        for(const item of items){
            const lbl = item.querySelector('.fieldlabel');
            if(lbl){
                const txt = lbl.textContent.trim();
                if(txt.includes('分类') && txt.includes('变更')){
                    const content = item.querySelector('.fieldcontent');
                    let currentVal = '(空)';
                    if(content){
                        const selVal = content.querySelector('.ant-select-selection-selected-value');
                        if(selVal) currentVal = selVal.textContent.trim();
                        else{
                            const inp = content.querySelector('input');
                            if(inp) currentVal = inp.value || '(空)';
                        }
                    }
                    return {found: true, label: txt, value: currentVal};
                }
            }
        }
        return {found: false};
    }""")
    if protect_check.get('found'):
        print(f"  ✓ 变更分类已检测到: '{protect_check['label']}'")
        print(f"  ✓ 当前值: '{protect_check['value']}'  → 保持不变!")
        SAVED_CLASSIFY_VALUE = protect_check.get('value', '')
    else:
        print(f"  ℹ 未检测到变更分类字段")
        SAVED_CLASSIFY_VALUE = ''

    # ==================== [8] 变更系统 ====================
    search_kw = active_cfg["search_keyword"]
    sys_path = active_cfg.get("system_path")
    print(f"\n[8] 变更系统 → 搜索 '{search_kw}'...")
    
    cols_data, options_data = search_system_options(ep, search_kw)
    system_selection = None
    if cols_data is None or options_data is None:
        print("  ❌ 变更系统搜索失败!")
    else:
        first_col_items = cols_data.get(0, [])
        target_idx = None
        if sys_path:
            leaf_name = sys_path[-1]
            for i, item in enumerate(first_col_items):
                if leaf_name in item['text']:
                    target_idx = i
                    break
        else:
            for i, item in enumerate(first_col_items):
                if search_kw in item['text']:
                    target_idx = i
                    break
        
        if target_idx is None:
            if first_col_items:
                target_idx = 0
            else:
                print("  ❌ 搜索列表为空，无法选择!")
                
        if target_idx is not None:
            print(f"  🎯 选中: [{target_idx}] {first_col_items[target_idx]['text']}")
            click_result = click_system_choice(ep, target_idx, first_col_items)
            
            cascade_state = handle_cascade_selection(ep, first_col_items[target_idx]['text'])
            while cascade_state.get('needs_choice'):
                level = cascade_state['level']
                cas_items = cascade_state['items']
                cas_idx = 0
                if sys_path and level <= len(sys_path):
                    target_name = sys_path[level - 1]
                    for ci_idx, ci in enumerate(cas_items):
                        if target_name in ci['text']:
                            cas_idx = ci_idx
                            break
                cascade_state = click_cascade_option(ep, level, cas_idx, cas_items, cascade_state['final_so_far'])
            
            system_selection = ep.evaluate("""() => {
                const fields = document.querySelectorAll('.formfield');
                for (const f of fields) {
                    const lbl = f.querySelector('.fieldlabel');
                    if (lbl && lbl.textContent.trim().includes('变更系统') && !lbl.textContent.trim().includes('分类')) {
                        const val = f.querySelector('.ant-cascader-picker-label')?.textContent.trim();
                        if(val) return val;
                    }
                }
                return '';
            }""") or (sys_path and "/".join(sys_path)) or cascade_state.get('final_text', first_col_items[target_idx]['text'])
            print(f"  🎯 变更系统最终选择: {system_selection}")

    # ==================== [8.5] 标题 ====================
    if system_selection:
        title_text = active_cfg["title_format"].format(SAT_STR=SAT_STR, date_compact="2026XXXX")
        print(f"\n{'=' * 55}")
        print(f"[8.5] 标题 → {title_text}")
        ep.keyboard.press("Escape"); time.sleep(0.3)
        title_result = ep.evaluate("""(params) => {
            const targetText = params.title;
            const fields = document.querySelectorAll('.formfield');
            for(const field of fields){
                const lbl = field.querySelector('.fieldlabel');
                if(lbl && lbl.textContent.includes('标题')){
                    const inputs = field.querySelectorAll('input:not([type="hidden"])');
                    for(const inp of inputs){
                        if(inp.offsetParent !== null){
                            inp.focus();
                            inp.value = targetText;
                            inp.dispatchEvent(new Event('input', {bubbles: true}));
                            inp.dispatchEvent(new Event('change', {bubbles: true}));
                            return {ok:true, filled:targetText};
                        }
                    }
                }
            }
            return {ok:false, error:'标题输入框未找到'};
        }""", {'title': title_text})
        if title_result.get('ok'):
            print(f"  ✓ 标题已填写: {title_result['filled']}")
        else:
            print(f"  ✗ 标题填写失败: {title_result.get('error','?')}")
    else:
        print("\n  ⚠ 变更系统未选定, 跳过标题填写")

    # ==================== [9] 工程号 ====================
    eng_search = active_cfg["engineering_search"]
    print("\n" + "=" * 55)
    print(f"[9] 工程号 → 弹窗选择 (固定: {eng_search})...")
    ep.keyboard.press("Escape"); time.sleep(0.5)

    ep.evaluate("""() => {
        const items = document.querySelectorAll('.formfield');
        for(const item of items){
            const lbl = item.querySelector('.fieldlabel');
            if(lbl && lbl.textContent.includes('工程号') && !lbl.textContent.includes('工程名称')){
                const content = item.querySelector('.fieldcontent');
                if(!content) return 'no_content';
                const tryOrder = [
                    content.querySelector('.ant-select-selection'),
                    content.querySelector('.ant-select'),
                    content.querySelector('input:not([type="hidden"])'),
                    content
                ];
                for(const el of tryOrder){
                    if(el && el.offsetParent !== null){ el.click(); return 'clicked'; }
                }
                return 'nothing_clickable';
            }
        }
        return 'not_found';
    }""")
    time.sleep(1.5)

    eng_result = ep.evaluate("""(targetEng) => {
        const modalSels = ['.ant-modal-wrap', '.ant-modal', '[role="dialog"]'];
        let modalEl = null;
        for(const sel of modalSels){
            for(const el of document.querySelectorAll(sel)){
                if(el.offsetParent !== null){ modalEl = el; break; }
            }
            if(modalEl) break;
        }
        if(!modalEl) return {status: 'no_modal'};

        const rows = modalEl.querySelectorAll('tr, .ant-table-row, .ant-list-item');
        for(const row of rows){
            if(row.offsetParent === null) continue;
            const t = (row.textContent || '').trim();
            if(t.includes(targetEng)){
                row.click();
                const radio = row.querySelector('.ant-radio-wrapper, .ant-radio');
                if(radio && radio.offsetParent !== null) radio.click();
                for(const sel of ['button', '.ant-btn']){
                    for(const btn of modalEl.querySelectorAll(sel)){
                        if(btn.offsetParent === null) continue;
                        const bt = (btn.textContent||'').trim();
                        if(bt === '确 定' || bt === '确定' || bt === '确认'){
                            btn.click(); return {status:'success', text: t.substring(0,60)};
                        }
                    }
                }
                for(const btn of modalEl.querySelectorAll('.ant-btn-primary')){
                    if(btn.offsetParent !== null){ btn.click(); return {status:'success', text: t.substring(0,60)}; }
                }
                return {status:'clicked_no_confirm', text: t.substring(0,60)};
            }
        }
        return {status: 'not_found', modal_text: (modalEl.innerText||'').substring(0,200)};
    }""", eng_search)
    print(f"  结果: {eng_result.get('status', eng_result)}")
    if eng_result.get('status') == 'success':
        print(f"  ✅ 已选: {eng_search}")
    else:
        print(f"  ⚠ 未找到 {eng_search}: {eng_result}")

    time.sleep(1.0)

    # ==================== [9.3] 系统版本号 ====================
    sysver_path = active_cfg.get("version_cascader_path")
    if sysver_path:
        print("\n" + "=" * 55)
        print("[9.3] 系统版本号 → 弹窗级联选择...")
        ep.keyboard.press("Escape"); time.sleep(0.3)

        trigger_result = ep.evaluate("""() => {
            const norm = s => (s||'').replace(/\\s+/g, '').replace(/\\u00A0/g, '');
            const TARGETS = ['请选择系统版本号', '← 请选择系统版本号'];
            const viz = el => el && el.offsetParent !== null && el.getBoundingClientRect().width > 0;

            for(const el of document.querySelectorAll('span, a, div, label, button')){
                if(!viz(el)) continue;
                if(el.children.length > 0) continue;
                const t = norm(el.textContent || '');
                for(const target of TARGETS){
                    if(t === norm(target)){
                        el.click();
                        return {status:'leaf_match', tag: el.tagName, text: t.substring(0,30)};
                    }
                }
            }
            for(const el of document.querySelectorAll('span, a, div')){
                if(!viz(el)) continue;
                if(el.children.length > 0) continue;
                if(el.textContent.includes('系统版本号')){
                    el.click();
                    return {status:'leaf_contains', tag: el.tagName};
                }
            }
            for(const el of document.querySelectorAll('*')){
                if(!viz(el)) continue;
                if((el.children.length === 0 || el.tagName === 'A') && el.textContent.length > 3 && el.textContent.length < 30){
                    const t = norm(el.textContent || '');
                    for(const target of TARGETS){
                        if(t === norm(target)){
                            el.click();
                            return {status:'any_match', tag: el.tagName};
                        }
                    }
                }
            }
            return {status:'not_found', url: location.href};
        }""")
        print(f"  弹窗触发: {json.dumps(trigger_result, ensure_ascii=False)}")
        time.sleep(1.5)

        overlay_info = ep.evaluate("""() => {
            const viz = el => el && el.offsetParent !== null;
            for(const m of document.querySelectorAll('.ant-drawer-open, .ant-drawer-content, .ant-modal-wrap, .ant-modal-content')){
                if(!viz(m)) continue;
                const title = m.querySelector('.ant-drawer-title, .ant-modal-title');
                return {type:'overlay', title: title?.textContent||'', hasDrawer: !!m.closest('.ant-drawer')};
            }
            for(const menu of document.querySelectorAll('.ant-cascader-menus')){
                if(viz(menu)){
                    const items = menu.querySelectorAll('.ant-cascader-menu-item');
                    return {type:'cascader_inline', itemCount: items.length, firstItem: items[0]?.textContent?.trim()||''};
                }
            }
            return {type:'none'};
        }""")
        print(f"  容器类型: {json.dumps(overlay_info, ensure_ascii=False)}")

        if overlay_info.get('type') == 'none':
            print("  ⚠ 级联下拉未打开，跳过系统版本号")
        elif overlay_info.get('type') == 'cascader_inline':
            print("  🔧 内联级联 → 每级选第一项...")
            for ki in range(len(sysver_path)):
                lvl = ep.evaluate("""() => {
                    const viz = el => el && el.offsetParent !== null;
                    const menus = document.querySelectorAll('.ant-cascader-menus');
                    const visMenus = Array.from(menus).filter(viz);
                    if(visMenus.length === 0) return {status:'no_menus'};
                    const last = visMenus[visMenus.length - 1];
                    const items = last.querySelectorAll('.ant-cascader-menu-item');
                    if(items.length === 0) return {status:'no_items'};
                    items[0].click();
                    return {status:'picked', text: items[0].textContent.trim()};
                }""")
                print(f"  L{ki+1}: {lvl}")
                if lvl.get('status') == 'no_menus': break
                time.sleep(0.5)
            print("  [OK] 系统版本号已完成")
        else:
            _modal_cascader_done = False
            print("  🔧 弹窗模式 → 变更系统（cascader搜索+菜单选择）...")

            click_sys = ep.evaluate("""() => {
                const viz = el => el && el.offsetParent !== null;
                for(const m of document.querySelectorAll('.ant-drawer-body, .ant-modal-body, .ant-drawer-content, .ant-modal-content')){
                    if(!viz(m)) continue;
                    for(const fi of m.querySelectorAll('.ant-form-item, .formfield, .ant-row')){
                        const lbl = fi.querySelector('.fieldlabel, .ant-form-item-label label');
                        if(!lbl) continue;
                        const lt = (lbl.textContent||'').trim();
                        if(!lt.includes('系统名称') && !lt.includes('变更系统')) continue;
                        const casInput = fi.querySelector('.ant-cascader-input[placeholder*="搜索"]');
                        if(casInput && viz(casInput)){ casInput.click(); return {status:'clicked'}; }
                        const casInput2 = fi.querySelector('.ant-cascader-input');
                        if(casInput2 && viz(casInput2) && !casInput2.readOnly){ casInput2.click(); return {status:'clicked_input'}; }
                        const picker = fi.querySelector('.ant-cascader-picker');
                        if(picker && viz(picker)){ picker.click(); return {status:'clicked_picker'}; }
                    }
                }
                return {status:'not_found'};
            }""")
            print(f"  变更系统触发: {click_sys}")

            if click_sys.get('status') not in ('clicked', 'clicked_input', 'clicked_picker'):
                print("  ❌ 弹窗内未找到变更系统cascader!")
            else:
                time.sleep(1.2)
                type_r = ep.evaluate("""() => {
                    const viz = el => el && el.offsetParent !== null;
                    for(const m of document.querySelectorAll('.ant-drawer-body, .ant-modal-body, .ant-drawer-content, .ant-modal-content')){
                        if(!viz(m)) continue;
                        const si = m.querySelector('.ant-cascader-input[placeholder*="搜索"]');
                        if(si && viz(si)){ si.focus(); si.select(); return {ok:true, source:'modal_scoped'}; }
                    }
                    for(const cm of document.querySelectorAll('.ant-cascader-menus')){
                        if(!viz(cm)) continue;
                        const si = cm.querySelector('.ant-cascader-input[placeholder*="搜索"]');
                        if(si && viz(si)){ si.focus(); si.select(); return {ok:true, source:'menus_scoped'}; }
                    }
                    for(const m of document.querySelectorAll('.ant-drawer-body, .ant-modal-body')){
                        if(!viz(m)) continue;
                        const inp = m.querySelector('.ant-cascader-input');
                        if(inp && viz(inp) && !inp.readOnly){ inp.focus(); inp.select(); return {ok:true, source:'modal_input'}; }
                    }
                    return {ok:false};
                }""")

                if type_r.get('ok'):
                    ep.keyboard.type(sysver_path[-1], delay=50)
                    print(f"  ✓ 已输入关键词: {sysver_path[-1]}")
                    time.sleep(1.2)

                    sel = ep.evaluate("""(kw) => {
                        const viz = el => el && el.offsetParent !== null;
                        for(const cm of document.querySelectorAll('.ant-cascader-menus')){
                            if(!viz(cm)) continue;
                            for(const menu of cm.querySelectorAll('.ant-cascader-menu')){
                                if(!viz(menu)) continue;
                                const items = menu.querySelectorAll('.ant-cascader-menu-item');
                                for(const item of items){
                                    if(!viz(item)) continue;
                                    if(item.classList.contains('ant-cascader-menu-item-disabled')) continue;
                                    const txt = (item.textContent||'').trim();
                                    if(txt && txt.includes(kw)){ item.click(); return {status:'picked', text:txt, col:0}; }
                                }
                                for(const item of items){
                                    if(!viz(item)) continue;
                                    if(item.classList.contains('ant-cascader-menu-item-disabled')) continue;
                                    const txt = (item.textContent||'').trim();
                                    if(txt){ item.click(); return {status:'picked', text:txt, col:0, fallback:true}; }
                                }
                            }
                        }
                        return {status:'no_options'};
                    }""", sysver_path[-1])
                    print(f"  变更系统选择: {sel}")

                    if sel.get('status') == 'picked':
                        time.sleep(0.8)
                        cascade = ep.evaluate("""(kw) => {
                            const viz = el => el && el.offsetParent !== null;
                            for(const cm of document.querySelectorAll('.ant-cascader-menus')){
                                if(!viz(cm)) continue;
                                const menus = cm.querySelectorAll('.ant-cascader-menu');
                                let visibleCount = 0;
                                for(const m of menus){ if(viz(m)) visibleCount++; }
                                if(visibleCount >= 2){
                                    const last = menus[visibleCount - 1];
                                    const items = last.querySelectorAll('.ant-cascader-menu-item');
                                    for(const item of items){
                                        if(!viz(item)) continue;
                                        if(item.classList.contains('ant-cascader-menu-item-disabled')) continue;
                                        const txt = (item.textContent||'').trim();
                                        if(txt && txt.includes(kw)){ item.click(); return {status:'cascade_picked', text:txt}; }
                                    }
                                    for(const item of items){
                                        if(!viz(item)) continue;
                                        if(item.classList.contains('ant-cascader-menu-item-disabled')) continue;
                                        const txt = (item.textContent||'').trim();
                                        if(txt){ item.click(); return {status:'cascade_picked', text:txt}; }
                                    }
                                    return {status:'cascade_no_items'};
                                }
                                return {status:'done'};
                            }
                            return {status:'no_visible_menus'};
                        }""", sysver_path[-1])
                        if cascade.get('status') == 'cascade_picked':
                            print(f"  级联选择: {cascade}")
                            time.sleep(0.6)
                            cascade3 = ep.evaluate("""(kw) => {
                                const viz = el => el && el.offsetParent !== null;
                                for(const cm of document.querySelectorAll('.ant-cascader-menus')){
                                    if(!viz(cm)) continue;
                                    const menus = cm.querySelectorAll('.ant-cascader-menu');
                                    let vc = 0;
                                    for(const m of menus){ if(viz(m)) vc++; }
                                    if(vc >= 3){
                                        const last = menus[vc - 1];
                                        const items = last.querySelectorAll('.ant-cascader-menu-item');
                                        for(const item of items){
                                            if(!viz(item)) continue;
                                            if(item.classList.contains('ant-cascader-menu-item-disabled')) continue;
                                            const txt = (item.textContent||'').trim();
                                            if(txt && txt.includes(kw)){ item.click(); return {status:'cascade3_picked', text:txt}; }
                                        }
                                        for(const item of items){
                                            if(!viz(item)) continue;
                                            if(item.classList.contains('ant-cascader-menu-item-disabled')) continue;
                                            const txt = (item.textContent||'').trim();
                                            if(txt){ item.click(); return {status:'cascade3_picked', text:txt}; }
                                        }
                                    }
                                    return {status:'done'};
                                }
                                return {status:'done'};
                            }""", sysver_path[-1])
                            if cascade3.get('status') == 'cascade3_picked':
                                print(f"  第3级选择: {cascade3}")
                        print("  [OK] 弹窗内变更系统已完成")
                        _modal_cascader_done = True

                        print("  ⏳ 等待 cascader 下拉菜单关闭...")
                        for _ in range(20):
                            still_open = ep.evaluate("""() => {
                                for(const cm of document.querySelectorAll('.ant-cascader-menus')){
                                    if(cm.offsetParent !== null) return true;
                                }
                                return false;
                            }""")
                            if not still_open:
                                print("  ✓ cascader overlay 已关闭")
                                break
                            time.sleep(0.1)
                    else:
                        print("  ⚠️ 未找到可选下拉项!")
                else:
                    print("  ❌ 未找到cascader面板搜索框!")

            if not _modal_cascader_done:
                print("  ⚠ 变更系统未完成，跳过系统版本号填充")
            else:
                print("  🔧 弹窗模式 → 系统版本号（ant-select + empty guard）...")
                sv_empty = ep.evaluate("""() => {
                    for(const m of document.querySelectorAll('.ant-modal-body, .ant-modal-content, .ant-drawer-body, .ant-drawer-content')){
                        if(!m.offsetParent) continue;
                        for(const fi of m.querySelectorAll('.ant-form-item, .formfield, .ant-row')){
                            const lbl = fi.querySelector('.fieldlabel, .ant-form-item-label label');
                            if(!lbl) continue;
                            const lt = (lbl.textContent||'').trim();
                            if(!lt.includes('系统版本号') && !lt.includes('版本号')) continue;
                            const sel = fi.querySelector('.ant-select');
                            if(!sel || !sel.offsetParent) continue;
                            const selVal = sel.querySelector('.ant-select-selection-selected-value');
                            if(selVal) return {empty:false, value: selVal.textContent.trim()};
                            return {empty:true, value:''};
                        }
                    }
                    return {empty:true, value:'?', note:'no_label_match'};
                }""")
                print(f"  系统版本号当前值: {sv_empty}")

                if not sv_empty.get('empty', True):
                    print(f"  ⚠ 系统版本号已有值 '{sv_empty.get('value')}'，跳过填充")
                else:
                    time.sleep(0.5)
                    trigger = ep.evaluate("""() => {
                        const selects = [];
                        for(const m of document.querySelectorAll('.ant-modal-body, .ant-modal-content, .ant-drawer-body, .ant-drawer-content')){
                            if(!m.offsetParent) continue;
                            for(const sel of m.querySelectorAll('.ant-select:not(.ant-select-disabled)')){
                                if(sel.closest('.ant-cascader-picker')) continue;
                                if(!sel.offsetParent) continue;
                                const r = sel.getBoundingClientRect();
                                selects.push({el: sel, y: r.y, x: r.x});
                            }
                        }
                        if(selects.length === 0) return {status:'no_select'};
                        selects.sort((a,b) => b.y - a.y);
                        selects[0].el.click();
                        return {status:'clicked', y: selects[0].y, total: selects.length};
                    }""")
                    print(f"  系统版本号触发: {trigger}")

                    if trigger.get('status') == 'clicked':
                        time.sleep(0.8)
                        select_result = ep.evaluate("""() => {
                            for(const dd of document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)')){
                                if(!dd.offsetParent) continue;
                                for(const item of dd.querySelectorAll('.ant-select-dropdown-menu-item')){
                                    if(!item.offsetParent) continue;
                                    const cls = item.className||'';
                                    if(cls.includes('disabled')) continue;
                                    const txt = item.textContent.trim();
                                    if(txt){ item.click(); return {status:'picked', text: txt}; }
                                }
                            }
                            return {status:'no_options'};
                        }""")
                        print(f"  系统版本号选择: {select_result}")
                    else:
                        print("  ⚠ 未找到系统版本号 ant-select!")

            print("  ⏳ 等待 select 下拉关闭...")
            for _ in range(20):
                sel_open = ep.evaluate("""() => {
                    for(const dd of document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)')){
                        if(dd.offsetParent !== null) return true;
                    }
                    return false;
                }""")
                if not sel_open: break
                time.sleep(0.1)
            time.sleep(0.3)

            confirmed = ep.evaluate("""() => {
                for(const m of document.querySelectorAll('.ant-modal-wrap, .ant-modal, .ant-drawer, [role="dialog"]')){
                    if(!m.offsetParent) continue;
                    for(const b of m.querySelectorAll('button, .ant-btn')){
                        if(!b.offsetParent || !b.offsetWidth) continue;
                        const t = (b.textContent||'').trim();
                        if(t === '确定' || t === '确认' || t === '确 定'){
                            b.click(); return 'ok';
                        }
                    }
                }
                return 'not_found';
            }""")
            print(f"  弹窗确定: {confirmed}")
            time.sleep(0.4)
            print("  [OK] 系统版本号已完成")
    else:
        # 针对 jzjy/cszx/dynamic 等普通系统：模糊匹配日期版本号
        page_title = ep.evaluate("""() => {
            const items = document.querySelectorAll('.formfield');
            for(const item of items){
                const lbl = item.querySelector('.fieldlabel');
                if(lbl && lbl.textContent.includes('标题')){
                    return item.querySelector('input[type=text]')?.value || '';
                }
            }
            return '';
        }""")
        current_title = page_title if page_title else title_text
        date_match = re.search(r'(\d{4})[-./]?(\d{2})[-./]?(\d{2})', current_title)
        if date_match:
            month = str(int(date_match.group(2)))
            day = str(int(date_match.group(3)))
            version_pattern = f"{month}.{day}"
        else:
            version_pattern = f"{SAT_M}.{SAT_D}"

        print("\n" + "=" * 55)
        print(f"[9.3] 系统版本号 → 模糊匹配日期 '{version_pattern}'...")
        ep.keyboard.press("Escape"); time.sleep(0.3)
        ver_trigger = ep.evaluate("""() => {
            const items = document.querySelectorAll('.formfield');
            for(const item of items){
                if(item.querySelector('.fieldlabel')?.textContent.includes('系统版本号')){
                    item.querySelector('.ant-select')?.click(); return 'clicked';
                }
            }
            return 'fail';
        }""")
        if ver_trigger == 'clicked':
            matched_option = None
            available_list = []
            for _ in range(10):
                time.sleep(0.5)
                ver_match = ep.evaluate("""(pattern) => {
                    const activeDropdowns = Array.from(document.querySelectorAll('.ant-select-dropdown'))
                        .filter(d => d.offsetParent !== null);
                    if (activeDropdowns.length === 0) return {success: false, reason: 'no_active_dropdown'};
                    
                    const activeDropdown = activeDropdowns[0];
                    const opts = activeDropdown.querySelectorAll('[role=option], .ant-select-dropdown-menu-item, li');
                    const visible = Array.from(opts).filter(o => o.offsetParent !== null);
                    for(const o of visible){
                        const t = (o.textContent || '').trim();
                        if(t.includes(pattern)){
                            o.click();
                            return {success: true, matched_text: t};
                        }
                    }
                    return {success: false, options: visible.map(o => (o.textContent || '').trim())};
                }""", version_pattern)
                if ver_match.get("success"):
                    matched_option = ver_match.get("matched_text")
                    break
                else:
                    available_list = ver_match.get("options", [])
            if matched_option:
                print(f"  ✓ 成功模糊匹配并选择第一个版本: '{matched_option}'")
            else:
                print(f"  ❌ 未能模糊匹配到包含 '{version_pattern}' 的系统版本选项。可用选项为: {available_list}")
        ep.keyboard.press("Escape"); time.sleep(0.3)

    # ==================== [9.35] 变更分类保护复查 (防误触) ====================
    if SAVED_CLASSIFY_VALUE and SAVED_CLASSIFY_VALUE != '(空)':
        classify_now = ep.evaluate("""() => {
            const items = document.querySelectorAll('.formfield');
            for(const item of items){
                const lbl = item.querySelector('.fieldlabel');
                if(!lbl) continue;
                if(!lbl.textContent.includes('分类') || !lbl.textContent.includes('变更')) continue;
                const content = item.querySelector('.fieldcontent');
                if(!content) continue;
                const selVal = content.querySelector('.ant-select-selection-selected-value');
                if(selVal) return selVal.textContent.trim();
                const inp = content.querySelector('input');
                if(inp) return inp.value || '';
            }
            return '';
        }""")
        if classify_now and classify_now != SAVED_CLASSIFY_VALUE:
            print(f"  ⚠ 变更分类被误改! 原值='{SAVED_CLASSIFY_VALUE}' 当前='{classify_now}' → 回滚...")
            ep.evaluate(f"""(orig) => {{
                for(const item of document.querySelectorAll('.formfield')){{
                    const lbl = item.querySelector('.fieldlabel');
                    if(!lbl || !lbl.textContent.includes('变更分类')) continue;
                    const pk = item.querySelector('.ant-cascader-picker');
                    if(pk && pk.offsetParent) pk.click();
                    setTimeout(() => {{
                        const inp = item.querySelector('.ant-cascader-input input') || item.querySelector('input');
                        if(inp){{ inp.focus(); inp.click(); }}
                    }}, 200);
                }}
                return 'triggered';
            }}(`{SAVED_CLASSIFY_VALUE!r}`)""")
            time.sleep(1.0)
            classify_after = ep.evaluate("""() => {
                const items = document.querySelectorAll('.formfield');
                for(const item of items){
                    const lbl = item.querySelector('.fieldlabel');
                    if(!lbl || !lbl.textContent.includes('变更分类')) continue;
                    const selVal = item.querySelector('.ant-select-selection-selected-value');
                    if(selVal) return selVal.textContent.trim();
                }
                return '';
            }""")
            if classify_after == SAVED_CLASSIFY_VALUE:
                print(f"  ✅ 变更分类已恢复: '{classify_after}'")
            else:
                print(f"  ❌ 变更分类恢复失败! 当前='{classify_after}'")
        else:
            print(f"  ✓ 变更分类未变: '{classify_now}'")

    # ==================== [9.4] 变更内容 → 新增弹窗全选确定 ====================
    print("\n" + "=" * 55)
    print("[9.4] 变更内容 → 点击新增，弹窗全选，确定...")

    ep.keyboard.press("Escape"); time.sleep(0.3)
    add_clicked = ep.evaluate("""(kw) => {
        function norm(t) { return (t||'').replace(/[\\s\\u00a0\\u3000]+/g, ''); }
        function isAddBtn(t) {
            const n = norm(t);
            return n === '\\u65b0\\u589e' || n === '+\\u65b0\\u589e' ||
                   n === '\\u6dfb\\u52a0' || n === '+\\u6dfb\\u52a0';
        }
        function isNoiseNode(el) {
            while (el) {
                const cls = String(el.className || '').toLowerCase();
                const id = String(el.id || '').toLowerCase();
                const tag = String(el.tagName || '').toLowerCase();
                if (cls.includes('anchor') || 
                    cls.includes('menu') || 
                    cls.includes('sidebar') || 
                    cls.includes('sider') || 
                    cls.includes('navbar') || 
                    cls.includes('ant-tabs-nav') || 
                    cls.includes('ant-tabs-tab-btn') || 
                    tag === 'nav' || 
                    id.includes('anchor') || 
                    id.includes('menu') || 
                    id.includes('sidebar')) {
                    return true;
                }
                el = el.parentElement;
            }
            return false;
        }

        const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let kwNode = null, tn;
        while(tn = tw.nextNode()){
            if(tn.textContent.includes(kw) && tn.parentElement){
                const pe = tn.parentElement;
                if(pe.offsetParent !== null && !isNoiseNode(pe)){
                    kwNode = pe;
                    pe.scrollIntoView({block: 'center', behavior: 'instant'});
                    break;
                }
            }
        }
        if(!kwNode){ return 'kw_not_found:' + kw; }
        const kwRect = kwNode.getBoundingClientRect();
        const kwY = kwRect.top + kwRect.height / 2;
        const allBtns = document.querySelectorAll('button, .ant-btn, span[role="button"], a');
        let bestBtn = null, bestDist = Infinity, bestInfo = '';
        for(const btn of allBtns){
            if(btn.offsetParent === null) continue;
            if(!isAddBtn(btn.textContent)) continue;
            const btnRect = btn.getBoundingClientRect();
            const btnY = btnRect.top + btnRect.height / 2;
            let vertDist = btnY - kwY;
            if(vertDist < 0) vertDist = Math.abs(vertDist) * 3;
            const horizDist = Math.abs(btnRect.left + btnRect.width/2 - kwRect.left - kwRect.width/2);
            const dist = vertDist + horizDist * 0.3;
            if(dist < bestDist){
                bestDist = dist;
                bestBtn = btn;
                bestInfo = 'proximity:vert=' + vertDist.toFixed(0) + ' horiz=' + horizDist.toFixed(0);
            }
        }
        if(bestBtn){
            bestBtn.click();
            return 'proximity:' + bestInfo;
        }
        return 'no_add_btn';
    }""", "变更内容")
    print(f"  新增按钮: {add_clicked}")
    time.sleep(10.0)

    check_result = ep.evaluate("""() => {
        function isVis(el){
            if(!el) return false;
            const s = window.getComputedStyle(el);
            return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
        }
        const wraps = document.querySelectorAll('.ant-modal-wrap');
        let targetModal = null;
        for(const wrap of wraps){
            if(!isVis(wrap) || wrap.classList.contains('ant-modal-wrap-hidden')) continue;
            const titleEl = wrap.querySelector('.ant-modal-title');
            if(titleEl && (titleEl.textContent||'').includes('选择变更内容')){
                targetModal = wrap; break;
            }
            const body = wrap.querySelector('.ant-modal-body');
            if(body && body.querySelector('table')){ targetModal = wrap; break; }
        }
        if(!targetModal) return {status:'no_modal'};

        const thead = targetModal.querySelector('thead');
        if(thead){
            const firstTh = thead.querySelector('th');
            if(firstTh){
                const ckWrap = firstTh.querySelector('.ant-checkbox-wrapper, .ant-checkbox');
                const ckInput = firstTh.querySelector('.ant-checkbox-input');
                if(ckWrap || ckInput){
                    (ckWrap || ckInput).click();
                    return {status:'clicked_header', thText: (firstTh.textContent||'').trim().substring(0,30)};
                }
            }
        }

        const allChecks = targetModal.querySelectorAll('.ant-checkbox-input, .ant-checkbox-wrapper');
        for(const ck of allChecks){
            if(!isVis(checkpoint)) continue;
            const th = ck.closest('th');
            if(th){
                ck.click();
                return {status:'clicked_first_th', thText: (th.textContent||'').trim().substring(0,30)};
            }
        }

        const allTh = targetModal.querySelectorAll('th');
        for(const th of allTh){
            const txt = (th.textContent||'').trim();
            if(txt.includes('需求/Story') || txt.includes('Story')){
                const ck = th.querySelector('.ant-checkbox-input, .ant-checkbox-wrapper');
                if(ck && isVis(ck)){
                    ck.click();
                    return {status:'clicked_story_th', thText: txt.substring(0,30)};
                }
            }
        }
        return {status:'not_found', modalTitle: (targetModal.querySelector('.ant-modal-title')||{}).textContent||''};
    }""")
    print(f"  全选: {check_result}")
    time.sleep(0.5)

    confirm_result = ep.evaluate("""() => {
        function isVis(el){
            if(!el) return false;
            const s = window.getComputedStyle(el);
            return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
        }
        const wraps = document.querySelectorAll('.ant-modal-wrap');
        let targetModal = null;
        for(const wrap of wraps){
            if(!isVis(wrap) || wrap.classList.contains('ant-modal-wrap-hidden')) continue;
            const titleEl = wrap.querySelector('.ant-modal-title');
            if(titleEl && (titleEl.textContent||'').includes('选择变更内容')){
                targetModal = wrap; break;
            }
        }
        if(!targetModal){
            for(const wrap of wraps){
                if(isVis(wrap) && !wrap.classList.contains('ant-modal-wrap-hidden')){
                    targetModal = wrap; break;
                }
            }
        }
        if(!targetModal) return {status:'no_modal'};

        const footer = targetModal.querySelector('.ant-modal-footer');
        if(footer){
            const btns = footer.querySelectorAll('button, .ant-btn');
            for(const btn of btns){
                if(!isVis(btn)) continue;
                const bt = (btn.textContent||'').trim();
                if(bt === '确定' || bt === '确 定'){
                    btn.click();
                    return {status:'confirmed_footer', btnText: bt};
                }
            }
            for(const btn of footer.querySelectorAll('.ant-btn-primary')){
                if(isVis(btn)){
                    btn.click();
                    return {status:'confirmed_primary', btnText: (btn.textContent||'').trim()};
                }
            }
        }

        const allBtns = targetModal.querySelectorAll('button, .ant-btn');
        for(const btn of allBtns){
            if(!isVis(btn)) continue;
            const bt = (btn.textContent||'').trim();
            if(bt === '确定' || bt === '确 定'){
                btn.click();
                return {status:'confirmed_any', btnText: bt};
            }
        }
        return {status:'not_found', modalTitle: (targetModal.querySelector('.ant-modal-title')||{}).textContent||''};
    }""")
    print(f"  确定: {confirm_result}")
    time.sleep(1.0)

    for _ in range(30):
        modal_open = ep.evaluate("""() => {
            for(const m of document.querySelectorAll('.ant-modal-wrap')){
                const s = window.getComputedStyle(m);
                if(s.display !== 'none' && s.visibility !== 'hidden' && !m.classList.contains('ant-modal-wrap-hidden')){
                    return true;
                }
            }
            return false;
        }""")
        if not modal_open:
            break
        time.sleep(0.1)
    else:
        ep.keyboard.press("Escape")
        time.sleep(0.5)
    print("  [OK] 变更内容已完成")

    # ==================== [9.5] 版本地址 ====================
    default_url = active_cfg["version_url"]
    
    # 查找 版本地址.txt
    addr_file = None
    for start_dir in [os.getcwd(), SCRIPT_DIR]:
        cur = start_dir
        for _ in range(6):
            p = os.path.join(cur, "版本地址.txt")
            if os.path.exists(p):
                addr_file = p
                break
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        if addr_file:
            break
            
    if not addr_file:
        alt_path = "/Volumes/Macintosh HD_Data/WorkBuddy/版本发布/版本地址.txt"
        if os.path.exists(alt_path):
            addr_file = alt_path

    version_url = default_url
    if addr_file:
        print(f"\n  [版本地址] 找到地址文件: {addr_file}")
        try:
            with open(addr_file, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f.read().splitlines() if l.strip()]
            url_map = {}
            for i in range(0, len(lines) - 1, 2):
                k = lines[i]
                v = lines[i+1]
                if "集中交易" in k or "jzjy" in k.lower():
                    url_map["jzjy"] = v
                elif "参数" in k or "cszx" in k.lower():
                    url_map["cszx"] = v
                elif "信创" in k or "95" in k.lower() or "xinchuang" in k.lower():
                    url_map["95xinchuang"] = v
                elif "创新" in k or "98" in k.lower() or "chuangxin" in k.lower():
                    url_map["98chuangxin"] = v
                else:
                    url_map[k] = v
            
            matched = url_map.get(MODE)
            if matched:
                version_url = matched
                print(f"  [版本地址] 匹配到 {MODE} 地址: {version_url}")
            else:
                for k, v in url_map.items():
                    if MODE in k or k in MODE:
                        version_url = v
                        print(f"  [版本地址] 模糊匹配 {MODE} -> {k} 地址: {version_url}")
                        break
        except Exception as e:
            print(f"  [版本地址] 解析失败: {e}")
    else:
        print(f"\n  [版本地址] 未找到 版本地址.txt，使用默认地址")

    print("\n" + "=" * 55)
    print(f"[9.5] 版本地址 → {version_url}...")
    fill_input_by_label(ep, "版本地址", version_url, "版本地址")

    # ==================== [10] 预估变更操作耗时 → 10分钟至30分钟 ====================
    print("\n" + "=" * 55)
    print("[10] 预估变更操作耗时 → 10分钟至30分钟...")
    fill_dropdown_by_label(ep, "预估变更操作耗时", "10分钟至30分钟", "预估变更操作耗时")

    # ==================== [11] 回退用时 → 30分钟内 ====================
    print("\n" + "=" * 55)
    print("[11] 回退用时 → 30分钟内...")
    fill_dropdown_by_label(ep, "回退用时", "30分钟内", "回退用时")

    # ==================== [12] 导致业务/系统中断时间 → 无中断 ====================
    print("\n" + "=" * 55)
    print("[12] 导致业务/系统中断时间 → 无中断...")
    fill_dropdown_by_label(ep, "中断", "无中断", "导致业务/系统中断时间")

    # ==================== [13] 是否停机 → 是 ====================
    print("\n" + "=" * 55)
    print("[13] 是否停机 → 是...")
    fill_radio_by_label(ep, "停机", "是", "是否停机")

    # ==================== [13.5] 实施负责人 ====================
    owner_search = active_cfg["owner"]
    owner_name = active_cfg["owner_name"]
    print("\n" + "=" * 55)
    print(f"[13.5] 实施负责人 → 弹窗搜索树勾选 (固定: {owner_search})...")
    ep.keyboard.press("Escape"); time.sleep(0.5)

    trigger_result = ep.evaluate("""() => {
        const items = document.querySelectorAll('.formfield');
        for(const item of items){
            const lbl = item.querySelector('.fieldlabel');
            if(lbl && lbl.textContent.includes('实施负责人') && !lbl.textContent.includes('审核') && !lbl.textContent.includes('确认') && !lbl.textContent.includes('测试')){
                const content = item.querySelector('.fieldcontent');
                if(!content) return 'no_content';
                const tryOrder = [
                    content.querySelector('.ant-select-selection'),
                    content.querySelector('.ant-select'),
                    content.querySelector('input:not([type="hidden"])'),
                    content
                ];
                for(const el of tryOrder){
                    if(el && window.getComputedStyle(el).display !== 'none'){ el.click(); return 'clicked'; }
                }
                return 'nothing_clickable';
            }
        }
        return 'not_found';
    }""")
    print(f"  触发实施负责人: {trigger_result}")
    time.sleep(1.5)

    search_result = ep.evaluate("""(keyword) => {
        const selectors = [
            '.ant-select-search__field',
            '.ant-select-selection-search-input',
            'input.ant-input[placeholder*="搜索"]',
            '.ant-select-dropdown input'
        ];
        for(const sel of selectors){
            const inputs = document.querySelectorAll(sel);
            for(const inp of inputs){
                if(inp.offsetParent !== null && !inp.readOnly && !inp.disabled){
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    nativeInputValueSetter.call(inp, keyword);
                    inp.dispatchEvent(new Event('input', {bubbles: true}));
                    inp.dispatchEvent(new Event('change', {bubbles: true}));
                    return {ok: true, source: sel};
                }
            }
        }
        const allInputs = document.querySelectorAll('input');
        for(const inp of allInputs){
            if(inp.offsetParent !== null && !inp.readOnly && !inp.disabled && inp.type !== 'hidden'){
                const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                nativeInputValueSetter.call(inp, keyword);
                inp.dispatchEvent(new Event('input', {bubbles: true}));
                return {ok: true, source: 'fallback_input'};
            }
        }
        return {ok: false};
    }""", owner_search)
    print(f"  ant-select搜索框输入: {search_result}")

    if search_result.get('ok'):
        ep.keyboard.press("Enter")
        print("  已按回车（触发弹窗）")
        time.sleep(1.5)

    modal_check = ep.evaluate("""(keyword) => {
        function isVis(el){
            if(!el) return false;
            const s = window.getComputedStyle(el);
            return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
        }
        const modals = document.querySelectorAll('.ant-modal-wrap');
        let modalBody = null;
        for(const m of modals){
            if(!isVis(m) || m.classList.contains('ant-modal-wrap-hidden')) continue;
            const body = m.querySelector('.ant-modal-body');
            if(body && body.children.length > 0){ modalBody = body; break; }
        }
        if(!modalBody) return {found: false};
        const input = modalBody.querySelector('.ant-input-affix-wrapper input.ant-input');
        if(!input) return {found: true, hasInput: false, treeChildCount: modalBody.querySelectorAll('.ant-tree-treenode').length};
        input.focus();
        input.value = '';
        input.dispatchEvent(new Event('input', {bubbles: true}));
        return {found: true, hasInput: true, treeChildCount: modalBody.querySelectorAll('.ant-tree-treenode').length, inputFocused: document.activeElement === input};
    }""", owner_search)
    print(f"  Modal检查: {modal_check}")

    if modal_check.get('found') and modal_check.get('hasInput'):
        type_result = ep.evaluate("""(keyword) => {
            function isVis(el){
                if(!el) return false;
                const s = window.getComputedStyle(el);
                return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
            }
            const modals = document.querySelectorAll('.ant-modal-wrap');
            let modalBody = null;
            for(const m of modals){
                if(!isVis(m) || m.classList.contains('ant-modal-wrap-hidden')) continue;
                const body = m.querySelector('.ant-modal-body');
                if(body && body.children.length > 0){ modalBody = body; break; }
            }
            if(!modalBody) return {ok: false, reason: 'no_modal'};
            const input = modalBody.querySelector('.ant-input-affix-wrapper input.ant-input');
            if(!input) return {ok: false, reason: 'no_input'};
            input.focus();
            input.value = '';
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            nativeInputValueSetter.call(input, keyword);
            input.dispatchEvent(new Event('keydown', {bubbles: true}));
            input.dispatchEvent(new Event('input', {bubbles: true}));
            input.dispatchEvent(new Event('keyup', {bubbles: true}));
            input.dispatchEvent(new Event('change', {bubbles: true}));
            const enterEvent = new KeyboardEvent('keydown', {
                key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
            });
            input.dispatchEvent(enterEvent);
            input.dispatchEvent(new KeyboardEvent('keyup', {
                key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
            }));
            return {ok: true, inputValue: input.value};
        }""", owner_search)
        print(f"  Modal搜索(含Enter): {type_result}")
        time.sleep(2.5)
    elif modal_check.get('found'):
        print(f"  Modal已出现，无搜索框，直接在树中查找")
        time.sleep(1.0)

    tree_result = ep.evaluate("""(keyword) => {
        function isVis(el){
            if(!el) return false;
            const s = window.getComputedStyle(el);
            return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
        }
        const modals = document.querySelectorAll('.ant-modal-wrap');
        let modalBody = null;
        for(const m of modals){
            if(!isVis(m) || m.classList.contains('ant-modal-wrap-hidden')) continue;
            const body = m.querySelector('.ant-modal-body');
            if(body && body.children.length > 0){ modalBody = body; break; }
        }
        if(!modalBody) return {status: 'no_modal'};

        const treeNodes = modalBody.querySelectorAll('.ant-tree-treenode');
        for(const node of treeNodes){
            if(!isVis(node)) continue;
            const title = node.querySelector('.ant-tree-title');
            if(!title) continue;
            const titleText = (title.textContent || '').trim();
            if(titleText.includes(keyword)){
                const checkbox = node.querySelector('.ant-tree-checkbox');
                if(checkbox){
                    checkbox.click();
                    return {status: 'checked', text: titleText.substring(0, 60)};
                }
                title.click();
                return {status: 'clicked_title', text: titleText.substring(0, 60)};
            }
        }
        const allTitles = modalBody.querySelectorAll('.ant-tree-title');
        for(const t of allTitles){
            if(!isVis(t)) continue;
            const txt = (t.textContent || '').trim();
            if(txt.includes(keyword)){
                let el = t.parentElement;
                while(el){
                    const cb = el.querySelector('.ant-tree-checkbox');
                    if(cb && isVis(cb)){ cb.click(); return {status: 'checked_ancestor', text: txt.substring(0, 60)}; }
                    if(el.classList.contains('ant-tree')) break;
                    el = el.parentElement;
                }
                let sib = t.previousElementSibling;
                while(sib){
                    if(sib.classList.contains('ant-tree-checkbox')){ sib.click(); return {status: 'checked_sibling_prev', text: txt.substring(0, 60)}; }
                    sib = sib.previousElementSibling;
                }
                sib = t.nextElementSibling;
                while(sib){
                    if(sib.classList.contains('ant-tree-checkbox')){ sib.click(); return {status: 'checked_sibling_next', text: txt.substring(0, 60)}; }
                    sib = sib.nextElementSibling;
                }
                const parent = t.parentElement;
                if(parent){
                    const cb = parent.querySelector('.ant-tree-checkbox');
                    if(cb && isVis(cb)){ cb.click(); return {status: 'checked_parent', text: txt.substring(0, 60)}; }
                }
                t.click();
                return {status: 'clicked_title_fallback', text: txt.substring(0, 60)};
            }
        }
        return {status: 'not_found'};
    }""", owner_search)
    print(f"  树节点勾选: {tree_result}")
    time.sleep(0.8)

    if tree_result.get('status', '').startswith('checked') or tree_result.get('status', '').startswith('clicked'):
        confirm_result = ep.evaluate("""() => {
            function isVis(el){
                if(!el) return false;
                const s = window.getComputedStyle(el);
                return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
            }
            const modals = document.querySelectorAll('.ant-modal-wrap');
            for(const m of modals){
                if(!isVis(m) || m.classList.contains('ant-modal-wrap-hidden')) continue;
                const footer = m.querySelector('.ant-modal-footer');
                if(!footer) continue;
                for(const btn of footer.querySelectorAll('button, .ant-btn')){
                    if(!isVis(btn)) continue;
                    const bt = (btn.textContent || '').trim();
                    if(bt === '确 定' || bt === '确定' || bt === '确认'){
                        btn.click(); return {status: 'confirmed', source: 'modal_footer', btnText: bt};
                    }
                }
                for(const btn of footer.querySelectorAll('.ant-btn-primary')){
                    if(isVis(btn)){ btn.click(); return {status: 'confirmed_primary'}; }
                }
            }
            return {status: 'no_confirm_btn'};
        }""")
        print(f"  确认按钮: {confirm_result}")
        if confirm_result.get('status', '').startswith('confirmed'):
            print(f"  ✅ 已选: {owner_search}")
            time.sleep(1.5)
            cleanup = ep.evaluate("""(params) => {
                const items = document.querySelectorAll('.formfield');
                for(const item of items){
                    const lbl = item.querySelector('.fieldlabel');
                    if(lbl && lbl.textContent.includes('实施负责人') && !lbl.textContent.includes('审核') && !lbl.textContent.includes('确认') && !lbl.textContent.includes('测试')){
                        const content = item.querySelector('.fieldcontent');
                        if(!content) return 'no_content';
                        let removed = 0;
                        const searchInput = content.querySelector('.ant-select-selection-search-input, input.ant-select-search__field');
                        if(searchInput && searchInput.value){
                            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                            nativeSetter.call(searchInput, '');
                            searchInput.dispatchEvent(new Event('input', {bubbles: true}));
                            removed++;
                        }
                        const choices = content.querySelectorAll('.ant-select-selection__choice, .ant-select-selection-item');
                        for(const ch of choices){
                            const txt = (ch.textContent || '').replace('×', '').trim();
                            if(txt === params.ownerName){
                                const removeBtn = ch.querySelector('.ant-select-selection__choice__remove, .anticon-close');
                                if(removeBtn){ removeBtn.click(); removed++; }
                                else { ch.dispatchEvent(new MouseEvent('click', {bubbles: true})); removed++; }
                            }
                        }
                        return {removed, choiceCount: choices.length};
                    }
                }
                return 'not_found';
            }""", {'ownerName': owner_name})
            print(f"  清理残留标签: {cleanup}")
        else:
            print(f"  ⚠ 勾选成功但确认按钮未找到: {confirm_result}")
    else:
        print(f"  ⚠ 未在树中找到 {owner_search}: {tree_result}")

    time.sleep(1.0)

    # ==================== [14] 变更需求类型 ====================
    print("\n" + "=" * 55)
    print("[14] 变更需求类型 → 普通业务功能...")
    fill_dropdown_by_label(ep, "变更需求类型", "普通业务功能", "变更需求类型")

    # ==================== [15] 实施复杂度 ====================
    print("\n" + "=" * 55)
    print("[15] 实施复杂度 → 跨系统...")
    fill_dropdown_by_label(ep, "实施复杂度", "跨系统", "实施复杂度")

    # ==================== [16] 变更组件 ====================
    print("\n" + "=" * 55)
    print(f"[16] 变更组件 → {active_cfg['components']}...")
    fill_checkbox_by_label(ep, "变更组件", active_cfg["components"], "变更组件")

    # ==================== [17] 影响业务功能 ====================
    print("\n" + "=" * 55)
    print(f"[17] 影响业务功能 → {active_cfg['business_functions']}...")
    fill_checkbox_by_label(ep, "影响业务功能", active_cfg["business_functions"], "影响业务功能")

    # ==================== [18] 影响用户范围 ====================
    print("\n" + "=" * 55)
    print(f"[18] 影响用户范围 → {active_cfg['user_range'][0]}...")
    fill_dropdown_by_label(ep, "影响用户范围", active_cfg["user_range"][0], "影响用户范围")

    # ==================== [18.5] 变更成功标准 ====================
    print("\n" + "=" * 55)
    print("[18.5] 变更成功标准 → 升级验证成功...")
    fill_input_by_label(ep, "变更成功标准", "升级验证成功", "变更成功标准")

    # ==================== [18.55] 变更系统信息 ====================
    # 查找 upt_content.txt
    upt_content_file = None
    for start_dir in [os.getcwd(), SCRIPT_DIR]:
        cur = start_dir
        for _ in range(6):
            p = os.path.join(cur, "upt_content.txt")
            if os.path.exists(p):
                upt_content_file = p
                break
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        if upt_content_file:
            break
    
    if not upt_content_file:
        # 兜底查找绝对路径
        alt_path = "/Volumes/Macintosh HD_Data/WorkBuddy/版本发布/upt_content.txt"
        if os.path.exists(alt_path):
            upt_content_file = alt_path

    parsed_blocks = []
    if upt_content_file:
        print(f"\n  [UptContent] 找到变更内容文件: {upt_content_file}")
        try:
            with open(upt_content_file, "r", encoding="utf-8") as f:
                raw_text = f.read()
            raw_blocks = raw_text.strip().split("\n\n")
            for rb in raw_blocks:
                if not rb.strip():
                    continue
                lines = rb.strip().split("\n")
                block_data = {}
                start_idx = 0
                if ":" in lines[0] and not any(k in lines[0] for k in ["主系统", "CMDB", "变更文件", "cmdb变更部位", "变更部位", "变更方式", "备注"]):
                    start_idx = 1
                
                for line in lines[start_idx:]:
                    line = line.strip()
                    if not line:
                        continue
                    matched = False
                    for key in ["主系统/灾备", "CMDB维护组名称", "变更文件", "cmdb变更部位", "变更部位", "变更方式", "备注"]:
                        if line.startswith(key):
                            val = line[len(key):].strip()
                            block_data[key] = val
                            matched = True
                            break
                    if not matched:
                        parts = line.split(None, 1)
                        if len(parts) == 2:
                            block_data[parts[0].strip()] = parts[1].strip()
                if block_data:
                    parsed_blocks.append(block_data)
            print(f"  [UptContent] 成功解析了 {len(parsed_blocks)} 个变更数据块")
        except Exception as e:
            print(f"  [UptContent] 读取/解析失败: {e}")

    # 构建和填写动作
    if parsed_blocks:
        print("\n" + "=" * 55)
        print(f"[18.55] 变更系统信息 → 从 upt_content.txt 循环新增 {len(parsed_blocks)} 条系统信息...")
        for idx, block in enumerate(parsed_blocks, start=1):
            # 参考现有默认值
            default_cmdb = "集中交易系统"
            if active_cfg.get("system_info_actions") and len(active_cfg["system_info_actions"]) > 1:
                default_cmdb = active_cfg["system_info_actions"][1].get("value", default_cmdb)
            
            # 从 block 中读取字段值，缺省则按原逻辑/默认值
            main_sys_val = block.get("主系统/灾备", "主系统").strip()
            if main_sys_val not in ["主系统", "灾备"]:
                main_sys_val = "主系统"
            cmdb_val = block.get("CMDB维护组名称", default_cmdb)
            files_val = block.get("变更文件", "见制品信息")
            cmdb_part_val = block.get("cmdb变更部位", "不适用")
            part_val = block.get("变更部位", "见制品信息包名")
            remark_val = block.get("备注", "").strip()
            
            way_str = block.get("变更方式", "")
            way_values = [v.strip() for v in re.split(r'[\s,，]+', way_str) if v.strip()]
            if not way_values:
                way_values = ["新增", "替换"]
            
            block_actions = [
                {"type": "select", "label": "主系统/灾备", "value": main_sys_val},
                {"type": "select", "label": "CMDB维护组名称", "value": cmdb_val},
                {"type": "input", "label": "变更文件", "value": files_val},
                {"type": "select", "label": "cmdb变更部位", "value": cmdb_part_val},
                {"type": "input", "label": "变更部位", "value": part_val},
                {"type": "multi_select", "label": "变更方式", "values": way_values},
            ]
            if remark_val:
                block_actions.append({"type": "input", "label": "备注", "value": remark_val})
            
            print(f"\n  👉 开始填写第 {idx} 条系统信息 (CMDB={cmdb_val}, 变更方式={way_values}, 备注={remark_val or '无'})...")
            fill_section_add_popup(ep, "变更系统信息", block_actions, f"变更系统信息 (第{idx}条)")
            # 增加间隔以保障稳定
            time.sleep(2.0)
    else:
        # Fallback to static config if no blocks parsed
        sys_info_actions = active_cfg.get("system_info_actions")
        if sys_info_actions:
            print("\n" + "=" * 55)
            print("[18.55] 变更系统信息 (兜底静态逻辑) → 新增 → 填写主系统/CMDB/变更文件/变更部位/变更方式...")
            fill_section_add_popup(ep, "变更系统信息", sys_info_actions, "变更系统信息")

    # ==================== [18.56] 变更方案 ====================
    print("\n" + "=" * 55)
    print("[18.56] 变更方案 → 新增 → 填写任务/操作步骤/序列/角色...")

    # 清理已有的无效空行
    print("\n[清理] 检查并清理变更方案中的无效/空行...")
    for attempt in range(5):
        result = ep.evaluate("""() => {
            const tables = document.querySelectorAll('table');
            let targetTable = null;
            for (const tbl of tables) {
                const ths = Array.from(tbl.querySelectorAll('th')).map(th => (th.textContent || '').trim());
                if (ths.some(t => t.includes('操作步骤')) && ths.some(t => t.includes('处理人')) && ths.some(t => t.includes('角色'))) {
                    targetTable = tbl;
                    break;
                }
            }
            if (!targetTable) return {status: 'table_not_found'};
            
            const ths = Array.from(targetTable.querySelectorAll('th')).map(th => (th.textContent || '').trim());
            const handlerIdx = ths.findIndex(t => t.includes('处理人'));
            const stepIdx = ths.findIndex(t => t.includes('操作步骤'));
            if (handlerIdx === -1) return {status: 'handler_col_not_found'};
            
            const rows = Array.from(targetTable.querySelectorAll('tbody tr, tr.ant-table-row'));
            for (const row of rows) {
                const tds = row.querySelectorAll('td');
                if (tds.length <= handlerIdx) continue;
                
                const handlerText = (tds[handlerIdx].textContent || '').trim();
                const stepText = stepIdx !== -1 ? (tds[stepIdx].textContent || '').trim() : '';
                
                // 空行：处理人为空，或者操作步骤为空
                if (!handlerText || !stepText) {
                    const deleteBtn = Array.from(row.querySelectorAll('a, button, span')).find(el => {
                        const t = (el.textContent || '').trim();
                        return t === '删除' || t.includes('删除');
                    });
                    if (deleteBtn) {
                        deleteBtn.click();
                        return {status: 'clicked_delete'};
                    }
                }
            }
            return {status: 'clean'};
        }""")
        
        print(f"  清理尝试 {attempt + 1}: {result}")
        if result.get('status') == 'clean' or result.get('status') == 'table_not_found':
            break
        time.sleep(1.0)
            
        if result.get('status') == 'clicked_delete':
            time.sleep(1.0)
            # Debug DOM logging
            try:
                debug_els = ep.evaluate("""() => {
                    return Array.from(document.querySelectorAll('.ant-popover, .ant-popconfirm, .ant-modal, button, a'))
                        .map(el => ({
                            tag: el.tagName,
                            cls: el.className,
                            text: (el.textContent || '').trim().substring(0, 30),
                            w: el.getBoundingClientRect().width,
                            h: el.getBoundingClientRect().height
                        }))
                        .filter(e => e.w > 0 && e.h > 0);
                }""")
                print(f"      [DEBUG] Visible popover/modal/buttons: {debug_els}")
            except Exception as de:
                print(f"      [DEBUG] DOM query failed: {de}")
                
            confirm_res = ep.evaluate("""() => {
                const popovers = document.querySelectorAll('.ant-popover, .ant-popconfirm, .ant-modal, .ant-modal-wrap');
                for (const pop of popovers) {
                    const rect = pop.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        const confirmBtn = Array.from(pop.querySelectorAll('button, .ant-btn-primary, span')).find(el => {
                            const t = (el.textContent || '').trim();
                            return t === '确定' || t === '确 定' || t === '确认' || t === '确 认' || t === 'OK';
                        });
                        if (confirmBtn) {
                            confirmBtn.click();
                            return 'confirmed';
                        }
                    }
                }
                const btns = Array.from(document.querySelectorAll('button, .ant-btn-primary')).filter(b => {
                    const r = b.getBoundingClientRect();
                    return r.width > 0 && r.height > 0 && ((b.textContent || '').includes('确定') || (b.textContent || '').includes('确 认'));
                });
                if (btns.length > 0) {
                    btns[0].click();
                    return 'fallback_confirmed';
                }
                return 'no_confirm_btn';
            }""")
            print(f"    二次确认结果: {confirm_res}")
            time.sleep(1.5)

    if MODE == "cszx":
        # 第一条：主实施负责人
        change_plan_actions_1 = [
            {"type": "select", "label": "任务", "value": "变更任务"},
            {"type": "input", "label": "操作步骤", "value": "升级版本"},
            {"type": "input", "label": "序列", "value": "1"},
            {"type": "select", "label": "角色", "value": "主实施负责人"},
            {"type": "tree_select", "label": "处理人", "value": active_cfg["owner_name"], "search": active_cfg["owner"]},
        ]
        fill_section_add_popup(ep, "变更方案", change_plan_actions_1, "变更方案 (第1条：主实施负责人)")
        time.sleep(2.0)
        
        # 第二条：运维侧验证人
        change_plan_actions_2 = [
            {"type": "select", "label": "任务", "value": "复核"},
            {"type": "input", "label": "操作步骤", "value": "复核"},
            {"type": "input", "label": "序列", "value": "2"},
            {"type": "select", "label": "角色", "value": "运维侧验证"},
            {"type": "tree_select", "label": "处理人", "value": "叶飞", "search": "108502"},
        ]
        fill_section_add_popup(ep, "变更方案", change_plan_actions_2, "变更方案 (第2条：运维侧验证)")
        time.sleep(2.0)
    elif MODE == "jzjy":
        # 第一条
        change_plan_actions_1 = [
            {"type": "select", "label": "任务", "value": "变更任务"},
            {"type": "input", "label": "操作步骤", "value": "按变更方式操作"},
            {"type": "input", "label": "序列", "value": "1"},
            {"type": "select", "label": "角色", "value": "主实施负责人"},
            {"type": "tree_select", "label": "处理人", "value": "张永军", "search": "108728"},
        ]
        fill_section_add_popup(ep, "变更方案", change_plan_actions_1, "变更方案 (第1条：张永军)")
        time.sleep(2.0)
        
        # 第二条
        change_plan_actions_2 = [
            {"type": "select", "label": "任务", "value": "变更任务"},
            {"type": "input", "label": "操作步骤", "value": "按变更方式操作"},
            {"type": "input", "label": "序列", "value": "2"},
            {"type": "select", "label": "角色", "value": "主实施负责人"},
            {"type": "tree_select", "label": "处理人", "value": "张博闻", "search": "111483"},
        ]
        fill_section_add_popup(ep, "变更方案", change_plan_actions_2, "变更方案 (第2条：张博闻)")
        time.sleep(2.0)

        # 第三条
        change_plan_actions_3 = [
            {"type": "select", "label": "任务", "value": "复核"},
            {"type": "input", "label": "操作步骤", "value": "复核"},
            {"type": "input", "label": "序列", "value": "3"},
            {"type": "select", "label": "角色", "value": "运维侧验证"},
            {"type": "tree_select", "label": "处理人", "value": "宋倩", "search": "114322"},
        ]
        fill_section_add_popup(ep, "变更方案", change_plan_actions_3, "变更方案 (第3条：宋倩)")
        time.sleep(2.0)
    else:
        change_plan_actions = [
            {"type": "select", "label": "任务", "value": "变更任务"},
            {"type": "input", "label": "操作步骤", "value": "升级版本"},
            {"type": "input", "label": "序列", "value": "1"},
            {"type": "select", "label": "角色", "value": "主实施负责人"},
        ]
        fill_section_add_popup(ep, "变更方案", change_plan_actions, "变更方案")
        time.sleep(2.0)

    print("\n[INFO] 变更方案所有条目已填写完毕，等待 3 秒以确保页面稳定，防止与回退计划发生冲突...")
    time.sleep(3.0)

    # ==================== [18.6] 回退计划 ====================
    print("\n" + "=" * 55)
    print("[18.6] 回退计划 → 新增 → 填入回退策略/条件/步骤...")
    rollback_actions = [
        {"type": "select", "label": "回退策略", "value": "全部回退"},
        {"type": "input", "label": "回退条件", "value": "变更后系统出现异常，经开发、运维共同评估需要整体回退"},
        {"type": "input", "label": "回退步骤", "value": "回退至上一版本"},
    ]
    fill_section_add_popup(ep, "回退计划", rollback_actions, "回退计划")

    # ==================== [18.6] 应急计划 ====================
    print("\n" + "=" * 55)
    print("[18.6] 应急计划 → 新增 → 选择应急场景...")
    emergency_actions = [
        {"type": "select", "label": "异常场景", "value": "升级验证失败"},
    ]
    fill_section_add_popup(ep, "应急计划", emergency_actions, "应急计划")

    # ==================== [20] 保存并截图 ====================
    time.sleep(1)
    ep.keyboard.press("Escape"); time.sleep(0.5)

    saved = click_submit_btn_in_toolbar(ep, "保存")
    check_auth_status(ep, has_mid_auth_error)
    if not saved:
        raise Exception("Failed to click Save button (not found or click error)")
    time.sleep(1.5)

    ss_path = os.path.join(SCRIPT_DIR, "eoa117_verify.png")
    ep.evaluate("() => window.scrollTo(0,0)")
    time.sleep(0.5)
    ep.screenshot(path=ss_path, full_page=True)
    print(f"\n[验证截图] 完整表单状态: {ss_path}")

    # ==================== 最终报告与 Session 保存 ====================
    print("\n" + "=" * 55)
    print("🎉 EOA117 表单通用自动填报完成!")
    print("=" * 55)
    
    # 写入 JSON 执行报告
    report_data = {
        "upgrade_date": SAT_STR,
        "system": system_selection or "(未选定)",
        "screenshot": ss_path,
        "status": "completed",
        "mode_parsed": MODE
    }
    report_path = os.path.join(SCRIPT_DIR, "eoa117_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    print(f"  📄 JSON 报告已写入: {report_path}")

    try:
        ctx.storage_state(path=SESSION_FILE)
        print("\n  Session 已保存")
    except Exception as e:
        print(f"\n  Session 保存失败: {e}")

    if not headless:
        print("\n" + "=" * 55)
        print("  脚本执行完毕，浏览器将在 60 秒后关闭，请在此期间确认保存结果...")
        print("=" * 55)
        time.sleep(60)
    else:
        print("\n  脚本在无头模式下执行完毕，立即退出...")
    os._exit(0)


if __name__ == "__main__":
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            main()
            sys.exit(0)
        except KeyboardInterrupt:
            print("\n[中断] 用户中断脚本")
            sys.exit(1)
        except Exception as e:
            print(f"\n[⚠️ 异常自动修复] 第 {attempt+1} 次尝试失败: {e}")
            traceback.print_exc()
            
            # Clean up active browser and playwright to prevent background zombie processes
            if active_browser:
                try: active_browser.close()
                except: pass
            if active_playwright:
                try: active_playwright.stop()
                except: pass
                
            if os.path.exists(SESSION_FILE):
                try:
                    os.remove(SESSION_FILE)
                    print("  已删除会话文件以清除潜在失效缓存，下一次尝试将重新登录...")
                except Exception as ex:
                    print(f"  删除会话文件失败: {ex}")
            if attempt == max_attempts - 1:
                print("\n[❌ 错误] 已达到最大重试次数，填报失败。")
                sys.exit(1)
            time.sleep(3)
