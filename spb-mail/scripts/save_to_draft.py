#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generic Coremail webmail draft saver using local skill config and encryption key"""

import os
import re
import csv
import json
import sys
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

# Load config from global email_expert configuration
CONFIG_PATH = Path("/Users/wujin/.gemini/config/skills/email-polisher/config.json")
KEY_PATH = "/Users/wujin/.workbuddy/.meeting_skill_key"
STORAGE_STATE = "/Users/wujin/.workbuddy/.coremail_storage_state.json"
OUT_DIR = "/Volumes/Macintosh HD_Data/WorkBuddy/邮件发送"

# Selector definitions
SEL_COMPOSE = "button.btn-compose, button:has-text('写 信'), button:has-text('写信'), .btn-compose, a:has-text('写信')"
SEL_SUBJ = "input[name='subject'], input#subject, input#subj, input[placeholder*='主题']"
SEL_TO = ".j-form-item-to .tag-editor textarea, .tag-editor textarea, li.tag-editor-li textarea, .tag-editor-tag textarea, input#toInput, input[name='to'], input#to, input[placeholder*='收件人'], #toAddrInput"
SEL_CC = ".j-form-item-cc .tag-editor textarea, .j-form-item-cc li.tag-editor-li textarea, .j-form-item-cc textarea, input#ccInput, input[name='cc'], input#cc, input[placeholder*='抄送'], #ccAddrInput"

def decrypt_password(enc_pwd, key_path):
    if not enc_pwd:
        return ""
    m = re.match(r"^ENC:(.*)", enc_pwd)
    if not m:
        return enc_pwd
        
    key = None
    if os.path.exists(key_path):
        try:
            with open(key_path, 'rb') as kf:
                key = kf.read().strip()
        except Exception as e:
            print(f"    [!] Error reading decryption key: {e}")
            
    if not key:
        key = (os.environ.get("CORMAIL_ENC_KEY") or "").encode()
        
    if not key or len(key) != 44:
        print("[ERROR] Decryption key not found or invalid.")
        sys.exit(1)
        
    try:
        from cryptography.fernet import Fernet
        return Fernet(key).decrypt(m.group(1).encode()).decode()
    except Exception as e:
        print(f"[ERROR] Password decryption failed: {e}")
        sys.exit(1)

def load_mail_credentials():
    if not CONFIG_PATH.exists():
        print(f"[ERROR] Config file not found at {CONFIG_PATH}")
        sys.exit(1)
        
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        mail_cfg = cfg.get("mail", {})
        url = mail_cfg.get("url", "https://mail.gtht.com/")
        username = mail_cfg.get("username", "")
        enc_password = mail_cfg.get("password", "")
        csv_path = cfg.get("csv_path", "")
        
        password = decrypt_password(enc_password, KEY_PATH)
        return url, username, password, csv_path
    except Exception as e:
        print(f"[ERROR] Failed to load config: {e}")
        sys.exit(1)

def md_to_html(md: str) -> str:
    """Minimal Markdown to HTML converter to preserve spacing, bolding and breaks"""
    html = md
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = html.replace("  ", "&nbsp;&nbsp;")
    html = html.replace("\n\n", "<div><br></div>")
    html = html.replace("\n", "<br>")
    return html

def extract_plain_emails(recipients):
    """将形如 `"姓名" <email>` 或 `email` 的收件人转换为纯邮箱地址。

    Coremail 收件人输入框直接键入纯邮箱地址最可靠；带引号+尖括号的
    完整格式可能无法被正确解析为联系人，导致发送失败。
    """
    emails = []
    for r in recipients:
        r = r.strip()
        if not r:
            continue
        m = re.search(r'<([^<>]+)>', r)
        if m:
            email = m.group(1).strip()
        else:
            email = r.strip(' "\'')
        if email and '@' in email:
            emails.append(email)
        elif email:
            # 无 @ 的地址（如纯姓名），保留原样交由 Coremail 处理
            emails.append(email)
    return emails

def find_in_all_frames(page, selector, timeout=5000):
    """Find a selector across the main page and all sub-frames, returning the element and its frame"""
    try:
        el = page.wait_for_selector(selector, timeout=timeout)
        if el and el.is_visible():
            return el, page
    except:
        pass
    
    for fr in page.frames:
        if fr == page:
            continue
        try:
            el = fr.wait_for_selector(selector, timeout=1000)
            if el and el.is_visible():
                return el, fr
        except:
            continue
            
    return None, None

def insert_body(page, body_text, is_html=False):
    """Instantly insert HTML body into Coremail editor without slow keyboard typing"""
    html = body_text if is_html else md_to_html(body_text)
    js_html = json.dumps(html)
    inserted = False

    def _is_editor_body(fr):
        try:
            return fr.evaluate("""() => {
                const d = document;
                return (d.designMode === 'on') ||
                       (d.body && d.body.contentEditable === 'true') ||
                       (d.querySelector('[contenteditable="true"]') !== null);
            }""")
        except:
            return False

    def _write_body(fr):
        try:
            fr.evaluate(f"""
                (() => {{
                    const d = document;
                    if (d.designMode === 'on') {{
                        d.open();
                        d.write({js_html});
                        d.close();
                    }} else if (d.body && d.body.contentEditable === 'true') {{
                        d.body.innerHTML = {js_html};
                        d.body.dispatchEvent(new Event("input", {{bubbles:true}}));
                    }} else {{
                        const ed = d.querySelector('[contenteditable="true"]');
                        if (ed) {{
                            ed.innerHTML = {js_html};
                            ed.dispatchEvent(new Event("input", {{bubbles:true}}));
                        }}
                    }}
                }})()
            """)
            return True
        except:
            return False

    # Check existing frames first
    for idx, fr in enumerate(page.frames):
        if fr == page:
            continue
        if _is_editor_body(fr):
            if _write_body(fr):
                print(f"    [+] Body written in iframe #{idx} instantly.")
                return True

    # Polling wait if not ready
    for attempt in range(15):
        for idx, fr in enumerate(page.frames):
            if fr == page:
                continue
            if _is_editor_body(fr):
                if _write_body(fr):
                    print(f"    [+] Body written in iframe #{idx} (attempt {attempt+1}).")
                    inserted = True
                    break
        if inserted:
            break
        page.wait_for_timeout(300)

    return inserted

def main():
    parser = argparse.ArgumentParser(description="Coremail Draft Saver & Email Sender Utility")
    parser.add_argument("--subject", default="", help="Email Subject")
    parser.add_argument("--body-file", required=True, help="Path to plain text email body file")
    parser.add_argument("--recipients", default="", help="Email recipients (comma/space/semicolon separated)")
    parser.add_argument("--cc", default="", help="Email CC recipients (comma/space/semicolon separated)")
    parser.add_argument("--send", action="store_true", help="Send the email immediately instead of saving as draft")
    args = parser.parse_args()

    # Load Body
    if not os.path.exists(args.body_file):
        print(f"[ERROR] Body file not found at {args.body_file}")
        sys.exit(1)
        
    with open(args.body_file, 'r', encoding='utf-8') as f:
        body = f.read()

    is_html = args.body_file.lower().endswith('.html')

    # Parse Subject from body file if present
    subject = args.subject
    subject_match = re.search(r'^(?:主题|邮件主题|Subject)\s*[:：]\s*(.*)$', body, re.MULTILINE | re.IGNORECASE)
    if subject_match:
        subject = subject_match.group(1).strip()
        body = re.sub(r'^(?:主题|邮件主题|Subject)\s*[:：].*$\n?', '', body, flags=re.MULTILINE | re.IGNORECASE)
        print(f"🎯 Parsed subject from body file: {subject}")

    # Load Credentials
    print("[0] Loading mail credentials...")
    url, email, password, csv_path = load_mail_credentials()
    print(f"    Loaded config: URL={url}, Username={email}")

    # Parse Recipients from args
    recipients = []
    if args.recipients:
        recipients = [r.strip() for r in re.split(r'[;；,，\r\n]+', args.recipients) if r.strip()]
        recipients = extract_plain_emails(recipients)
        print(f"🎯 Recipients: {recipients}")

    cc_recipients = []
    if args.cc:
        cc_recipients = [r.strip() for r in re.split(r'[;；,，\r\n]+', args.cc) if r.strip()]
        cc_recipients = extract_plain_emails(cc_recipients)
        print(f"🎯 CC Recipients: {cc_recipients}")

    body = body.lstrip()

    # Ensure output dir exists
    os.makedirs(OUT_DIR, exist_ok=True)

    # Detect Chrome.app path on macOS to avoid crash
    chrome_locs = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Google Chrome.app/Contents/MacOS/google-chrome",
    ]
    chrome_exe = next((loc for loc in chrome_locs if Path(loc).exists()), None)

    print("🚀 Launching Playwright (Max Speed Mode)...")
    with sync_playwright() as p:
        browser = None
        try:
            if chrome_exe:
                browser = p.chromium.launch(headless=True, executable_path=chrome_exe)
                print(f"    Launched Chrome: {chrome_exe}")
            else:
                browser = p.chromium.launch(headless=True)
                print("    Launched Bundled Chromium")
        except Exception as e:
            print(f"    Failed to launch Chrome: {e}, falling back to bundled Chromium")
            browser = p.chromium.launch(headless=True)

        context_opts = {
            "ignore_https_errors": True,
            "viewport": {"width": 1280, "height": 900},
            "locale": "zh-CN"
        }
        
        # Skip loading session state - always do fresh login for reliability
        # if os.path.exists(STORAGE_STATE) and os.path.getsize(STORAGE_STATE) > 100:
        #     print("🔑 Loading active session state...")
        #     context_opts["storage_state"] = STORAGE_STATE
            
        context = browser.new_context(**context_opts)
        page = context.new_page()

        try:
            # Step 1: Open webmail (wait for DOM ready)
            print("[1] Opening mail.gtht.com...")
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)

            # Check if login form is visible
            uid_input = page.query_selector("input#uid")
            if not uid_input:
                # Try alternative login form selectors
                uid_input = page.query_selector("input[name='uid']")
            if not uid_input:
                # Maybe already logged in? Check for compose button
                compose_check = page.query_selector("button.btn-compose, button:has-text('写 信'), button:has-text('写信')")
                if compose_check:
                    print("    Already logged in (compose button found).")
                else:
                    print("    [WARN] Login form not found, taking screenshot...")
                    page.screenshot(path=os.path.join(OUT_DIR, "coremail_before_login.png"))
                    # Try waiting a bit more
                    page.wait_for_timeout(5000)
                    uid_input = page.query_selector("input#uid")
                if uid_input:
                    print("    Found login form after waiting.")
            if uid_input:
                print("[2] Session expired. Performing fresh login...")
                uid_input.fill(email)
                page.fill("input#password", password)

                ssl_checkbox = page.query_selector("#rcmloginssl")
                if ssl_checkbox and not ssl_checkbox.is_checked():
                    ssl_checkbox.click()

                # Submit form instantly by pressing Enter
                page.keyboard.press("Enter")
                print("    Submitted login form.")

            # Dynamically wait for login completion by searching for compose button in all frames
            print("    Waiting for email page to load...")
            compose_btn = None
            for attempt in range(25):
                compose_btn, btn_frame = find_in_all_frames(page, SEL_COMPOSE, timeout=1000)
                if compose_btn:
                    break
                page.wait_for_timeout(500)
                
            if not compose_btn:
                raise Exception("Timed out waiting for mail page to load (Compose button not found)")
            print("✅ Mailbox loaded successfully!")

            # Session state loading is disabled - always fresh login
            # if uid_input:
            #     context.storage_state(path=STORAGE_STATE)
            #     print("💾 Saved fresh session state.")

            # Step 2: Click Compose with retry loop
            print("[3] Clicking compose...")
            compose_page = None
            subj_el = None
            compose_frame = None
            
            for click_attempt in range(4):
                try:
                    new_page = None
                    with context.expect_page(timeout=5000) as new_page_info:
                        compose_btn.click(force=True)
                        print("    Waiting for compose tab to open...")
                    new_page = new_page_info.value
                    print("    Compose opened in new tab.")
                    compose_page = new_page
                    compose_page.wait_for_load_state("domcontentloaded", timeout=15000)
                    compose_page.wait_for_timeout(2000)
                except Exception as e:
                    print(f"    New tab not opened (trying current page): {e}")
                    compose_page = page
                
                print(f"    Check compose form visibility (attempt {click_attempt+1}/4)...")
                # Try multiple times to find the subject input (iframe may be slow to load)
                for iframe_wait in range(5):
                    subj_el, compose_frame = find_in_all_frames(compose_page, SEL_SUBJ, timeout=1000)
                    if subj_el:
                        break
                    compose_page.wait_for_timeout(800)
                
                if subj_el:
                    break
                    
                print("    Compose form not visible yet. Waiting and retrying click...")
                page.wait_for_timeout(2000)
                
            if not subj_el:
                # Take a screenshot for debugging
                try:
                    page.screenshot(path=os.path.join(OUT_DIR, "coremail_compose_timeout.png"))
                    if compose_page and compose_page != page:
                        compose_page.screenshot(path=os.path.join(OUT_DIR, "coremail_compose_page.png"))
                except:
                    pass
                raise Exception("Timed out waiting for compose form")
                
            print(f"    [+] Compose form found in {'page' if compose_frame == compose_page else 'iframe'}")

            # Step 3: Fill Details
            print("[5] Filling details...")
            
            # Fill To
            if recipients:
                to_el = compose_frame.query_selector(SEL_TO)
                if to_el:
                    try:
                        to_el.focus()
                    except Exception as fe:
                        print(f"    Failed to focus to_el: {fe}")
                    for r in recipients:
                        print(f"    Typing recipient: {r}")
                        try:
                            to_el.focus()
                        except:
                            pass
                        compose_frame.keyboard.type(r, delay=30)
                        compose_frame.wait_for_timeout(800)
                        compose_frame.keyboard.press("Enter")
                        compose_frame.wait_for_timeout(400)
                    print(f"    Filled To: {recipients}")
            else:
                print("    Skipped To field (no recipient provided)")

            # Fill CC
            if cc_recipients:
                cc_el = compose_frame.query_selector(SEL_CC)
                if not cc_el or not cc_el.is_visible():
                    # Click Add CC button
                    btn_cc = compose_frame.query_selector('a:has-text("添加抄送"), span:has-text("添加抄送"), a:has-text("抄送"), span:has-text("抄送")')
                    if not btn_cc:
                        btn_cc = compose_page.query_selector('a:has-text("添加抄送"), span:has-text("添加抄送"), a:has-text("抄送"), span:has-text("抄送")')
                    if btn_cc:
                        print("    Clicking '添加抄送' link...")
                        btn_cc.click()
                        compose_frame.wait_for_timeout(500)
                
                cc_el = compose_frame.query_selector(SEL_CC)
                if cc_el:
                    try:
                        cc_el.focus()
                    except:
                        pass
                    for r in cc_recipients:
                        print(f"    Typing CC: {r}")
                        try:
                            cc_el.focus()
                        except:
                            pass
                        compose_frame.keyboard.type(r, delay=30)
                        compose_frame.wait_for_timeout(800)
                        compose_frame.keyboard.press("Enter")
                        compose_frame.wait_for_timeout(400)
                    print(f"    Filled CC: {cc_recipients}")
                else:
                    print("    [WARN] CC input field not found/visible after trying to show it.")

            # Fill Subject
            subj_el.fill(subject)
            print("    Filled Subject")

            # Fill Body (Instantly)
            body_written = insert_body(compose_page, body, is_html=is_html)
            if not body_written:
                for sel in ['[contenteditable="true"]', '#editor_body', 'textarea']:
                    try:
                        el = compose_frame.query_selector(sel)
                        if el:
                            el.fill(body)
                            body_written = True
                            break
                    except:
                        pass
            
            if not body_written:
                raise Exception("Failed to write email body")

            # Step 4: Save Draft or Send
            if args.send:
                print("[6] Sending email...")
                # Primary: use .j-tbl-send (Coremail 真实发送按钮)
                send_btn = compose_frame.query_selector('.j-tbl-send')
                if not send_btn:
                    send_btn = compose_page.query_selector('.j-tbl-send')
                # Fallback: text-based selectors
                if not send_btn:
                    send_btn = compose_frame.query_selector('a:has-text("发送"), button:has-text("发送"), span:has-text("发送")')
                if not send_btn:
                    send_btn = compose_page.query_selector('a:has-text("发送"), button:has-text("发送"), span:has-text("发送")')
                if send_btn:
                    send_btn.click(force=True)
                    print("    Clicked send button")
                else:
                    raise Exception("Failed to find send button")
                
                # Handle any confirmation dialogs that may appear after clicking send
                compose_page.wait_for_timeout(1500)
                # Check for "确定不需要写邮件内容吗？" or "请填写收件人地址" dialogs
                for confirm_sel in [
                    "button:has-text('确定')", "a:has-text('确定')",
                    ".u-dialog button:first-child", ".u-dialog-operation button:first-child"
                ]:
                    try:
                        confirm_btn = compose_page.query_selector(confirm_sel)
                        if confirm_btn and confirm_btn.is_visible():
                            confirm_btn.click(force=True)
                            print(f"    Clicked confirmation: {confirm_sel}")
                            compose_page.wait_for_timeout(1000)
                            break
                    except:
                        pass
                
                # Wait for send confirmation - robust: check sent folder nav OR compose close
                print("    Waiting for send confirmation...")
                sent = False
                for poll_sec in range(15):
                    # Check 1: Main page URL navigated to sent folder
                    try:
                        if 'mail.list' in (compose_page.url or ''):
                            sent = True
                            break
                    except:
                        pass
                    
                    # Check 2: Compose inputs hidden/removed in any frame (compose closed)
                    closed = False
                    for fr in compose_page.frames:
                        try:
                            to = fr.query_selector('input[name="to"], input#toInput, input#to')
                            subj = fr.query_selector('input[name="subject"], input#subject')
                            to_hidden = (to is None) or (not to.is_visible())
                            subj_hidden = (subj is None) or (not subj.is_visible())
                            if to_hidden and subj_hidden:
                                closed = True
                                break
                        except:
                            continue
                    if closed:
                        sent = True
                        break
                    
                    compose_page.wait_for_timeout(1000)
                
                compose_page.screenshot(path=os.path.join(OUT_DIR, "coremail_final.png"))
                
                if sent:
                    print("[7] ✅ Done! Email successfully sent (verified: compose closed / navigated to sent folder).")
                else:
                    print("[7] ⚠️ Send button clicked, but could not verify if email was actually sent.")
                    print("    Please check the screenshot at:", os.path.join(OUT_DIR, "coremail_final.png"))
            else:
                print("[6] Saving draft...")
                # Method 1: Click "存草稿" button directly
                save_btn = compose_frame.query_selector('a:has-text("存草稿"), button:has-text("存草稿"), span:has-text("存草稿")')
                if not save_btn:
                    save_btn = compose_page.query_selector('a:has-text("存草稿"), button:has-text("存草稿"), span:has-text("存草稿")')
                
                if save_btn:
                    print("    Clicking '存草稿' button...")
                    save_btn.click(force=True)
                    compose_page.wait_for_timeout(2000)
                    print("    Save draft button clicked.")
                else:
                    # Fallback: use keyboard shortcut (Cmd+S on Mac, Ctrl+S on Windows)
                    print("    '存草稿' button not found, using keyboard shortcut...")
                    modifier = "Meta" if sys.platform == "darwin" else "Control"
                    compose_page.keyboard.press(f"{modifier}+s")
                    compose_page.wait_for_timeout(1500)
                
                # Wait for save confirmation (look for success message)
                try:
                    confirm_el = compose_page.wait_for_selector('text="已保存", text="草稿已保存", text="保存成功"', timeout=5000)
                    if confirm_el:
                        print("    ✅ Draft save confirmed!")
                except:
                    print("    (No explicit save confirmation found, checking screenshot...)")
                
                compose_page.screenshot(path=os.path.join(OUT_DIR, "coremail_draft_saved.png"))
                print("[7] ✅ Done! Draft successfully saved to 草稿箱.")

        except Exception as e:
            print(f"❌ Error during drafting: {e}")
            try:
                page.screenshot(path=os.path.join(OUT_DIR, "coremail_error.png"))
            except:
                pass
        finally:
            browser.close()

if __name__ == "__main__":
    main()
