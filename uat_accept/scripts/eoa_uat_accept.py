# -*- coding: utf-8 -*-
# EOA 草稿箱 UAT验收自动提交技能 (通用极速版)
# 可通过命令行参数配置过滤文种和接收处理人

import json, time, traceback, sys, os, io
import argparse
from playwright.sync_api import sync_playwright

# 终端输出编码强制 UTF-8
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


# 引入公共 SDK
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COMMON_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', 'common'))
if COMMON_DIR not in sys.path:
    sys.path.append(COMMON_DIR)

try:
    from workbuddy_vault import decrypt_secret
except ImportError:
    def decrypt_secret(s): return s


class EOADraftSubmitter:
    """EOA 草稿箱通用提交器类"""
    
    def __init__(self, config_path="config.json", doc_type="UAT测试申请(需求)", recipient="106881", headless=True, slow_mo=0):
        self.config_path = os.path.abspath(config_path)
        print(f"[初始化] 配置文件: {self.config_path}")
        print(f"[初始化] 过滤文种: {doc_type}")
        print(f"[初始化] 接收人员: {recipient}")
        print(f"[初始化] 无界面运行: {headless}, 慢动作毫秒: {slow_mo}")
        
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
            
        self.username = self.config["account"]["username"]
        raw_password = self.config["account"].get("PASSWORD", self.config["account"].get("password", ""))
        self.password = decrypt_secret(raw_password)
        self.viewport = self.config["browser"]["viewport"]
        self.home_url = self.config["platform"].get("home_url", "https://www.gtht.com.cn/home.html")
        
        self.doc_type = doc_type
        self.recipient = recipient
        self.headless = headless
        self.slow_mo = slow_mo
        
        # Session 复用路径与黑名单持久化路径
        self.session_file = os.path.join(SCRIPT_DIR, ".fintech_session.json")
        self.failed_file = os.path.join(SCRIPT_DIR, ".eoa_failed_drafts.json")

    def _load_failed_drafts(self):
        """加载持久化失败黑名单"""
        if os.path.exists(self.failed_file):
            try:
                with open(self.failed_file, "r", encoding="utf-8") as f:
                    return set(json.load(f))
            except Exception:
                pass
        return set()

    def _save_failed_drafts(self, failed_set):
        """保存失败黑名单到持久化文件"""
        try:
            with open(self.failed_file, "w", encoding="utf-8") as f:
                json.dump(list(failed_set), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def safe_wait(self, page, t=2000):
        try: page.wait_for_load_state("networkidle", timeout=t)
        except: time.sleep(1)

    def _ensure_login_v2(self, page):
        """直开首页，检测登录状态，未登录则自动登录"""
        print(f"[登录] 访问页面: {self.home_url}")
        page.goto(self.home_url, timeout=30000)
        
        # 等待登录框或者首页加载 (最多等待5秒，检测到即刻继续)
        start = time.time()
        state = {'needsLogin': False}
        while (time.time() - start) < 5:
            try:
                state = page.evaluate("""() => {
                    const hasPwd = document.querySelector('input[type="password"]');
                    const hasUser = [...document.querySelectorAll('input')]
                        .some(el => (el.placeholder||'').includes('工号') || (el.placeholder||'').includes('OA'));
                    const isLoginUrl = location.href.includes('login');
                    
                    if (hasPwd && hasUser) return {ready: true, needsLogin: true, reason: 'login_form'};
                    if (isLoginUrl) return {ready: true, needsLogin: true, reason: 'login_url'};
                    
                    const hasMenu = document.querySelector('.ant-menu, .layout, #app, .header, .home');
                    if (hasMenu) return {ready: true, needsLogin: false, reason: 'home_loaded'};
                    
                    return {ready: false};
                }""")
                if state.get('ready'):
                    break
            except Exception as e:
                pass
            time.sleep(0.1)
            
        print(f"[登录] 页面检测状态: {json.dumps(state, ensure_ascii=False)}")

        if not state.get('needsLogin'):
            print("[登录] Session有效，已进入系统")
            return

        # 需要登录
        print("[登录] 检测到登录页面，执行登录...")
        page.wait_for_selector('input[placeholder*="工号"]', timeout=5000)
        page.locator('input[placeholder*="工号"]').fill(self.username)
        page.locator('input[type="password"]').fill(self.password)
        
        clicked = False
        for bs in ['button:has-text("登 录")', 'button:has-text("登录")', 'button[type="submit"]']:
            if page.locator(bs).count() > 0:
                page.locator(bs).first.click(timeout=5000)
                clicked = True
                break
        if not clicked:
            page.keyboard.press("Enter")
            
        # 等待首页渲染加载跳转完成 (最多等待6秒，一旦进入首页即刻继续)
        start = time.time()
        while (time.time() - start) < 6:
            try:
                is_home = page.evaluate("""() => {
                    return !document.querySelector('input[type="password"]') && 
                           (!!document.querySelector('.ant-menu') || !!document.querySelector('.layout') || location.href.includes('home'));
                }""")
                if is_home:
                    break
            except Exception as e:
                pass
            time.sleep(0.1)
        print(f"[登录] 登录完成 → 当前URL: {page.url}")

    def navigate_to_drafts(self, page):
        """寻找并点击【我的草稿】按钮/标签"""
        print("\n--- 正在寻找并点击 【我的草稿】 ---")
        page.keyboard.press("Escape"); time.sleep(0.1)
        
        selectors = [
            'text="我的草稿"',
            '.ant-menu-item:has-text("我的草稿")',
            'a:has-text("我的草稿")',
            'span:has-text("我的草稿")',
            'div:has-text("我的草稿")',
            'li:has-text("我的草稿")'
        ]
        
        # 增加等待“我的草稿”元素渲染成功的重试循环 (最多等待8秒)
        start = time.time()
        clicked = False
        while (time.time() - start) < 8:
            for sel in selectors:
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0 and loc.is_visible():
                        loc.click(timeout=1000)
                        print(f"  ✓ 点击成功: {sel}")
                        clicked = True
                        break
                except:
                    pass
            if clicked:
                break
                
            # 尝试通过 JS 强点
            try:
                js_clicked = page.evaluate("""() => {
                    const els = Array.from(document.querySelectorAll('a, span, div, li, button'));
                    for (const el of els) {
                        if (el.offsetParent !== null && el.textContent.trim() === '我的草稿') {
                            el.scrollIntoView({block: 'center'});
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                if js_clicked:
                    print("  ✓ JS强点【我的草稿】成功")
                    clicked = True
                    break
            except:
                pass
                
            time.sleep(0.2)
            
        if not clicked:
            print("  ⚠ 未能找到【我的草稿】元素")
            return False
            
        start = time.time()
        while (time.time() - start) < 5:
            has_filter = page.evaluate("""() => {
                return [...document.querySelectorAll('label, span, div')].some(el => el.textContent.includes('文种'));
            }""")
            if has_filter:
                break
            time.sleep(0.1)
        return True

    def select_document_type(self, page):
        """选择文种过滤"""
        print(f"\n--- 正在选择文种: {self.doc_type} ---")
        page.keyboard.press("Escape"); time.sleep(0.1)
        
        click_r = page.evaluate("""(kw) => {
            const labels = Array.from(document.querySelectorAll('label, .fieldlabel, .ant-form-item-label label, span, div'))
                .filter(el => {
                    const text = el.textContent.trim();
                    // 确保是包含 "文种" 的叶子节点或者文字较短的标签节点，防止匹配到包含大量内容的大型容器
                    if (el.children.length > 2) return false;
                    return text === kw || (text.includes(kw) && text.length < 15);
                });
                
            for (const lbl of labels) {
                let parent = lbl.parentElement;
                for (let i = 0; i < 4; i++) {
                    if (!parent) break;
                    
                    const sel = parent.querySelector('.ant-select, .ant-select-selection, .ant-cascader-picker, .ant-select-selector');
                    if (sel && sel.offsetParent !== null) {
                        // 排除分页器相关的下拉框
                        if (sel.closest('.ant-pagination') || sel.classList.contains('ant-pagination-options-size-changer')) {
                            continue;
                        }
                        sel.click();
                        return {status: 'select_clicked', tag: sel.tagName, className: sel.className};
                    }
                    
                    const inp = parent.querySelector('input:not([type="hidden"])');
                    if (inp && inp.offsetParent !== null) {
                        const selectWrapper = inp.closest('.ant-select') || inp.closest('.ant-select-selection') || inp.closest('.ant-select-selector');
                        if (selectWrapper) {
                            if (selectWrapper.closest('.ant-pagination') || selectWrapper.classList.contains('ant-pagination-options-size-changer')) {
                                continue;
                            }
                            selectWrapper.click();
                            return {status: 'select_wrapper_clicked', tag: selectWrapper.tagName, className: selectWrapper.className};
                        }
                        
                        inp.focus();
                        inp.click();
                        return {status: 'text_input_focused', tag: inp.tagName, className: inp.className};
                    }
                    parent = parent.parentElement;
                }
            }
            
            return {status: 'not_found'};
        }""", "文种")
        
        print(f"  触发文种控件: {click_r}")
        
        if click_r.get('status') == 'text_input_focused':
            page.keyboard.press("Control+a")
            time.sleep(0.05)
            page.keyboard.type(self.doc_type)
            time.sleep(0.1)
            page.keyboard.press("Enter")
            print(f"  ✓ 文本框已输入 '{self.doc_type}' 并按回车过滤")
            time.sleep(1.5)
            return True
            
        elif click_r.get('status') in ('select_clicked', 'select_wrapper_clicked'):
            start = time.time()
            select_r = 'no_option_found'
            while (time.time() - start) < 3:
                select_r = page.evaluate("""(targetVal) => {
                    const query = '[role="option"], .ant-select-dropdown-menu-item, .ant-select-dropdown li, li[role="menuitem"], .ant-select-item-option, .ant-select-item, .ant-select-item-option-content';
                    const opts = document.querySelectorAll(query);
                    const visible = Array.from(opts).filter(o => o.offsetParent !== null);
                    
                    for(const o of visible){
                        const t = (o.textContent || '').trim();
                        if(t === targetVal || t.includes(targetVal)){
                            o.click();
                            return 'selected:' + t;
                        }
                    }
                    for(const o of opts){
                        const t = (o.textContent || '').trim();
                        if(t === targetVal || t.includes(targetVal)){
                            o.click();
                            return 'hidden_selected:' + t;
                        }
                    }
                    return 'no_option_found';
                }""", self.doc_type)
                if 'selected' in str(select_r):
                    break
                time.sleep(0.1)
                
            print(f"  下拉项选择结果: {select_r}")
            if 'selected' in str(select_r):
                time.sleep(0.8)
                return True

        direct_click = page.evaluate("""(targetVal) => {
            const els = Array.from(document.querySelectorAll('a, span, div, li'));
            for (const el of els) {
                if (el.offsetParent !== null && el.children.length === 0 && el.textContent.trim() === targetVal) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""", self.doc_type)
        if direct_click:
            print(f"  ✓ 直接点击过滤项 '{self.doc_type}' 成功")
            time.sleep(1.0)
            return True

        print(f"  ⚠ 未能通过筛选定位到文种: {self.doc_type}")
        return False

    def get_draft_titles_info(self, page):
        """获取草稿列表里的所有标题及基本信息"""
        return page.evaluate("""() => {
            const results = [];
            const rows = document.querySelectorAll('tr, .ant-table-row, .ant-list-item');
            let index = 0;
            
            for (const row of rows) {
                if (row.offsetParent === null) continue;
                if (row.querySelector('th')) continue;
                
                const links = Array.from(row.querySelectorAll('a, span.title, td a'));
                for (const link of links) {
                    if (link.offsetParent === null) continue;
                    const txt = (link.textContent || '').trim();
                    if (!txt) continue;
                    
                    if (['编辑', '删除', '修改', '查看', '详情', '提交', '撤销', '撤回'].includes(txt)) continue;
                    if (txt.length < 3) continue;
                    
                    results.push({
                        row_index: index,
                        text: txt,
                        tag: link.tagName
                    });
                    break;
                }
                index++;
            }
            
            if (results.length === 0) {
                const allLinks = document.querySelectorAll('.ant-list-item-meta-title a, .draft-list a, .list a');
                allLinks.forEach((link, idx) => {
                    if (link.offsetParent !== null) {
                        const txt = (link.textContent || '').trim();
                        if (txt && !['编辑', '删除', '修改'].includes(txt)) {
                            results.push({
                                row_index: idx,
                                text: txt,
                                tag: link.tagName
                            });
                        }
                    }
                });
            }
            
            return results;
        }""")

    def click_draft_title(self, page, target_text):
        """点击指定的草稿标题超链接"""
        print(f"  正在点击标题链接: '{target_text}'")
        success = page.evaluate("""(txt) => {
            const links = Array.from(document.querySelectorAll('a, span, td a, .ant-list-item-meta-title a'));
            for (const link of links) {
                if (link.offsetParent !== null && (link.textContent || '').trim() === txt) {
                    link.scrollIntoView({block: 'center'});
                    link.click();
                    return true;
                }
            }
            return false;
        }""", target_text)
        return success

    # ============================================================
    # 极速动态等待函数
    # ============================================================
    def wait_for_submit_button(self, page, timeout_ms=4000):
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            for frame in page.frames:
                try:
                    has_btn = frame.evaluate("""() => {
                        const btns = document.querySelectorAll('button, .ant-btn, .toolbar button, .bottom-bar button, .fixed-toolbar button, a.btn, input[type="button"], span');
                        return Array.from(btns).some(b => b.offsetParent !== null && (b.textContent||b.value||'').replace(/\\s+/g, '').includes('提交'));
                    }""")
                    if has_btn:
                        return True
                except:
                    pass
            time.sleep(0.05)
        return False

    def wait_for_modal_visible(self, page, timeout_ms=3000):
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            if self.is_modal_visible(page):
                return True
            time.sleep(0.05)
        return False

    def wait_for_modal_hidden(self, page, timeout_ms=4000):
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            if not self.is_modal_visible(page):
                return True
            time.sleep(0.05)
        return False

    def wait_for_search_results(self, page, timeout_ms=3000):
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            for frame in page.frames:
                try:
                    has_res = frame.evaluate("""(uid) => {
                        const opts = document.querySelectorAll(
                            '[role="option"], .ant-select-dropdown-menu-item, .ant-select-dropdown li, li[role="menuitem"], .ant-list-item, .ant-tree-treenode, tr, td, span, div'
                        );
                        return Array.from(opts).some(o => o.offsetParent !== null && o.textContent.includes(uid));
                    }""", self.recipient)
                    if has_res:
                        return True
                except:
                    pass
            time.sleep(0.05)
        return False

    # ============================================================
    # 详情页处理 & 审批人选择 (全面支持 iframe)
    # ============================================================
    def click_toolbar_button(self, page, btn_text="提交"):
        """点击工具栏或页面上的按钮（如：提交、保存）"""
        print(f"  正在寻找并点击按钮: '{btn_text}'")
        page.keyboard.press("Escape"); time.sleep(0.1)
        
        for i, frame in enumerate(page.frames):
            try:
                result = frame.evaluate("""(btnText) => {
                    const btns = document.querySelectorAll('button, .ant-btn, .toolbar button, .bottom-bar button, .fixed-toolbar button, a.btn, input[type="button"], span');
                    const visible = Array.from(btns).filter(b => b.offsetParent !== null);
                    for(const b of visible){
                        const t = (b.textContent||b.value||'').replace(/\\s+/g, '');
                        if(t === btnText || t.includes(btnText)){
                            b.scrollIntoView({block: 'center'});
                            b.click();
                            return {ok: true, text: t, tag: b.tagName};
                        }
                    }
                    return {ok: false, count: visible.length};
                }""", btn_text)
                
                if result.get('ok'):
                    frame_desc = "主页面" if i == 0 else f"Frame {i} ({frame.name or frame.url[:40]})"
                    print(f"  ✓ 在 {frame_desc} 中成功点击了 '{btn_text}' 按钮: {result}")
                    return True
            except:
                pass
                
        print(f"  ❌ 未能在详情页（包括所有 iframes）中找到/点击 '{btn_text}' 按钮")
        return False

    def is_modal_visible(self, page):
        """判断当前页面上是否弹出了对话框/模态窗口"""
        for frame in page.frames:
            try:
                visible = frame.evaluate("""() => {
                    const modals = document.querySelectorAll('.ant-modal-wrap, .ant-modal, [role="dialog"], .ant-drawer');
                    for (const m of modals) {
                        if (m.offsetParent !== null) return true;
                    }
                    return false;
                }""")
                if visible:
                    return True
            except:
                pass
        return False

    def fill_approver_search_box(self, page):
        """定位输入姓名、工号、OA账户搜索输入框并输入用户工号"""
        print(f"  正在填写审批人搜索框: {self.recipient}")
        
        for i, frame in enumerate(page.frames):
            try:
                result = frame.evaluate("""(uid) => {
                    const placeholders = ['输入姓名、工号、OA账户搜索', '输入姓名、工号、OA账户', '姓名、工号、OA账户', '搜索', '工号', '姓名'];
                    
                    for (const ph of placeholders) {
                        const inputs = document.querySelectorAll(`input[placeholder*="${ph}"]`);
                        for (const inp of inputs) {
                            if (inp && inp.offsetParent !== null) {
                                inp.focus();
                                inp.value = '';
                                
                                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                                nativeSetter.call(inp, uid);
                                inp.dispatchEvent(new Event('input', {bubbles: true}));
                                inp.dispatchEvent(new Event('change', {bubbles: true}));
                                return {ok: true, method: 'placeholder', match: ph};
                            }
                        }
                    }
                    
                    const labels = Array.from(document.querySelectorAll('label, span, div'))
                        .filter(el => el.textContent.includes('搜索') || el.textContent.includes('账户') || el.textContent.includes('工号'));
                        
                    for (const lbl of labels) {
                        let parent = lbl.parentElement;
                        for (let i = 0; i < 3; i++) {
                            if (!parent) break;
                            const inp = parent.querySelector('input:not([type="hidden"])');
                            if (inp && inp.offsetParent !== null) {
                                inp.focus();
                                inp.value = '';
                                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                                nativeSetter.call(inp, uid);
                                inp.dispatchEvent(new Event('input', {bubbles: true}));
                                inp.dispatchEvent(new Event('change', {bubbles: true}));
                                return {ok: true, method: 'label_nearby', label: lbl.textContent.trim()};
                            }
                            parent = parent.parentElement;
                        }
                    }
                    
                    const modals = document.querySelectorAll('.ant-modal-wrap, .ant-modal, [role="dialog"], .ant-drawer');
                    for (const m of modals) {
                        if (m.offsetParent !== null) {
                            const inp = m.querySelector('input:not([type="hidden"])');
                            if (inp) {
                                inp.focus();
                                inp.value = '';
                                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                                nativeSetter.call(inp, uid);
                                inp.dispatchEvent(new Event('input', {bubbles: true}));
                                inp.dispatchEvent(new Event('change', {bubbles: true}));
                                return {ok: true, method: 'modal_fallback'};
                            }
                        }
                    }
                    
                    return {ok: false};
                }""", self.recipient)
                
                if result.get('ok'):
                    frame_desc = "主页面" if i == 0 else f"Frame {i}"
                    print(f"  ✓ 在 {frame_desc} 中成功定位并输入: {result}")
                    time.sleep(0.2)
                    page.keyboard.press("Backspace")
                    time.sleep(0.05)
                    page.keyboard.type(self.recipient[-1])
                    self.wait_for_search_results(page, 3000)
                    return True
            except:
                pass
                
        return False

    def select_search_result(self, page):
        """在联想搜索列表中选择匹配的用户选项"""
        print(f"  正在选中包含 '{self.recipient}' 的搜索结果...")
        
        for i, frame in enumerate(page.frames):
            try:
                result = frame.evaluate("""(uid) => {
                    const opts = document.querySelectorAll(
                        '[role="option"], .ant-select-dropdown-menu-item, .ant-select-dropdown li, li[role="menuitem"], .ant-list-item, .ant-tree-treenode, tr, td'
                    );
                    const visible = Array.from(opts).filter(o => o.offsetParent !== null);
                    
                    for (const o of visible) {
                        const t = (o.textContent || '').trim();
                        if (t.includes(uid)) {
                            const cb = o.querySelector('input[type="checkbox"], input[type="radio"], .ant-checkbox, .ant-radio');
                            if (cb) {
                                cb.click();
                                return {ok: true, type: 'checkbox_radio', text: t};
                            }
                            o.click();
                            return {ok: true, type: 'direct_item_click', text: t};
                        }
                    }
                    
                    const leafElements = document.querySelectorAll('.ant-modal-body span, .ant-modal-body div, .ant-drawer-body span, .ant-drawer-body div');
                    for (const el of leafElements) {
                        if (el.offsetParent !== null && el.children.length === 0) {
                            const t = (el.textContent || '').trim();
                            if (t.includes(uid)) {
                                el.click();
                                return {ok: true, type: 'leaf_element_click', text: t};
                            }
                        }
                    }
                    
                    return {ok: false};
                }""", self.recipient)
                
                if result.get('ok'):
                    frame_desc = "主页面" if i == 0 else f"Frame {i}"
                    print(f"  ✓ 在 {frame_desc} 中成功选中结果: {result}")
                    return True
            except:
                pass
                
        return False

    def click_modal_submit_button(self, page, btn_text="提交"):
        """点击弹窗底部的确认提交/确定按钮"""
        print(f"  正在点击弹窗确认按钮: '{btn_text}'")
        
        for i, frame in enumerate(page.frames):
            try:
                result = frame.evaluate("""(btnText) => {
                    const modals = document.querySelectorAll('.ant-modal-wrap, .ant-modal, [role="dialog"], .ant-drawer');
                    let activeModal = null;
                    for (const m of modals) {
                        if (m.offsetParent !== null) {
                            activeModal = m;
                            break;
                        }
                    }
                    
                    const container = activeModal || document;
                    const btns = container.querySelectorAll('button, .ant-btn, a.btn, input[type="button"]');
                    const visible = Array.from(btns).filter(b => b.offsetParent !== null);
                    
                    for (const b of visible) {
                        const t = (b.textContent||b.value||'').replace(/\\s+/g, '');
                        if (t === btnText) {
                            b.scrollIntoView({block: 'center'});
                            b.click();
                            return {ok: true, text: t, match: 'exact'};
                        }
                    }
                    
                    for (const b of visible) {
                        const t = (b.textContent||b.value||'').replace(/\\s+/g, '');
                        if (t.includes(btnText)) {
                            b.scrollIntoView({block: 'center'});
                            b.click();
                            return {ok: true, text: t, match: 'partial'};
                        }
                    }
                    
                    if (activeModal) {
                        const primaryBtn = activeModal.querySelector('.ant-modal-footer .ant-btn-primary, .ant-drawer-actions .ant-btn-primary');
                        if (primaryBtn && primaryBtn.offsetParent !== null) {
                            primaryBtn.click();
                            return {ok: true, text: primaryBtn.textContent.trim(), match: 'primary_fallback'};
                        }
                    }
                    
                    return {ok: false, count: visible.length};
                }""", btn_text)
                
                if result.get('ok'):
                    frame_desc = "主页面" if i == 0 else f"Frame {i}"
                    print(f"  ✓ 在 {frame_desc} 中成功点击弹窗按钮: {result}")
                    return True
            except:
                pass
                
        return False

    def process_draft_detail(self, page):
        """处理草稿详情页的点击提交及选人表单提交"""
        print("  等待详情页渲染组件...")
        if not self.wait_for_submit_button(page, 4000):
             print("  ⚠ 详情页加载较慢或未检测到'提交'按钮，尝试强行继续...")
        
        # 1. 点击详情页的 "提交" 按钮
        if not self.click_toolbar_button(page, "提交"):
            print("  ❌ 未能在详情页找到/点击 '提交' 按钮")
            return False
            
        print("  等待选人弹窗出现...")
        self.wait_for_modal_visible(page, 3000)
        
        if not self.is_modal_visible(page):
            print("  ℹ 提交后未发现选人弹窗，可能已直接提交成功")
            return True
            
        # 2. 在搜索框内填写工号/姓名
        if not self.fill_approver_search_box(page):
            print("  ❌ 未能定位或填写处理人搜索框")
            return False
            
        # 3. 选中搜索出的行/选项
        if not self.select_search_result(page):
            print("  ❌ 未能在联想列表中选中工号/账号")
            return False
            
        # 4. 点击弹窗上的确认提交/确定按钮
        success = self.click_modal_submit_button(page, "提交")
        if not success:
            success = self.click_modal_submit_button(page, "确定")
            
        if success:
            print("  ✓ 弹窗提交按钮已点击，正在等待弹窗关闭...")
            self.wait_for_modal_hidden(page, 5000)
            time.sleep(0.5)
            return True
        else:
            print("  ❌ 点击确认提交按钮失败")
            return False

    def run(self):
        """运行草稿箱自动提交全流程"""
        print("\n" + "=" * 55)
        print("EOA 通用草稿自动提交技能运行开始")
        print("=" * 55)
        
        p = sync_playwright().start()
        browser = p.chromium.launch(
            channel="chrome",
            headless=self.headless,
            slow_mo=self.slow_mo
        )
        
        if os.path.exists(self.session_file):
            print(f"[Session] 发现已保存的登录态，进行复用...")
            ctx = browser.new_context(viewport=self.viewport, locale="zh-CN", storage_state=self.session_file)
        else:
            ctx = browser.new_context(viewport=self.viewport, locale="zh-CN")
            
        pg = ctx.new_page()

        try:
            # 1. 登录
            self._ensure_login_v2(pg)
            
            # 2. 导航到我的草稿
            if not self.navigate_to_drafts(pg):
                print("  ❌ 无法进入【我的草稿】标签，程序终止。")
                return
                
            # 3. 筛选过滤文种
            if not self.select_document_type(pg):
                print("  ❌ 筛选文种失败，程序终止。")
                return
                
            # 4. 循环迭代提交草稿
            processed_count = 0
            failed_titles = self._load_failed_drafts()
            if failed_titles:
                print(f"  ℹ️ 已加载持久化失败跳过黑名单 ({len(failed_titles)} 条)")
            
            while True:
                drafts = self.get_draft_titles_info(pg)
                active_drafts = [d for d in drafts if d['text'] not in failed_titles]
                
                if len(active_drafts) == 0:
                    print(f"\n  🎉 所有匹配的草稿已处理完毕。")
                    print(f"     ✅ 成功处理/提交: {processed_count} 个")
                    print(f"     ⚠️ 失败/跳过: {len(failed_titles)} 个")
                    break
                    
                target_draft = active_drafts[0]
                title_text = target_draft['text']
                
                print(f"\n[第 {processed_count+1} 项] 开始提交草稿: '{title_text}'")
                
                success = False
                try:
                    new_page = None
                    try:
                        with pg.expect_popup(timeout=2500) as popup_info:
                            self.click_draft_title(pg, title_text)
                        new_page = popup_info.value
                        new_page.wait_for_load_state("load")
                        
                        success = self.process_draft_detail(new_page)
                        try: new_page.close()
                        except: pass
                        
                    except Exception as popup_err:
                        # 单标签内页跳转逻辑兼容
                        self.click_draft_title(pg, title_text)
                        time.sleep(0.5)
                        self.safe_wait(pg, 2000)
                        
                        success = self.process_draft_detail(pg)
                        
                        # 重回草稿重新过滤
                        self.navigate_to_drafts(pg)
                        self.select_document_type(pg)
                        
                except Exception as e:
                    print(f"  ❌ 提交过程遭遇异常: {e}")
                    traceback.print_exc()
                    
                if success:
                    processed_count += 1
                    print(f"  ✅ '{title_text}' 提交成功")
                    # 重新刷新当前列表，防止数据错乱
                    print("  重新加载并刷新草稿列表...")
                    self.navigate_to_drafts(pg)
                    self.select_document_type(pg)
                else:
                    failed_titles.add(title_text)
                    self._save_failed_drafts(failed_titles)
                    print(f"  ⚠️ '{title_text}' 提交失败/跳过 (已写入持久化黑名单)")
                    
                time.sleep(0.5)

            # 保存 session 并退出
            try:
                ctx.storage_state(path=self.session_file)
                print("\n[Session] 登录 Session 已成功保存更新")
            except Exception as e:
                print(f"\n[Session] Session 保存失败: {e}")
                
        finally:
            print("\n" + "=" * 55)
            print("  自动化脚本执行完毕，正在清理并退出。")
            print("=" * 55)
            try: browser.close()
            except: pass
            p.stop()


if __name__ == "__main__":
    # 解析命令行参数
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_config = os.path.join(script_dir, "config.json")
    
    parser = argparse.ArgumentParser(description="EOA 草稿箱通用自动提交技能")
    parser.add_argument("--doc-type", default="UAT测试申请(需求)", help="过滤的文种名称 (默认: UAT测试申请(需求))")
    parser.add_argument("--recipient", default="106881", help="接收审批人的工号/姓名/OA账号 (默认: 106881)")
    parser.add_argument("--config", default=default_config, help=f"配置文件路径 (默认: {default_config})")
    parser.add_argument("--no-headless", action="store_true", help="是否显示浏览器运行界面")
    parser.add_argument("--slow-mo", type=int, default=0, help="慢动作时间延时毫秒数 (默认: 0)")
    
    args = parser.parse_args()
    headless_run = not args.no_headless
    
    submitter = EOADraftSubmitter(
        config_path=args.config,
        doc_type=args.doc_type,
        recipient=args.recipient,
        headless=headless_run,
        slow_mo=args.slow_mo
    )
    
    try:
        submitter.run()
    except KeyboardInterrupt:
        print("\n[中断] 用户手动中止脚本执行")
    except Exception as e:
        print(f"\n[ERROR] 全局异常: {e}")
        traceback.print_exc()
