import sys
import os
import time
from playwright.sync_api import sync_playwright

sys.path.append("/Volumes/Macintosh HD_Data/WorkBuddy/邮件发送")
try:
    from save_this_draft import load_mail_credentials
    url_mail, email, password = load_mail_credentials()
    username = email.split("@")[0] if "@" in email else email
except Exception as e:
    username = "wujin"
    password = ""

def main():
    target_url = "https://www.gtht.com.cn/jswps/kdrive/latest"
    cache_dir = "/Users/wujin/.gemini/antigravity/state/bcp_tracker"
    os.makedirs(cache_dir, exist_ok=True)
    
    state_path = os.path.join(cache_dir, "wps_state.json")
    out_xlsx = os.path.join(cache_dir, "downloaded_workbook.xlsx")
    
    start_time = time.time()
    print("Launching Playwright...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # Load storage state if exists to reuse session cookies/localStorage
        kwargs = {}
        if os.path.exists(state_path):
            print("Reusing existing session storage state...")
            kwargs["storage_state"] = state_path
            
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            **kwargs
        )
        page = context.new_page()
        
        # Go to dashboard
        print("Navigating to dashboard...")
        page.goto(target_url, wait_until="load")
        
        # Check if we need to log in
        try:
            # Short timeout to detect login form
            page.wait_for_selector("input[type='password']", timeout=2000)
            print("Session expired or not logged in. Performing login...")
            user_sel = "input[placeholder*='Employee ID'], input[placeholder*='OA'], input[type='text']"
            pass_sel = "input[type='password']"
            page.fill(user_sel, username)
            page.fill(pass_sel, password)
            
            with page.expect_navigation(timeout=10000):
                page.click("button:has-text('Login'), button:has-text('登录'), button")
                
            # Save new storage state
            context.storage_state(path=state_path)
            print("New session state saved.")
        except Exception:
            print("Already logged in or login form not detected. Continuing...")
            
        # Wait for target file row to render
        print("Waiting for file element to render...")
        file_locator = page.locator("text=/集中交易历史数据/").first
        file_locator.wait_for(state="visible", timeout=10000)
        
        # Grace delay to ensure JS events are attached
        page.wait_for_timeout(1000)
        
        # Right click to trigger context menu
        print("Right-clicking file row...")
        file_locator.click(button="right")
        
        # Wait for download option
        print("Waiting for download menu option...")
        download_locator = page.locator("text=/Download|下载/").first
        download_locator.wait_for(state="visible", timeout=5000)
        
        # Click download and save
        print("Triggering download...")
        with page.expect_download(timeout=10000) as download_info:
            download_locator.click()
            
        download = download_info.value
        download.save_as(out_xlsx)
        
        elapsed = time.time() - start_time
        print(f"✅ Excel workbook downloaded in {elapsed:.2f} seconds!")
        print(f"File size: {os.path.getsize(out_xlsx)} bytes")
        
        browser.close()

if __name__ == "__main__":
    main()
