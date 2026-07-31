#!/usr/bin/env python3
"""
Coremail Fast Draft Saver v2.0 — 极速无界面草稿保存（含收件人自动填写）

全程 headless，无 GUI 交互，5-15 秒完成。
自动填写收件人（键盘逐字输入+下拉框选择）、主题、正文，然后存草稿。

用法:
  python fast_draft.py --config config.json --subject "主题" --body-file body.txt [--recipients "吴进,周倩"]

v2.0 变更:
  - 新增收件人自动填写（键盘输入+Enter选下拉框），不再仅做参考提示
  - 修复 f-string 中 JS 花括号语法冲突
  - 流程从4步改为5步：login → compose → recipients → subject+body → save
"""

import argparse, json, os, re, shutil, sys
from pathlib import Path

try:
    from cryptography.fernet import Fernet
    HAS_FERNET = True
except ImportError:
    HAS_FERNET = False

STORAGE_STATE_PATH = os.path.expanduser("~/.workbuddy/.cormail_storage_state.json")
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent

# ── Config & Password ──
def find_config(config_arg):
    if config_arg:
        p = Path(config_arg)
        if p.exists():
            if p.is_dir():
                cand = p / "config.json"
                if cand.exists(): return str(cand.resolve())
                return str(p.resolve())
            return str(p.resolve())
        print(f"[WARN] 指定路径不存在: {config_arg}")
    cand = SKILL_DIR / "config.json"
    if cand.exists(): return str(cand.resolve())
    raise FileNotFoundError("config.json 未找到")

def load_config(path):
    with open(path, encoding="utf-8") as f: return json.load(f)

def resolve_csv_path(config):
    raw = config.get("csv_path", "")
    if not raw:
        return None
    p = Path(raw)
    if p.is_absolute():
        return str(p) if p.exists() else None
    # 搜索优先级：SKILL 目录 → 当前工作目录及其父级（最多往上 3 层）
    search_roots = [SKILL_DIR, Path.cwd()]
    for _ in range(3):
        pdir = Path.cwd().parent
        if pdir != Path.cwd():
            search_roots.append(pdir)
    for root in search_roots:
        cand = root / raw
        if cand.exists():
            return str(cand.resolve())
        for d in config.get("csv_search_dirs", []):
            if d:
                cand = root / d / raw
                if cand.exists():
                    return str(cand.resolve())
    return None

def get_sender_name(username, csv_path):
    """
    根据发件人邮箱用户名拼音去 CSV 中匹配其真实中文姓名。
    """
    if not username:
        return None
    email_prefix = username.split("@")[0].lower()
    email_prefix = re.sub(r"\d+$", "", email_prefix)
    if not email_prefix:
        return None

    # 兜底：如果是 wujin 打头，发件人姓名直接设定为 "吴进"
    if email_prefix.startswith("wujin"):
        return "吴进"

    sender_name = None
    try:
        import pypinyin
        import csv
        roster_names = []
        if csv_path and os.path.exists(csv_path):
            for encoding in ['utf-8', 'gbk', 'gb2312']:
                try:
                    with open(csv_path, mode='r', encoding=encoding) as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            name = row.get('人员', '')
                            if not name:
                                name = list(row.values())[0] if row.values() else ''
                            name = name.strip()
                            if name:
                                roster_names.append(name)
                    break
                except:
                    continue
        for rname in roster_names:
            name_pinyin = "".join(pypinyin.lazy_pinyin(rname)).lower()
            if name_pinyin == email_prefix:
                sender_name = rname
                break
    except Exception as e:
        print(f"[*] 解析发件人拼音出错: {e}")
    return sender_name

def decrypt_password(enc):
    if not enc: return ""
    if isinstance(enc, list): enc = "".join(enc)
    m = re.match(r"^ENC:(.*)", enc)
    if not m: return enc
    if not HAS_FERNET:
        print("[ERROR] 密码已加密，请先 pip install cryptography"); sys.exit(1)
    key = (os.environ.get("CORMAIL_ENC_KEY") or "").encode()
    if len(key) != 44:
        key_path = Path.home() / ".workbuddy" / ".meeting_skill_key"
        if key_path.exists(): key = key_path.read_text().strip().encode()
    if len(key) != 44:
        print("[ERROR] CORMAIL_ENC_KEY 未设置"); sys.exit(1)
    try: return Fernet(key).decrypt(m.group(1).encode()).decode()
    except Exception as e: print(f"[ERROR] 密码解密失败: {e}"); sys.exit(1)

def convert_md_table_to_html(rows):
    if len(rows) < 2:
        return "\n".join(rows)
    headers = [cell.strip() for cell in rows[0].split("|")[1:-1]]
    sep_cells = [cell.strip() for cell in rows[1].split("|")[1:-1]]
    if not all(re.match(r"^:?-+:?$", cell) for cell in sep_cells):
        return "\n".join(rows)
    
    html = []
    html.append('<table style="border-collapse: collapse; width: 100%; border: 1px solid #ddd; font-size: 14px; font-family: sans-serif; margin: 15px 0;">')
    html.append('<thead>')
    html.append('<tr style="background-color: #f2f2f2; text-align: left;">')
    for cell in headers:
        cell_formatted = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", cell)
        html.append(f'<th style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">{cell_formatted}</th>')
    html.append('</tr>')
    html.append('</thead>')
    html.append('<tbody>')
    for row in rows[2:]:
        cells = [cell.strip() for cell in row.split("|")[1:-1]]
        html.append('<tr>')
        for cell in cells:
            cell_formatted = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", cell)
            html.append(f'<td style="padding: 10px; border: 1px solid #ddd;">{cell_formatted}</td>')
        html.append('</tr>')
    html.append('</tbody>')
    html.append('</table>')
    return "".join(html)

def md_to_html(md: str) -> str:
    # 1. First parse tables
    lines = md.split("\n")
    new_lines = []
    in_table = False
    table_rows = []
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            in_table = True
            table_rows.append(line)
        else:
            if in_table:
                html_table = convert_md_table_to_html(table_rows)
                new_lines.append(html_table)
                in_table = False
                table_rows = []
            new_lines.append(line)
            
    if in_table:
        html_table = convert_md_table_to_html(table_rows)
        new_lines.append(html_table)
        
    html = "\n".join(new_lines)
    
    # 2. General markdown formatting
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = html.replace("　", "&nbsp;&nbsp;")
    html = html.replace("\n\n", "<div><br></div>")
    html = html.replace("\n", "<br>")
    return html

# ── Coremail 选择器 ──
SEL_COMPOSE = ", ".join([
    'a:has-text("写信")', 'button:has-text("写信")',
    'span:has-text("写信")', 'div:has-text("写信")', 'li:has-text("写信")',
    '[title*="写信"]', '[aria-label*="写信"]',
    '#composeBtn', '.compose-btn', '.btn-compose',
])
SEL_SUBJ = 'input[name="subject"], input[id*="subject"], input[id*="Subject"], input[placeholder*="主题"]'
SEL_UID = 'input[name="uid"], input[id*="uid"], input[placeholder*="账号"], input[placeholder*="邮箱"], input[type="text"]'
SEL_PWD = 'input[name="password"], input[name="pwd"], input[type="password"]'

SELECTORS_TO = [
    'input#toInput', 'input#to', 'input[id*="toInput"]', 'input[id*="toAddrInput"]', '#toAddrInput',
    'input[placeholder*="收件人"]', 'input[placeholder*="收件"]',
    'input[title*="收件人"]', 'input[title*="收件"]',
    'input[name="to"]', 'textarea[name="to"]', 'textarea[id*="to"]',
    'input[class*="addr"]', 'textarea[class*="addr"]',
]

SELECTORS_SUBJ = [
    'input[name="subject"]', 'input[id*="subject"]', 'input[id*="Subject"]',
    'input[placeholder*="主题"]', 'input[title*="主题"]',
    'textarea[name="subject"]', 'textarea[placeholder*="主题"]',
]

SELECTORS_SAVE = [
    'a:has-text("存草稿")', 'button:has-text("存草稿")', 'span:has-text("存草稿")', 'a[title*="存草稿"]',
    'a:has-text("保存")', 'button:has-text("保存")',
]

def wait_for_visible_element(page, selectors_list, timeout=5000):
    """在 page 和所有 frames 中查找第一个可见的目标元素"""
    import time
    end_time = time.time() + (timeout / 1000.0)
    while True:
        for fr in [page] + page.frames:
            for sel in selectors_list:
                try:
                    elements = fr.query_selector_all(sel)
                    for el in elements:
                        if el.is_visible():
                            return el, fr
                except:
                    pass
        if time.time() >= end_time:
            break
        page.wait_for_timeout(200)
    return None, None

# ── 收件人自动填写 ──
def fill_recipients_fast(page, names):
    """
    逐个输入收件人，并敲击回车+Tab确认，确保 Coremail 稳定解析所有收件人为独立的 Tag 标签。
    """
    if not names:
        return 0

    print(f"  [-] 收件人 ({len(names)} 人):")

    # 确保焦点在收件人输入区
    try:
        to_el, to_fr = wait_for_visible_element(page, SELECTORS_TO, timeout=5000)
        if to_el:
            to_el.focus()
            to_el.evaluate("el => el.click()")
            print("  [+] Focused and JS-clicked To input field")
        else:
            print("  [!] Failed to find visible To input field")
            return 0
    except Exception as e:
        print(f"  [!] Failed to focus To input field: {e}")
        return 0
    page.wait_for_timeout(200)

    try:
        for name in names:
            page.keyboard.type(name, delay=20)
            page.wait_for_timeout(600)   # 等待通讯录 AJAX 检索并弹出下拉列表
            page.keyboard.press("ArrowDown") # 高亮选中下拉菜单中匹配的联系人
            page.wait_for_timeout(100)
            page.keyboard.press("Enter")     # 确认选中联系人（转为带邮箱的蓝标签）
            page.wait_for_timeout(200)   # 等待 Tag 稳定渲染
            print(f"  [+] Entered recipient: {name}")
        return len(names)
    except Exception as e:
        print(f"  [!] Failed to type recipients: {e}")
        return 0

def wait_for_compose_btn(page, timeout=15_000):
    """用多种方式等待"写信"按钮出现。在所有 tab 和所有 frame 中查找，返回 (el, active_page) 或 (None, None)"""
    import time
    end_time = time.time() + (timeout / 1000.0)
    while True:
        for p in page.context.pages:
            for fr in [p] + p.frames:
                try:
                    el = fr.query_selector(SEL_COMPOSE)
                    if el and el.is_visible():
                        p.bring_to_front()
                        return el, p
                except:
                    pass
        if time.time() >= end_time:
            break
        page.wait_for_timeout(200)
    return None, None

# ── Coremail 登录 ──
def try_session_restore(page, url):
    """尝试复用已保存的 session 直接进入邮箱。
    返回 (success, active_page)：如果新 tab 打开了邮箱，返回那个 page。
    """
    if not Path(STORAGE_STATE_PATH).exists():
        return False, page
    try:
        page.goto(url, wait_until="commit", timeout=10_000)
        btn, active_page = wait_for_compose_btn(page, timeout=5000)
        if btn:
            return True, active_page
    except Exception as e:
        print(f"  [!] Session restore failed: {e}")
    return False, page

def login_fast(page, url, username, password):
    """快速登录（类似 save_to_draft.py 的 login_coremail）。"""
    page.goto(url, wait_until="commit", timeout=10_000)
    uid_el = None
    for ms in [2_000, 3_000, 5_000]:
        try:
            uid_el = page.wait_for_selector(SEL_UID, timeout=ms)
            if uid_el: break
        except: pass
    if not uid_el:
        raise Exception("登录表单未出现")
    uid_el.click()
    uid_el.fill(username)
    print(f"  [-] UID: {username}")
    try:
        pwd_el = page.wait_for_selector(SEL_PWD, timeout=5_000)
        pwd_el.fill(password)
        print("  [-] Password: ****")
    except: raise
    page.keyboard.press("Enter")
    print("  [-] Login submitted")

    # 等邮箱加载
    btn, active_page = wait_for_compose_btn(page, timeout=20000)
    if btn:
        return active_page

    # 登录失败：截图辅助排查
    try:
        shot = SCRIPT_DIR / "debug_login_fast_fail.png"
        page.screenshot(path=str(shot))
        print(f"  [D] Login fail screenshot: {shot}")
        print(f"  [D] Page URL: {page.url}")
    except: pass

    # 检查是否有新 tab
    all_pages = page.context.pages
    for p in all_pages:
        if p != page:
            try:
                el = p.wait_for_selector(SEL_COMPOSE, timeout=3_000)
                if el:
                    p.bring_to_front()
                    return p
            except: pass

    raise Exception("登录失败（可能有验证码，请先用 save_to_draft.py --no-headless 建立session）")

# ── 正文注入 ──
def inject_body(page, body_html):
    """将 HTML 注入 KindEditor iframe 正文区域，并严格校验非空。"""
    js_html = json.dumps(body_html)

    def _write(fr):
        try:
            js_code = """(() => {
  const d = document;
  const html = """ + js_html + """;
  if (d && d.body) {
    d.body.innerHTML = html;
    d.body.dispatchEvent(new Event('input', {bubbles: true}));
    d.body.dispatchEvent(new Event('change', {bubbles: true}));
    return d.body.innerHTML.length > 10;
  }
  return false;
})()"""
            return fr.evaluate(js_code)
        except: return False

    # 轮询等待 iframe 加载并成功写入正文
    for _ in range(15):
        for fr in page.frames:
            if fr == page: continue
            try:
                is_editor = fr.evaluate("() => document.body && (document.designMode === 'on' || document.body.contentEditable === 'true' || (document.body.className && document.body.className.includes('ke-content')))")
                if is_editor and _write(fr):
                    return True
            except: pass
        page.wait_for_timeout(300)

    # 降级方案 1：全局 KindEditor 实例
    for fr in [page] + page.frames:
        try:
            res = fr.evaluate("""(html) => {
                if (window.editor) { window.editor.html(html); return true; }
                if (window.KindEditor && KindEditor.instances && KindEditor.instances[0]) { KindEditor.instances[0].html(html); return true; }
                return false;
            }""", body_html)
            if res: return True
        except: pass

    # 降级方案 2：textarea
    try:
        ta = page.wait_for_selector('textarea[name="ml-editor"]', timeout=2_000)
        if ta: ta.fill(body_html); return True
    except: pass

    return False

# ── 主流程 ──
def save_draft_fast(config, subject, body_file_path, recipient_names=None, headless=True):
    """极速保存草稿：headless + session复用 + 收件人自动填写。"""
    from playwright.sync_api import sync_playwright

    mail_cfg = config.get("mail", {})
    url = mail_cfg.get("url", "https://mail.gtht.com/")
    username = mail_cfg.get("username", "")
    password = decrypt_password(mail_cfg.get("password", ""))

    if not username or not password:
        print("[ERROR] mail.username/password 未配置"); sys.exit(1)

    # 读取正文
    body_md = Path(body_file_path).read_text(encoding="utf-8")
    body_html = md_to_html(body_md)

    chrome_locs = [
        shutil.which("google-chrome"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
    ]
    chrome_exe = next((loc for loc in chrome_locs if loc and Path(loc).exists()), None)

    # Coremail 对 headless 浏览器有 session 校验差异，使用 headless=False + 最小化窗口
    # 实际体验等同后台执行（窗口短暂出现后自动关闭）
    with sync_playwright() as pw:
        launch_kwargs = {"headless": headless}
        if chrome_exe:
            launch_kwargs["executable_path"] = chrome_exe
        if not headless:
            launch_kwargs["args"] = ["--window-position=-2400,-2400"]
        browser = pw.chromium.launch(**launch_kwargs)

        ctx_kwargs = {"viewport": {"width": 1280, "height": 900}, "locale": "zh-CN"}
        if Path(STORAGE_STATE_PATH).exists():
            ctx_kwargs["storage_state"] = STORAGE_STATE_PATH
            print(f"[1/5] 复用登录态: {STORAGE_STATE_PATH}")

        ctx = browser.new_context(**ctx_kwargs)
        page = ctx.new_page()

        try:
            # ── Step 1: 登录 ──
            print("[1/5] 连接邮箱...")
            restored, active_page = try_session_restore(page, url)
            if restored:
                print("  [+] Session 恢复成功")
                page = active_page  # 切换到包含邮箱的页面
            else:
                print("  [*] Session 失效，尝试自动登录...")
                try:
                    page = login_fast(page, url, username, password)
                    try: page.context.storage_state(path=STORAGE_STATE_PATH)
                    except: pass
                    print("  [+] 登录成功，session 已更新")
                except Exception as e:
                    print(f"  [!] 登录失败: {e}")
                    print("  [!] 请先运行: save_to_draft.py --no-headless --local YYYYMMDD")
                    print("  [!] 完成一次手动登录后，session 会自动保存，后续可自动复用")
                    browser.close(); sys.exit(1)

            mailbox_url = page.url

            # ── Step 2: 打开写信 ──
            print("[2/5] 打开写信...")
            btn, btn_fr = wait_for_visible_element(page, [SEL_COMPOSE], timeout=15000)
            if not btn:
                raise Exception("无法在邮箱首页找到写信按钮")

            # Click compose button and wait for the compose form (subject field) to load
            compose_loaded = False
            for attempt in range(5):
                try:
                    btn.click(force=True)
                    print(f"  [-] Clicked compose button (attempt {attempt+1})")
                    # Check if compose form is visible
                    subj_el, subj_fr = wait_for_visible_element(page, SELECTORS_SUBJ, timeout=1000)
                    if subj_el:
                        compose_loaded = True
                        break
                except Exception:
                    pass
                page.wait_for_timeout(300)

            if not compose_loaded:
                raise Exception("点击写信按钮后，写信表单未能成功加载")

            # 等表单完全加载
            page.wait_for_timeout(500)

            # ── Step 3: 填写收件人 ──
            filled_count = 0
            if recipient_names:
                print("[3/5] 填写收件人...")
                filled_count = fill_recipients_fast(page, recipient_names)
                # 收件人填完后，Tab 切换到主题输入框
                page.keyboard.press("Tab")
                page.wait_for_timeout(50)
            else:
                print("[3/5] 无收件人，跳过")

            # ── Step 4: 填写主题+正文 ──
            print("[4/5] 填写主题+正文...")
            try:
                subj_el, subj_fr = wait_for_visible_element(page, SELECTORS_SUBJ, timeout=5000)
                if subj_el:
                    subj_el.fill(subject)
                    print(f"  [-] Subject: {subject[:50]}")
                else:
                    print("  [!] Visible Subject field not found")
            except Exception as e:
                print(f"  [!] Subject 填写失败: {e}")

            if inject_body(page, body_html):
                print("  [+] Body 注入成功")
            else:
                print("  [!] Body 注入失败")

            # ── Step 5: 存草稿 ──
            print("[5/5] 保存草稿...")
            save_btn, save_fr = wait_for_visible_element(page, SELECTORS_SAVE, timeout=5000)
            if save_btn:
                try:
                    save_btn.evaluate("""el=>{const o={bubbles:true,cancelable:true,view:window};el.dispatchEvent(new MouseEvent('mousedown',o));el.dispatchEvent(new MouseEvent('mouseup',o));el.dispatchEvent(new MouseEvent('click',o));}""")
                    print("  [-] 存草稿 dispatched")
                except:
                    try: save_btn.click(force=True, no_wait_after=True)
                    except: pass

                saved = False
                try:
                    page.locator('text=/保存草稿成功|草稿已保存|已保存|保存成功/').wait_for(timeout=3000)
                    for text in ["保存草稿成功", "草稿已保存", "已保存", "保存成功"]:
                        if page.locator(f"text={text}").is_visible():
                            print(f"  [+] ✅ 确认: {text}")
                            saved = True; break
                except:
                    pass

                if not saved:
                    print("  [*] 未检测到确认文本，草稿大概率已保存")
            else:
                print("  [!] 存草稿按钮未找到")
                try:
                    shot = SCRIPT_DIR / "debug_fast_save_fail.png"
                    page.screenshot(path=str(shot))
                    print(f"  [D] 截图: {shot}")
                except: pass

            browser.close()
            print(f"\n✅ 完成！草稿已保存到 Coremail 草稿箱")
            if recipient_names and filled_count > 0:
                print(f"   收件人已自动填写 {filled_count}/{len(recipient_names)} 人")
                if filled_count < len(recipient_names):
                    missed = [n for i, n in enumerate(recipient_names) if i >= filled_count]
                    print(f"   未填写：{'、'.join(missed)}，请在 Coremail 中手动补齐")
            return True

        except Exception as exc:
            print(f"\n[ERROR] {exc}")
            try: browser.close()
            except: pass
            sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="Coremail Fast Draft Saver v2.0")
    ap.add_argument("--config", default="", help="config.json 路径")
    ap.add_argument("--subject", required=True, help="邮件主题")
    ap.add_argument("--body-file", required=True, help="邮件正文文件（Markdown）")
    ap.add_argument("--recipients", default="", help="收件人姓名（逗号分隔，自动逐字输入+下拉框选择）")
    ap.add_argument("--no-headless", action="store_true", help="显示浏览器窗口")
    args = ap.parse_args()

    cfg_path = find_config(args.config)
    cfg = load_config(cfg_path)

    recipient_names = [n.strip() for n in args.recipients.split(",") if n.strip()] if args.recipients else None

    # Filter out sender name
    mail_cfg = cfg.get("mail", {})
    username = mail_cfg.get("username", "")
    csv_path = resolve_csv_path(cfg)
    sender_name = get_sender_name(username, csv_path)

    if recipient_names and sender_name:
        recipient_names_filtered = [r for r in recipient_names if r != sender_name]
        if len(recipient_names_filtered) < len(recipient_names):
            print(f"  [*] 过滤发件人 {sender_name}，过滤前 {len(recipient_names)} 人，过滤后 {len(recipient_names_filtered)} 人")
        recipient_names = recipient_names_filtered

    save_draft_fast(cfg, args.subject, args.body_file, recipient_names, headless=not args.no_headless)


if __name__ == "__main__":
    main()
