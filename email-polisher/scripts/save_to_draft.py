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

# Resolve config path relative to script directory
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
CONFIG_PATH = SKILL_DIR / "config.json"

KEY_PATH = "/Users/wujin/.workbuddy/.meeting_skill_key"
STORAGE_STATE = "/Users/wujin/.workbuddy/.coremail_storage_state.json"
OUT_DIR = "/Volumes/Macintosh HD_Data/WorkBuddy/邮件发送"

# Selector definitions
SEL_COMPOSE = "button.btn-compose, button:has-text('写 信'), button:has-text('写信'), .btn-compose, a:has-text('写信')"
SEL_SUBJ = "input[name='subject'], input#subject, input#subj, input[placeholder*='主题']"
SEL_TO = "input#toInput, input[name='to'], input#to, input[placeholder*='收件人'], #toAddrInput"

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

def resolve_recipient_from_body(body_text, csv_path):
    lines = [l.strip() for l in body_text.split('\n') if l.strip()]
    if not lines:
        return None
    greeting = lines[0]
    
    group_keywords = ["各位", "大家", "领导", "同事", "团队", "老师们", "同仁", "全体", "全员"]
    if any(kw in greeting for kw in group_keywords):
        print(f"    Greeting '{greeting}' matches group keywords. Leaving recipient empty.")
        return None
        
    name = greeting
    name = re.sub(r'[：:\s,!！]+$', '', name)
    name = re.sub(r'(老师|总|经理|主任|副总|高级)$', '', name)
    name = name.strip()
    
    if not name:
        return None
        
    matches = []
    try:
        if csv_path and os.path.exists(csv_path):
            for encoding in ['utf-8', 'gbk', 'gb2312']:
                try:
                    with open(csv_path, mode='r', encoding=encoding) as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            person = row.get('人员', '').strip()
                            dept = row.get('部门', '').strip()
                            if person == name or person.startswith(name):
                                matches.append((person, dept))
                    break
                except:
                    continue
    except Exception as e:
        print(f"    Error reading CSV roster: {e}")
        
    if matches:
        print(f"    Matched names in CSV for greeting '{greeting}': {[m[0] for m in matches]}")
        for person, dept in matches:
            if dept == "技术研发部":
                return person
        return matches[0][0]
    
    if len(name) <= 4:
        return name
    return None

def md_to_html(md: str) -> str:
    """Minimal Markdown to HTML converter to preserve spacing, bolding and breaks"""
    html = md
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = html.replace("  ", "&nbsp;&nbsp;")
    html = html.replace("\n\n", "<div><br></div>")
    html = html.replace("\n", "<br>")
    return html

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
    """Instantly insert HTML body into Coremail editor without slow keyboard typing"""
    html = md_to_html(body_text)
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
    parser = argparse.ArgumentParser(description="Coremail Draft Saver Utility")
    parser.add_argument("--subject", default="", help="Email Subject")
    parser.add_argument("--body-file", required=True, help="Path to plain text email body file")
    parser.add_argument("--recipients", default="", help="Email recipients (comma or space separated)")
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

    # Parse Recipients from body file if present
    recipients = []
    recipients_match = re.search(r'^(?:收件人|To)\s*[:：]\s*(.*)$', body, re.MULTILINE | re.IGNORECASE)
    if recipients_match:
        recipients_str = recipients_match.group(1).strip()
        recipients = [r.strip() for r in re.split(r'[,，\s]+', recipients_str) if r.strip()]
        body = re.sub(r'^(?:收件人|To)\s*[:：].*$\n?', '', body, flags=re.MULTILINE | re.IGNORECASE)
        print(f"🎯 Parsed recipients from body file: {recipients}")

    # Load Credentials dynamically from local skill config
    print("[0] Loading mail credentials...")
    url, email, password, csv_path = load_mail_credentials()
    print(f"    Loaded config: URL={url}, Username={email}")

    if args.recipients:
        recipients = [r.strip() for r in re.split(r'[,，\s]+', args.recipients) if r.strip()]
        print(f"🎯 Overridden recipients from CLI: {recipients}")

    if not recipients:
        recipient_name = resolve_recipient_from_body(body, csv_path)
        if recipient_name:
            recipients = [recipient_name]
            print(f"🎯 Resolved recipient from body greeting: {recipient_name}")
        else:
            print("🎯 No specific recipient resolved or provided. Leaving 'To' field blank.")

    body = body.lstrip()

    print("🚀 Launching Playwright (Max Speed Mode)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context_opts = {
            "ignore_https_errors": True,
            "viewport": {"width": 1280, "height": 900},
            "locale": "zh-CN"
        }
        
        if os.path.exists(STORAGE_STATE) and os.path.getsize(STORAGE_STATE) > 100:
            print("🔑 Loading active session state...")
            context_opts["storage_state"] = STORAGE_STATE
            
        context = browser.new_context(**context_opts)
        page = context.new_page()

        try:
            # Step 1: Open webmail (fast commit)
            print("[1] Opening mail.gtht.com...")
            page.goto(url, wait_until="commit", timeout=10000)
            page.wait_for_timeout(1000)

            # Check if login form is visible
            uid_input = page.query_selector("input#uid")
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

            # If we performed login, save the new session state
            if uid_input:
                context.storage_state(path=STORAGE_STATE)
                print("💾 Saved fresh session state.")

            # Step 2: Click Compose with retry loop to handle unbound JS handlers
            print("[3] Clicking compose...")
            compose_page = None
            subj_el = None
            compose_frame = None
            
            for click_attempt in range(4):
                try:
                    new_page = None
                    # Click, and listen for new tab concurrently
                    with context.expect_page(timeout=2000) as new_page_info:
                        compose_btn.click(force=True)
                    new_page = new_page_info.value
                    print("    Compose opened in new tab.")
                    compose_page = new_page
                    compose_page.wait_for_load_state("domcontentloaded")
                except:
                    # Click might open compose inline in the current page
                    compose_page = page
                
                # Check if compose form fields are visible
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
                print("    Skipped To field (no recipient resolved/provided)")

            # Fill Subject
            subj_el.fill(subject)
            print("    Filled Subject")

            # Fill Body (Instantly)
            body_written = insert_body(compose_page, body)
            if not body_written:
                # Fallback
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
                send_btn = compose_frame.query_selector('a:has-text("发送"), button:has-text("发送"), span:has-text("发送")')
                if not send_btn:
                    send_btn = compose_page.query_selector('a:has-text("发送"), button:has-text("发送"), span:has-text("发送")')
                if send_btn:
                    send_btn.click(force=True)
                    print("    Clicked send button")
                else:
                    raise Exception("Failed to find send button")
                
                # Wait for send confirmation
                compose_page.wait_for_timeout(3000)
                compose_page.screenshot(path=os.path.join(OUT_DIR, "coremail_final.png"))
                print("[7] ✅ Done! Email successfully sent.")
            else:
                print("[6] Saving draft...")
                compose_frame.keyboard.press("Control+s")
                compose_page.wait_for_timeout(1000)

                # Click save draft button to confirm
                save_btn = compose_frame.query_selector('a:has-text("存草稿"), button:has-text("存草稿"), span:has-text("存草稿")')
                if not save_btn:
                    save_btn = compose_page.query_selector('a:has-text("存草稿"), button:has-text("存草稿"), span:has-text("存草稿")')
                
                if save_btn:
                    save_btn.click(force=True)
                    print("    Clicked save draft button")

                # Wait for save confirmation
                compose_page.wait_for_timeout(1500)
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
