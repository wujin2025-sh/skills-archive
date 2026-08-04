#!/usr/bin/env python3
"""
腾讯会议录制激活脚本 (v1.0)

当 tmeet record list 返回空时，自动打开腾讯会议 Web 端录制页面，
找到对应会议点击"前往查看"触发转写生成，然后轮询 API 直到数据可用。

用法:
  /usr/local/bin/python3 activate_recording.py \
    --meeting-code "547572839" \
    --meeting-subject "2026ETF组合优惠利率需求讨论" \
    [--cookies-file mt_cookies.json] \
    [--no-headless] \
    [--timeout 120]

原理:
  腾讯会议的云录制转写是"按需生成"的 —— 会议结束后转写文件不会自动生成，
  需要用户在 App 或 Web 端点击"前往查看"后服务端才开始处理。
  本脚本模拟这一操作，自动触发转写生成。
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent

# ────────────────────────────────────────────────
# 1. tmeet CLI 封装
# ────────────────────────────────────────────────
def get_tmeet_bin() -> str:
    import shutil
    bin_path = shutil.which("tmeet")
    if bin_path:
        return bin_path
    fallback = os.path.expanduser("~/.workbuddy/binaries/node/cli-connector-packages/bin/tmeet")
    if os.path.exists(fallback):
        return fallback
    return "tmeet"

def tmeet_record_list(meeting_code: str) -> dict:
    """调用 tmeet CLI 查询录制列表"""
    tmeet_bin = get_tmeet_bin()
    cmd = [tmeet_bin, "record", "list", "--meeting-code", meeting_code, "--compact"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip())
    except Exception as e:
        print(f"  [W] tmeet record list 执行异常: {e}")
    return {"data": {"total_count": 0, "record_meetings": []}}



def poll_record_list(meeting_code: str, max_wait: int = 90, interval: int = 5) -> dict:
    """轮询录制列表，直到有数据或超时"""
    print(f"  [I] 轮询录制列表（最多 {max_wait}s，间隔 {interval}s）...")
    start = time.time()
    while time.time() - start < max_wait:
        result = tmeet_record_list(meeting_code)
        total = result.get("data", {}).get("total_count", 0)
        if total > 0:
            print(f"  [✓] 录制数据已生成！total_count={total}")
            return result
        elapsed = int(time.time() - start)
        print(f"  [.] 等待中... ({elapsed}s / {max_wait}s)")
        time.sleep(interval)

    print(f"  [✗] 轮询超时（{max_wait}s），录制数据仍未生成")
    return {"data": {"total_count": 0, "record_meetings": []}}


# ────────────────────────────────────────────────
# 2. Playwright 录制激活
# ────────────────────────────────────────────────
def activate_recording_playwright(
    meeting_code: str,
    meeting_subject: str = "",
    cookies_file: str = "",
    headless: bool = True,
    timeout: int = 120,
) -> bool:
    """使用 Playwright 打开腾讯会议 Web 端，触发录制生成"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] Playwright 未安装，请运行: pip install playwright && playwright install chromium")
        return False

    storage_path = os.path.expanduser("~/.workbuddy/.meeting_storage_state.json")

    with sync_playwright() as p:
        # 启动浏览器（优先 Chrome，回退 Chromium）
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ]
        try:
            browser = p.chromium.launch(
                channel="chrome",
                headless=headless,
                args=launch_args,
            )
        except Exception:
            print("  [I] Chrome 未找到，使用 Chromium")
            browser = p.chromium.launch(headless=headless, args=launch_args)

        # 复用登录态
        context_kwargs = {}
        if os.path.exists(storage_path):
            context_kwargs["storage_state"] = storage_path
            print(f"  [I] 复用登录态: {storage_path}")

        # 加载 cookies（如有）
        if cookies_file and os.path.exists(cookies_file):
            try:
                with open(cookies_file, "r") as f:
                    cookies = json.load(f)
                context_kwargs.setdefault("storage_state", {})
                # cookies 会在 context 创建后添加
                print(f"  [I] 加载 cookies: {cookies_file} ({len(cookies)} 条)")
            except Exception as e:
                print(f"  [W] cookies 加载失败: {e}")
                cookies = []
        else:
            cookies = []

        context = browser.new_context(**context_kwargs)

        # 添加 cookies
        if cookies:
            try:
                context.add_cookies(cookies)
            except Exception as e:
                print(f"  [W] cookies 添加失败: {e}")

        page = context.new_page()

        # ── 拦截网络请求，捕获关键 API ──
        captured_apis = []
        def on_request(request):
            url = request.url
            if "meeting.tencent.com" in url and any(k in url for k in ["/api/", "/wapi/", "/v1/"]):
                captured_apis.append({
                    "url": url,
                    "method": request.method,
                    "post_data": request.post_data,
                })

        page.on("request", on_request)

        # ── 导航到录制管理页 ──
        print("  [I] 打开腾讯会议录制管理页...")
        try:
            page.goto(
                "https://meeting.tencent.com/user-center/meeting-record",
                wait_until="networkidle",
                timeout=30000,
            )
        except Exception as e:
            print(f"  [W] 页面加载超时: {e}")
            page.goto("https://meeting.tencent.com/user-center/meeting-record", timeout=60000)

        current_url = page.url
        print(f"  [I] 当前 URL: {current_url}")

        # 检查是否需要登录
        if "login" in current_url.lower() or "passport" in current_url.lower():
            print("  [!] 需要登录腾讯会议 Web 端")
            print("  [I] 请在浏览器窗口中手动完成登录（企业微信扫码）...")
            if headless:
                print("  [W] headless 模式下无法手动登录，切换到有头模式")
                browser.close()
                return activate_recording_playwright(
                    meeting_code, meeting_subject, cookies_file,
                    headless=False, timeout=timeout,
                )

            # 等待用户手动登录
            try:
                page.wait_for_url("**/meeting-record**", timeout=120000)
                print("  [✓] 登录成功！")
                # 保存登录态
                context.storage_state(path=storage_path)
                print(f"  [I] 登录态已保存: {storage_path}")
            except Exception:
                print("  [✗] 登录超时")
                page.screenshot(path=str(SCRIPT_DIR / "debug_login_timeout.png"))
                browser.close()
                return False

        # ── 在录制列表中查找目标会议 ──
        print(f"  [I] 查找会议: {meeting_subject or meeting_code}")

        # 先截图看看页面结构
        page.screenshot(path=str(SCRIPT_DIR / "debug_record_page.png"))

        # 策略 1: 尝试搜索功能
        search_input = None
        for selector in [
            'input[placeholder*="搜索"]',
            'input[placeholder*="会议"]',
            'input[type="search"]',
            '.search-input input',
            '.search-box input',
        ]:
            search_input = page.query_selector(selector)
            if search_input:
                print(f"  [I] 找到搜索框: {selector}")
                break

        if search_input:
            search_input.fill(meeting_code)
            search_input.press("Enter")
            page.wait_for_timeout(2000)
            print(f"  [I] 已搜索会议号: {meeting_code}")

        # 策略 2: 尝试直接通过 URL 筛选
        # 腾讯会议录制页面可能支持 URL 参数筛选

        # ── 查找并点击"前往查看"按钮 ──
        clicked = False
        click_selectors = [
            'text=前往查看',
            'text=查看录制',
            'text=查看',
            'a:has-text("前往查看")',
            'button:has-text("前往查看")',
            '.record-item:has-text("' + (meeting_subject or meeting_code) + '") a',
            '.record-item:has-text("' + (meeting_subject or meeting_code) + '") button',
        ]

        # 如果有会议主题，先尝试定位包含该主题的条目
        if meeting_subject:
            # 尝试找到包含会议主题的行
            item_selectors = [
                f'tr:has-text("{meeting_subject}")',
                f'.record-item:has-text("{meeting_subject}")',
                f'[class*="record"]:has-text("{meeting_subject}")',
                f'[class*="meeting"]:has-text("{meeting_subject}")',
                f'div:has-text("{meeting_subject}")',
            ]
            for sel in item_selectors:
                try:
                    item = page.query_selector(sel)
                    if item:
                        print(f"  [I] 找到会议条目: {sel}")
                        # 在该条目内查找"前往查看"按钮
                        for btn_sel in ['text=前往查看', 'text=查看', 'a', 'button']:
                            btn = item.query_selector(btn_sel)
                            if btn:
                                btn.click()
                                clicked = True
                                print(f"  [✓] 已点击: {btn_sel}")
                                break
                        if clicked:
                            break
                except Exception:
                    continue

        # 如果没有通过主题定位，直接查找"前往查看"按钮
        if not clicked:
            for sel in click_selectors:
                try:
                    btn = page.query_selector(sel)
                    if btn:
                        btn.click()
                        clicked = True
                        print(f"  [✓] 已点击: {sel}")
                        break
                except Exception:
                    continue

        if not clicked:
            print("  [W] 未找到'前往查看'按钮，尝试点击第一条录制条目...")
            # 尝试点击第一个录制条目
            first_item_selectors = [
                '.record-item:first-child a',
                '.record-item:first-child button',
                'tr:first-child a',
                'a[href*="record"]',
            ]
            for sel in first_item_selectors:
                try:
                    btn = page.query_selector(sel)
                    if btn:
                        btn.click()
                        clicked = True
                        print(f"  [✓] 已点击首个条目: {sel}")
                        break
                except Exception:
                    continue

        if not clicked:
            print("  [✗] 未能点击任何录制条目")
            page.screenshot(path=str(SCRIPT_DIR / "debug_no_click_target.png"))
            # 打印页面内容帮助调试
            print(f"  [D] 页面文本（前 500 字）: {page.inner_text('body')[:500]}")
            browser.close()
            return False

        # ── 等待页面加载（触发转写生成） ──
        print("  [I] 等待转写生成...")
        page.wait_for_timeout(3000)

        # 截图确认
        page.screenshot(path=str(SCRIPT_DIR / "debug_after_click.png"))

        # 保存登录态
        try:
            context.storage_state(path=storage_path)
        except Exception:
            pass

        # 打印捕获的 API（帮助后续优化）
        if captured_apis:
            print(f"  [D] 捕获到 {len(captured_apis)} 个 API 请求:")
            for api in captured_apis[-10:]:  # 只打印最后10个
                print(f"    {api['method']} {api['url'][:120]}")

        browser.close()

    return clicked


# ────────────────────────────────────────────────
# 3. 主流程
# ────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="腾讯会议录制激活脚本")
    parser.add_argument("--meeting-code", required=True, help="会议号（9位数字）")
    parser.add_argument("--meeting-subject", default="", help="会议主题（用于定位）")
    parser.add_argument("--cookies-file", default="", help="cookies JSON 文件路径")
    parser.add_argument("--no-headless", action="store_true", help="显示浏览器窗口")
    parser.add_argument("--timeout", type=int, default=120, help="总超时（秒）")
    parser.add_argument("--skip-playwright", action="store_true", help="跳过 Playwright，仅轮询")
    args = parser.parse_args()

    print(f"=== 录制激活: 会议号 {args.meeting_code} ===")

    # Step 1: 先检查录制是否已存在
    result = tmeet_record_list(args.meeting_code)
    total = result.get("data", {}).get("total_count", 0)
    if total > 0:
        print(f"  [✓] 录制数据已存在（total_count={total}），无需激活")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print("  [I] 录制数据为空，开始激活流程...")

    if args.skip_playwright:
        print("  [I] 跳过 Playwright，直接轮询...")
    else:
        # Step 2: Playwright 触发激活
        success = activate_recording_playwright(
            meeting_code=args.meeting_code,
            meeting_subject=args.meeting_subject,
            cookies_file=args.cookies_file,
            headless=not args.no_headless,
            timeout=args.timeout,
        )
        if not success:
            print("  [✗] Playwright 激活失败")
            return 1

    # Step 3: 轮询等待录制生成
    remaining_timeout = max(30, args.timeout - 30)
    final_result = poll_record_list(args.meeting_code, max_wait=remaining_timeout)

    if final_result.get("data", {}).get("total_count", 0) > 0:
        print("\n=== 激活成功！===")
        print(json.dumps(final_result, ensure_ascii=False, indent=2))
        return 0
    else:
        print("\n=== 激活失败：录制数据仍未生成 ===")
        print("  可能原因：")
        print("  1. 该会议确实没有录制/转写")
        print("  2. 转写生成时间较长，请稍后重试")
        print("  3. Web 端页面结构变化，需更新脚本")
        return 1


if __name__ == "__main__":
    sys.exit(main())
