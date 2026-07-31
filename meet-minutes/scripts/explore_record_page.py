#!/usr/bin/env python3
"""
腾讯会议录制页面探索脚本 v3 — 深度分析录制页面 API
目标：找到录制列表 API 和"前往查看"触发的 API
"""
import json, os, time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

def explore():
    from playwright.sync_api import sync_playwright
    
    storage_path = os.path.expanduser("~/.workbuddy/.meeting_storage_state.json")
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=False,
                                        args=["--disable-blink-features=AutomationControlled"])
        except:
            browser = p.chromium.launch(headless=False)
        
        ctx_kwargs = {}
        if os.path.exists(storage_path):
            ctx_kwargs["storage_state"] = storage_path
        
        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()
        
        # 捕获所有 API 请求和响应
        api_log = []
        def on_request(req):
            url = req.url
            if "meeting.tencent.com" not in url:
                return
            if any(x in url for x in ["aegis.qq", "google-analytics", ".js", ".css", ".png", ".svg", ".woff", ".ico", "cdn.meeting"]):
                return
            api_log.append({"type": "request", "url": url, "method": req.method, "post_data": req.post_data})
        
        def on_response(resp):
            url = resp.url
            if "meeting.tencent.com" not in url:
                return
            if any(x in url for x in ["aegis.qq", "google-analytics", ".js", ".css", ".png", ".svg", ".woff", ".ico", "cdn.meeting"]):
                return
            try:
                ct = resp.headers.get("content-type", "")
                body = None
                if "json" in ct:
                    body = resp.json()
                entry = {
                    "type": "response", 
                    "url": url, 
                    "method": resp.request.method, 
                    "status": resp.status,
                    "body": body  # 保存完整响应体
                }
                api_log.append(entry)
            except:
                api_log.append({"type": "response", "url": url, "method": resp.request.method, "status": resp.status})
        
        page.on("request", on_request)
        page.on("response", on_response)
        
        print("[I] 打开腾讯会议主页...")
        page.goto("https://meeting.tencent.com/", wait_until="networkidle", timeout=30000)
        
        current_url = page.url
        print(f"[I] 当前 URL: {current_url}")
        
        if "login" in current_url.lower() or "passport" in current_url.lower():
            print("[!] 需要登录！请在浏览器窗口中完成登录...")
            page.wait_for_url("**/meeting.tencent.com/**", timeout=180000)
            print("[✓] 登录成功！")
            context.storage_state(path=storage_path)
        
        page.wait_for_timeout(3000)
        
        # 尝试通过 URL hash 路由到录制页面
        print("[I] 导航到录制页面...")
        page.evaluate("() => { window.location.hash = '#/user-center/my-record'; }")
        page.wait_for_timeout(5000)
        
        # 截图
        page.screenshot(path=str(SCRIPT_DIR / "explore_v3_after_nav.png"))
        print(f"[I] 截图保存: explore_v3_after_nav.png")
        
        # 等待录制列表加载
        print("[I] 等待录制列表加载...")
        page.wait_for_timeout(5000)
        
        # 再次截图
        page.screenshot(path=str(SCRIPT_DIR / "explore_v3_after_load.png"))
        
        # 分析页面内容
        body_text = page.inner_text("body")
        print(f"\n=== 页面内容（前 2000 字）===")
        print(body_text[:2000])
        
        # 查找录制列表
        print("\n=== 查找录制列表 ===")
        # 尝试各种选择器
        for sel in [
            '[class*="record"]', '[class*="cloud"]', '[class*="meeting-item"]',
            '[class*="list-item"]', '[class*="card"]', 'table', 'tbody tr',
            'a[href*="record"]', 'button:has-text("查看")', 'button:has-text("前往")',
        ]:
            try:
                els = page.query_selector_all(sel)
                if els and len(els) > 1:  # 至少 2 个才打印
                    print(f"  {sel}: {len(els)} 个元素")
                    for i, el in enumerate(els[:5]):
                        text = el.inner_text()[:150].replace('\n', ' | ')
                        print(f"    [{i}] {text}")
            except:
                pass
        
        # 打印录制相关 API
        print(f"\n=== 录制相关 API 调用 ({len([x for x in api_log if 'record' in x.get('url','').lower() or 'cloud' in x.get('url','').lower()])}) ===")
        for entry in api_log:
            url = entry.get("url", "")
            if "record" in url.lower() or "cloud" in url.lower() or "transcode" in url.lower() or "transcript" in url.lower():
                print(f"\n  ★ {entry['method']} {url}")
                body = entry.get("body")
                if body and isinstance(body, dict):
                    print(f"    Response: {json.dumps(body, ensure_ascii=False)[:500]}")
        
        # 打印所有 API（分类）
        print(f"\n=== 所有 API ({len(api_log)}) ===")
        for entry in api_log:
            url = entry.get("url", "")
            method = entry.get("method", "")
            status = entry.get("status", "")
            url_short = url[url.find("meeting.tencent.com") + 19:] if "meeting.tencent.com" in url else url[:100]
            print(f"  {method} {status} ...{url_short}")
        
        # 保存完整 API 日志
        log_path = SCRIPT_DIR / "api_log.json"
        with open(log_path, "w") as f:
            json.dump(api_log, f, ensure_ascii=False, indent=2)
        print(f"\n[I] 完整 API 日志已保存: {log_path}")
        
        # 浏览器保持打开
        print("\n[I] 浏览器将保持打开 30 秒供手动检查...")
        page.wait_for_timeout(30000)
        
        context.storage_state(path=storage_path)
        browser.close()

if __name__ == "__main__":
    explore()
