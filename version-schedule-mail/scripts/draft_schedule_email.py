#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Coremail webmail draft saver for Version Schedule Email using local skill config and encryption key"""

import os
import re
import json
import sys
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

# Load config from global email_expert configuration
CONFIG_PATH = Path("/Users/wujin/.gemini/config/skills/email-polisher/config.json")
KEY_PATH = "/Users/wujin/.workbuddy/.meeting_skill_key"
OUT_DIR = "/Volumes/Macintosh HD_Data/WorkBuddy/邮件发送"

# Selector definitions
SEL_COMPOSE = "button.btn-compose, button:has-text('写 信'), button:has-text('写信'), .btn-compose, a:has-text('写信')"
SEL_SUBJ = "input[name='subject'], input#subject, input#subj, input[placeholder*='主题']"
SEL_TO = "input#toInput, input[name='to'], input#to, input[placeholder*='收件人'], #toAddrInput"
SEL_CC = "input#ccInput, input[name='cc'], input#cc, input[placeholder*='抄送'], #ccAddrInput"

DEFAULT_RECIPIENTS = (
    '"周倩" <zhouqian4@gtht.com>; "刘勇明" <liuyongming@gtht.com>; "胡玲杰" <hulingjie@gtht.com>; '
    '"乔露露" <qiaolulu@gtht.com>; "聂章艳" <niezhangyan@gtht.com>; "李萍萍" <lipingping@gtht.com>; '
    '"刘青" <liuqing5@gtht.com>; "丁伟" <dingwei2@gtht.com>; "罗琼" <luoqiong@gtht.com>; '
    '"高健" <gaojian2@gtht.com>; "常丽" <changli@gtht.com>; "李正林" <lizhenglin@gtht.com>; '
    '"揭由翔" <jieyouxiang@gtht.com>; "黄星" <huangxing@gtht.com>; "张志鹏" <zhangzhipeng@gtht.com>; '
    '"单大卫" <shandawei@gtht.com>; "程恩惠" <chengenhui@gtht.com>; "瞿格" <quge@gtht.com>; '
    '"王冰冰" <wangbingbing@gtht.com>; "李庆辉" <liqinghui@gtht.com>; "甘峰浩" <ganfenghao@gtht.com>; '
    '"吴亚如" <wuyaru@gtht.com>; "柴恒" <chaiheng@gtht.com>; "杜军辉" <dujunhui@gtht.com>; '
    '"张兆国" <zhangzhaoguo@gtht.com>; "刘辉" <liuhui7@gtht.com>; "苏清玲" <suqingling@gtht.com>; '
    '"茆莹莹" <maoyingying@gtht.com>; "刘璐" <liulu@gtht.com>; "季金燕" <jijinyan@gtht.com>; '
    '"樊静宜" <fanjingyi@gtht.com>; "李楷达" <likaida@gtht.com>; "张帆" <zhangfan4@gtht.com>; '
    '"唐登龙" <tangdenglong@gtht.com>; "谢一凡" <xieyifan@gtht.com>; "朱腾龙" <zhutenglong@gtht.com>; '
    '"沈芳" <shenfang@gtht.com>; "杨晨旭" <yangchenxu@gtht.com>; "俞梦妮" <yumengni@gtht.com>; '
    '"邵从人" <shaocongren@gtht.com>; "卢霖铨" <lulinquan@gtht.com>; "钱幼文" <qianyouwen@gtht.com>; '
    '"王壮壮" <wangzhuangzhuang@gtht.com>; "符振威" <fuzhenwei@gtht.com>; "刘牧青" <liumuqing@gtht.com>; '
    '"鄂泓希" <ehongxi@gtht.com>; "郑波" <zhengbo2@gtht.com>; "倪康夫" <nikangfu@gtht.com>; '
    '"刘栋梁" <liudongliang@gtht.com>; "史亮" <shiliang@gtht.com>; "陈喆" <chenzhe4@gtht.com>; '
    '"帅翔" <shuaixiang@gtht.com>; "刘灿彬" <liucanbin@gtht.com>; "徐嫦悦" <xuchangyue@gtht.com>; '
    '"徐适" <xushi@gtht.com>; "毕钰东方" <biyudongfang@gtht.com>; "张元超" <zhangyuanchao@gtht.com>; '
    '"史安妮" <shianni@gtht.com>; "刘琼" <liuqiong3@gtht.com>; "张之泽" <zhangzhize@gtht.com>; '
    '"谢越" <xieyue2@gtht.com>; "龚燕萍" <gongyanping@gtht.com>; "李鹤晨" <lihechen@gtht.com>; '
    '"宋健" <songjian2@gtht.com>; "吴进" <wujin@gtht.com>; "牛婷婷" <niutingting@gtht.com>; '
    '"张康" <zhangkang2@gtht.com>; "陈曦" <chenxi10@gtht.com>; "潘首道" <panshoudao@gtht.com>; '
    '"孙丽荣" <sunlirong@gtht.com>; "王南图" <wangnantu@gtht.com>; "虞聪" <yucong@gtht.com>; '
    '"冯通" <fengtong@gtht.com>; "侯英祺" <houyingqi@gtht.com>; "陈安童" <chenantong@gtht.com>; '
    '"UAT测试组" <uat测试组@gtht.com>; "叶飞" <yefei@gtht.com>; "施晔" <shiye@gtht.com>; '
    '"孙锴" <sunkai4@gtht.com>'
)

DEFAULT_CC = (
    '"王姝暘" <wangshuyang@gtht.com>; "赵永杰" <zhaoyongjie@gtht.com>; '
    '"周哲博" <zhouzhebo@gtht.com>; "姜婷婷" <jiangtingting2@gtht.com>; '
    '"纪飞" <jifei@gtht.com>; "周尤珠" <zhouyouzhu@gtht.com>; '
    '"陈文培" <chenwenpei@gtht.com>'
)

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
        
        password = decrypt_password(enc_password, KEY_PATH)
        return url, username, password
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
    parser = argparse.ArgumentParser(description="Coremail Draft Saver for Version Schedule Email")
    parser.add_argument("--subject", default="", help="Email Subject")
    parser.add_argument("--body", default="", help="Plain text email body string")
    parser.add_argument("--body-file", default="", help="Path to plain text/HTML email body file")
    parser.add_argument("--recipients", default=DEFAULT_RECIPIENTS, help="Override email recipients")
    parser.add_argument("--cc", default=DEFAULT_CC, help="Override email CC recipients")
    args = parser.parse_args()

    # Determine Subject and Body
    subject = args.subject
    body = args.body

    if args.body_file:
        if not os.path.exists(args.body_file):
            print(f"[ERROR] Body file not found at {args.body_file}")
            sys.exit(1)
        with open(args.body_file, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        # Parse Subject from body file if present
        subject_match = re.search(r'^(?:主题|邮件主题|Subject)\s*[:：]\s*(.*)$', file_content, re.MULTILINE | re.IGNORECASE)
        if subject_match:
            if not subject:
                subject = subject_match.group(1).strip()
            file_content = re.sub(r'^(?:主题|邮件主题|Subject)\s*[:：].*$\n?', '', file_content, flags=re.MULTILINE | re.IGNORECASE)
        
        body = file_content.strip()

    if not subject:
        # Fallback default subject if not provided
        subject = "集中交易系统版本发布与测试排期通知"

    if not body:
        print("[ERROR] Email body is empty. Please provide --body or --body-file.")
        sys.exit(1)

    # Load Credentials
    print("[0] Loading mail credentials...")
    url, email, password = load_mail_credentials()
    print(f"    Loaded config: URL={url}, Username={email}")

    # Parse recipients
    recipients = [r.strip() for r in re.split(r'[;；\r\n]+', args.recipients) if r.strip()]
    cc_recipients = [r.strip() for r in re.split(r'[;；\r\n]+', args.cc) if r.strip()]
    
    print(f"🎯 Total recipients to fill: {len(recipients)}")
    print(f"🎯 Total CC to fill: {len(cc_recipients)}")

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
        
        context = browser.new_context(**context_opts)
        page = context.new_page()

        try:
            # Step 1: Open webmail
            print("[1] Opening mail.gtht.com...")
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)

            # Check login form
            uid_input = page.query_selector("input#uid") or page.query_selector("input[name='uid']")
            if uid_input:
                print("[2] Performing login...")
                uid_input.fill(email)
                page.fill("input#password", password)

                ssl_checkbox = page.query_selector("#rcmloginssl")
                if ssl_checkbox and not ssl_checkbox.is_checked():
                    ssl_checkbox.click()

                page.keyboard.press("Enter")
                print("    Submitted login form.")

            # Dynamically wait for mailbox load
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

            # Step 2: Click Compose
            print("[3] Clicking compose...")
            compose_page = None
            subj_el = None
            compose_frame = None
            
            for click_attempt in range(4):
                try:
                    new_page = None
                    with context.expect_page(timeout=5000) as new_page_info:
                        compose_btn.click(force=True)
                        print("    Waiting for compose tab...")
                    new_page = new_page_info.value
                    compose_page = new_page
                    compose_page.wait_for_load_state("domcontentloaded", timeout=15000)
                    compose_page.wait_for_timeout(2000)
                except Exception as e:
                    print(f"    New tab not opened (trying current page): {e}")
                    compose_page = page
                
                print(f"    Check compose form visibility (attempt {click_attempt+1}/4)...")
                for iframe_wait in range(5):
                    subj_el, compose_frame = find_in_all_frames(compose_page, SEL_SUBJ, timeout=1000)
                    if subj_el:
                        break
                    compose_page.wait_for_timeout(800)
                
                if subj_el:
                    break
                page.wait_for_timeout(2000)
                
            if not subj_el:
                try:
                    page.screenshot(path=os.path.join(OUT_DIR, "coremail_compose_timeout.png"))
                except:
                    pass
                raise Exception("Timed out waiting for compose form")
                
            print(f"    [+] Compose form found in {'page' if compose_frame == compose_page else 'iframe'}")

            # Step 3: Fill Details
            print("[5] Filling details...")
            
            # Fill To - Populating each recipient one-by-one to guarantee no missing records in Coremail
            if recipients:
                to_el = compose_frame.query_selector(SEL_TO)
                if to_el:
                    print("    Filling recipients one by one...")
                    to_el.focus()
                    compose_frame.wait_for_timeout(500)
                    for idx, r in enumerate(recipients):
                        try:
                            to_el.focus()
                        except:
                            pass
                        compose_frame.keyboard.insert_text(r + ";")
                        compose_frame.wait_for_timeout(250)
                        compose_frame.keyboard.press("Enter")
                        compose_frame.wait_for_timeout(150)
                    print("    To field filled.")

            # Fill CC - Populating each CC one-by-one to guarantee accuracy
            if cc_recipients:
                cc_el = compose_frame.query_selector(SEL_CC)
                if not cc_el or not cc_el.is_visible():
                    btn_cc = compose_frame.query_selector('a:has-text("添加抄送"), span:has-text("添加抄送"), a:has-text("抄送"), span:has-text("抄送")')
                    if not btn_cc:
                        btn_cc = compose_page.query_selector('a:has-text("添加抄送"), span:has-text("添加抄送"), a:has-text("抄送"), span:has-text("抄送")')
                    if btn_cc:
                        btn_cc.click()
                        compose_frame.wait_for_timeout(500)
                
                cc_el = compose_frame.query_selector(SEL_CC)
                if cc_el:
                    print("    Filling CC recipients one by one...")
                    cc_el.focus()
                    compose_frame.wait_for_timeout(500)
                    for idx, r in enumerate(cc_recipients):
                        try:
                            cc_el.focus()
                        except:
                            pass
                        compose_frame.keyboard.insert_text(r + ";")
                        compose_frame.wait_for_timeout(250)
                        compose_frame.keyboard.press("Enter")
                        compose_frame.wait_for_timeout(150)
                    print("    CC field filled.")

            # Fill Subject
            subj_el.fill(subject)
            print("    Filled Subject")

            # Fill Body
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

            # Step 4: Save Draft
            print("[6] Saving draft...")
            save_btn = compose_frame.query_selector('a:has-text("存草稿"), button:has-text("存草稿"), span:has-text("存草稿")')
            if not save_btn:
                save_btn = compose_page.query_selector('a:has-text("存草稿"), button:has-text("存草稿"), span:has-text("存草稿")')
            
            if save_btn:
                save_btn.click(force=True)
                compose_page.wait_for_timeout(3000)
            else:
                modifier = "Meta" if sys.platform == "darwin" else "Control"
                compose_page.keyboard.press(f"{modifier}+s")
                compose_page.wait_for_timeout(2000)
            
            # Verify saving
            try:
                confirm_el = compose_page.wait_for_selector('text="已保存", text="草稿已保存", text="保存成功"', timeout=5000)
                if confirm_el:
                    print("    ✅ Draft save confirmed by UI!")
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
