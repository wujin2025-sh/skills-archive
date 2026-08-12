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
SEL_TO = "input#toInput, input[name='to'], input#to, input[placeholder*='收件人'], #toAddrInput"
SEL_CC = "input#ccInput, input[name='cc'], input#cc, input[placeholder*='抄送'], #ccAddrInput"

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
    stripped = md.lstrip()
    if stripped.startswith("<") or "<html" in md.lower() or "<table" in md.lower():
        return md
    html = md
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = html.replace("  ", "&nbsp;&nbsp;")
    html = html.replace("\n\n", "<div><br></div>")
    html = html.replace("\n", "<br>")
    return html

def parse_clean_email(recipient_str):
    """提取干净的邮箱地址或姓名邮箱组合"""
    m = re.search(r'<([^>]+)>', recipient_str)
    if m:
        return m.group(1).strip()
    return recipient_str.strip()

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

def insert_body(page, body_text):
    """Instantly insert HTML body into Coremail editor using KindEditor official API or fallback"""
    html = md_to_html(body_text)
    js_html = json.dumps(html)

    for attempt in range(15):
        for idx, fr in enumerate(page.frames):
            try:
                res = fr.evaluate(f"""() => {{
                    if (window.KindEditor && window.KindEditor.instances && window.KindEditor.instances.length > 0) {{
                        window.KindEditor.instances[0].html({js_html});
                        if (window.KindEditor.instances[0].sync) window.KindEditor.instances[0].sync();
                        return true;
                    }}
                    const ed = document.querySelector('.ke-edit-textarea, [contenteditable="true"], [contenteditable=""], [contenteditable]');
                    if (ed) {{
                        ed.innerHTML = {js_html};
                        ed.dispatchEvent(new Event("input", {{bubbles:true}}));
                        ed.dispatchEvent(new Event("change", {{bubbles:true}}));
                        return true;
                    }}
                    return false;
                }}""")
                if res:
                    print(f"    [+] Body written via KindEditor API / DOM in frame #{idx}.")
                    return True
            except:
                pass
        page.wait_for_timeout(300)

    return False

def main():
    parser = argparse.ArgumentParser(description="Coremail Draft Saver & Email Sender Utility")
    parser.add_argument("--subject", default="", help="Email Subject")
    parser.add_argument("--body-file", required=True, help="Path to plain text email body file")
    parser.add_argument("--recipients", default="", help="Email recipients (comma/space/semicolon separated)")
    parser.add_argument("--cc", default="", help="Email CC recipients (comma/space/semicolon separated)")
    parser.add_argument("--attachments", "--attachment", "-a", default="", help="Attachment files (comma or semicolon separated)")
    parser.add_argument("--send", action="store_true", help="Send the email immediately instead of saving as draft")
    args = parser.parse_args()

    # Load Body
    if not os.path.exists(args.body_file):
        print(f"[ERROR] Body file not found at {args.body_file}")
        sys.exit(1)
        
    with open(args.body_file, 'r', encoding='utf-8') as f:
        body = f.read()

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
        print(f"🎯 Recipients: {recipients}")

    cc_recipients = []
    if args.cc:
        cc_recipients = [r.strip() for r in re.split(r'[;；,，\r\n]+', args.cc) if r.strip()]
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
        
        # Force fresh login every time to prevent stale session expiry popup
        if os.path.exists(STORAGE_STATE):
            try:
                os.remove(STORAGE_STATE)
                print("🧹 Cleared stale session state for clean login.")
            except:
                pass

        context = browser.new_context(**context_opts)
        page = context.new_page()

        try:
            # Step 1: Open webmail (fast commit)
            print("[1] Opening mail.gtht.com...")
            page.goto(url, wait_until="commit", timeout=15000)
            page.wait_for_timeout(1000)

            # Check if login form or expired modal is visible
            print("[2] Performing fresh login...")
            btn_relogin = page.query_selector('button:has-text("重新登录"), a:has-text("重新登录"), .btn-relogin')
            if btn_relogin:
                try:
                    btn_relogin.click(force=True)
                    page.wait_for_timeout(1000)
                except:
                    pass

            for _ in range(10):
                uid_input = page.query_selector("input#uid, input[name='uid']")
                if uid_input:
                    break
                page.wait_for_timeout(300)

            uid_input = page.query_selector("input#uid, input[name='uid']")
            if uid_input:
                uid_input.fill(email)
                page.fill("input#password", password)

                ssl_checkbox = page.query_selector("#rcmloginssl")
                if ssl_checkbox and not ssl_checkbox.is_checked():
                    ssl_checkbox.click()

                # Submit form instantly by pressing Enter
                page.keyboard.press("Enter")
                print("    Submitted login form successfully.")
            else:
                print("    [!] Login form not found directly, proceeding to check compose button...")

            # Dynamically wait for login completion by searching for compose button in all frames
            print("    Waiting for mailbox page to load...")
            compose_btn = None
            for attempt in range(25):
                compose_btn, btn_frame = find_in_all_frames(page, SEL_COMPOSE, timeout=1000)
                if compose_btn:
                    break
                page.wait_for_timeout(500)
                
            if not compose_btn:
                raise Exception("Timed out waiting for mail page to load (Compose button not found)")
            print("✅ Mailbox loaded successfully!")

            # Save the new session state
            context.storage_state(path=STORAGE_STATE)
            print("💾 Saved fresh session state.")

            # Step 2: Click Compose with retry loop
            print("[3] Clicking compose...")
            compose_page = None
            subj_el = None
            compose_frame = None
            
            for click_attempt in range(4):
                try:
                    new_page = None
                    with context.expect_page(timeout=2000) as new_page_info:
                        compose_btn.click(force=True)
                    new_page = new_page_info.value
                    print("    Compose opened in new tab.")
                    compose_page = new_page
                    compose_page.wait_for_load_state("domcontentloaded")
                except:
                    compose_page = page
                
                print(f"    Check compose form visibility (attempt {click_attempt+1}/4)...")
                subj_el, compose_frame = find_in_all_frames(compose_page, SEL_SUBJ, timeout=1500)
                if subj_el:
                    break
                    
                print("    Compose form not visible yet. Waiting and retrying click...")
                page.wait_for_timeout(1500)
                
            if not subj_el:
                raise Exception("Timed out waiting for compose form")
                
            print(f"    [+] Compose form found in {'page' if compose_frame == compose_page else 'iframe'}")

            # Step 3: Fill Details
            print("[5] Filling details...")
            
            # Fill To (Tag-by-Tag Mode for 100% Recipient Coverage)
            if recipients:
                to_el = compose_frame.query_selector(SEL_TO)
                if to_el:
                    try:
                        to_el.focus()
                    except Exception as fe:
                        print(f"    Failed to focus to_el: {fe}")
                    
                    clean_to_emails = [parse_clean_email(r) for r in recipients]
                    print(f"    Adding {len(clean_to_emails)} recipient emails into Coremail...")
                    for idx, email_addr in enumerate(clean_to_emails):
                        compose_page.keyboard.press("Escape")
                        compose_page.wait_for_timeout(50)
                        compose_page.keyboard.type(email_addr + ";", delay=3)
                        compose_page.wait_for_timeout(100)
                    compose_page.keyboard.press("Enter")
                    print(f"    ✅ Successfully added all {len(clean_to_emails)} recipients!")
            else:
                print("    Skipped To field (no recipient provided)")

            # Fill CC
            if cc_recipients:
                cc_el = compose_frame.query_selector(SEL_CC)
                if not cc_el or not cc_el.is_visible():
                    btn_cc = compose_frame.query_selector('a:has-text("添加抄送"), span:has-text("添加抄送"), a:has-text("抄送"), span:has-text("抄送")')
                    if not btn_cc:
                        btn_cc = compose_page.query_selector('a:has-text("添加抄送"), span:has-text("添加抄送"), a:has-text("抄送"), span:has-text("抄送")')
                    if btn_cc:
                        print("    Clicking '添加抄送' link...")
                        btn_cc.click()
                        compose_page.wait_for_timeout(500)
                
                cc_el = compose_frame.query_selector(SEL_CC)
                if cc_el:
                    clean_cc_emails = [parse_clean_email(r) for r in cc_recipients]
                    for idx, email_addr in enumerate(clean_cc_emails):
                        compose_page.keyboard.press("Escape")
                        compose_page.wait_for_timeout(50)
                        compose_page.keyboard.type(email_addr + ";", delay=3)
                        compose_page.wait_for_timeout(100)
                    compose_page.keyboard.press("Enter")
                    print(f"    Filled CC field with {len(cc_recipients)} recipients.")

            # Fill Subject
            subj_el.fill(subject)
            print("    Filled Subject")

            # Fill Body (Instantly)
            body_written = insert_body(compose_page, body)
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

            # Upload Attachments
            if args.attachments:
                att_paths = [a.strip() for a in re.split(r'[;；,]+', args.attachments) if a.strip()]
                valid_atts = [os.path.abspath(a) for a in att_paths if os.path.exists(a)]
                if valid_atts:
                    print(f"    [+] Uploading {len(valid_atts)} attachment(s)...")
                    file_input = compose_frame.query_selector('input[type="file"]')
                    if not file_input:
                        for fr in compose_page.frames:
                            fi = fr.query_selector('input[type="file"]')
                            if fi:
                                file_input = fi
                                break
                    if file_input:
                        file_input.set_input_files(valid_atts)
                        compose_page.wait_for_timeout(1500)
                        print(f"    ✅ Successfully uploaded attachment(s): {[os.path.basename(a) for a in valid_atts]}")
                    else:
                        print("    ⚠️ Could not find file input for attachments")

            # Helper to check and handle session expired popup
            def handle_expired_session(pg):
                btn_relogin = pg.query_selector('button:has-text("重新登录"), a:has-text("重新登录"), .btn-relogin')
                if not btn_relogin:
                    # check in all frames
                    for f in pg.frames:
                        btn_relogin = f.query_selector('button:has-text("重新登录"), a:has-text("重新登录")')
                        if btn_relogin:
                            break
                if btn_relogin:
                    print("⚠️ [Session Expired Popup] Detected '会话已过期，请重新登录'! Re-authenticating...")
                    try:
                        btn_relogin.click(force=True)
                        pg.wait_for_timeout(1500)
                    except:
                        pass
                    
                    pwd_el = pg.query_selector("input#password, input[type='password']")
                    if pwd_el:
                        pwd_el.fill(password)
                        pg.keyboard.press("Enter")
                        pg.wait_for_timeout(2000)
                        print("    Submitted fresh login credentials.")
                        return True
                return False

            # Step 4: Save Draft or Send
            if args.send:
                print("[6] Sending email...")
                send_btn = compose_frame.query_selector('a:has-text("发送"), button:has-text("发送"), span:has-text("发送")')
                if not send_btn:
                    send_btn = compose_page.query_selector('a:has-text("发送"), button:has-text("发送"), span:has-text("发送")')
                if send_btn:
                    send_btn.click(force=True)
                    print("    Clicked send button")
                else:
                    raise Exception("Failed to find send button")
                
                # Check session expiration
                compose_page.wait_for_timeout(1500)
                if handle_expired_session(compose_page):
                    compose_page.wait_for_timeout(1500)
                    send_btn = compose_frame.query_selector('a:has-text("发送"), button:has-text("发送"), span:has-text("发送")')
                    if send_btn:
                        send_btn.click(force=True)
                        
                compose_page.wait_for_timeout(2000)
                compose_page.screenshot(path=os.path.join(OUT_DIR, "coremail_final.png"))
                print("[7] ✅ Done! Email successfully sent.")
            else:
                print("[6] Saving draft...")
                save_btn = compose_frame.query_selector('a:has-text("存草稿"), button:has-text("存草稿"), span:has-text("存草稿")')
                if not save_btn:
                    save_btn = compose_page.query_selector('a:has-text("存草稿"), button:has-text("存草稿"), span:has-text("存草稿")')
                
                if save_btn:
                    save_btn.click(force=True)
                    print("    Clicked save draft button")
                else:
                    compose_frame.keyboard.press("Control+s")

                compose_page.wait_for_timeout(1500)
                
                # Check session expiration
                if handle_expired_session(compose_page):
                    compose_page.wait_for_timeout(1500)
                    save_btn = compose_frame.query_selector('a:has-text("存草稿"), button:has-text("存草稿"), span:has-text("存草稿")')
                    if save_btn:
                        save_btn.click(force=True)
                        print("    Re-clicked save draft button after re-login.")
                        compose_page.wait_for_timeout(2000)

                compose_page.screenshot(path=os.path.join(OUT_DIR, "coremail_final.png"))
                print("[7] ✅ Done! Final draft successfully saved.")

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
