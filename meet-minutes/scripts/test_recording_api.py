#!/usr/bin/env python3
"""
腾讯会议录制激活 — API 直接触发方案

经过分析，Web 端是 SPA 应用，hash 路由无法通过 Playwright 可靠触发。
替代方案：
1. 直接调用腾讯会议 Web API 触发录制转写生成
2. 发现关键 API：/wemeet-tapi/v2/wemeet-cloudrecording-webapi/

下一步：分析 tmeet CLI 的 OAuth token，尝试直接调用 Web API
"""
import json, os, re, subprocess, time, urllib.request, urllib.parse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

def get_tmeet_token():
    """从 tmeet 配置中提取 OAuth token"""
    # tmeet 的 token 存储在 ~/.config/tmeet/ 或类似位置
    # 尝试找到 token 文件
    token_paths = [
        os.path.expanduser("~/.config/tmeet/token.json"),
        os.path.expanduser("~/.tmeet/token.json"),
        os.path.expanduser("~/.config/tmeet/config.json"),
    ]
    for p in token_paths:
        if os.path.exists(p):
            with open(p) as f:
                data = json.load(f)
            # 查找 access_token
            if "access_token" in data:
                return data["access_token"]
            if "token" in data:
                return data["token"]
    return None


def get_tmeet_cookies():
    """从 mt_cookies.json 获取 cookies"""
    cookies_file = SCRIPT_DIR / "mt_cookies.json"
    if cookies_file.exists():
        with open(cookies_file) as f:
            return json.load(f)
    return []


def try_trigger_recording_api(meeting_code: str, meeting_id: str = ""):
    """尝试通过 Web API 触发录制生成"""
    print(f"[I] 尝试通过 API 触发录制生成: meeting_code={meeting_code}")
    
    # 获取 cookies
    cookies = get_tmeet_cookies()
    cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
    
    # 构建请求头
    headers = {
        "Cookie": cookie_str,
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    # 尝试调用录制列表 API（使用 Web API，不是 OAuth API）
    # 这个 API 可能会触发录制生成
    base_url = "https://meeting.tencent.com"
    
    # 尝试 API 1: 录制列表
    api_urls = [
        f"{base_url}/wemeet-tapi/v2/wemeet-cloudrecording-webapi/v1/records?meeting_code={meeting_code}",
        f"{base_url}/wemeet-tapi/v2/wemeet-cloudrecording-webapi/v1/records?meeting_id={meeting_id}",
        f"{base_url}/wemeet-webapi/v2/record/list?meeting_code={meeting_code}",
    ]
    
    for url in api_urls:
        try:
            print(f"  [.] GET {url[:100]}")
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode()
                print(f"  [✓] 响应: {body[:200]}")
        except Exception as e:
            print(f"  [✗] 失败: {e}")
    
    # 尝试 POST API：触发转写生成
    post_apis = [
        {
            "url": f"{base_url}/wemeet-tapi/v2/wemeet-cloudrecording-webapi/v1/record/trigger-transcode",
            "data": {"meeting_code": meeting_code}
        },
        {
            "url": f"{base_url}/wemeet-tapi/v2/record/transcript/generate",
            "data": {"meeting_code": meeting_code}
        },
    ]
    
    for api in post_apis:
        try:
            print(f"  [.] POST {api['url'][:100]}")
            data = json.dumps(api["data"]).encode()
            req = urllib.request.Request(api["url"], data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode()
                print(f"  [✓] 响应: {body[:200]}")
        except Exception as e:
            print(f"  [✗] 失败: {e}")


def try_direct_api_call(meeting_code: str):
    """
    使用 tmeet 的 OAuth token 直接调用腾讯会议 REST API
    关键发现：tmeet 使用 OAuth 2.0，token 可以通过 `tmeet auth status` 获取
    """
    print(f"\n[I] 获取 tmeet OAuth token...")
    try:
        result = subprocess.run(["tmeet", "auth", "status", "--format", "json"],
                                capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            token = data.get("access_token") or data.get("token")
            print(f"  [✓] Token 获取成功: {token[:20]}..." if token else "  [✗] Token 为空")
        else:
            print(f"  [✗] tmeet auth status 失败: {result.stderr}")
    except Exception as e:
        print(f"  [✗] 获取 token 异常: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting-code", default="547572839")
    parser.add_argument("--meeting-id", default="")
    args = parser.parse_args()
    
    # 先检查 tmeet 是否能获取数据
    print("=== 检查 tmeet CLI 访问权限 ===")
    result = subprocess.run(
        ["tmeet", "record", "list", "--meeting-code", args.meeting_code, "--compact"],
        capture_output=True, text=True, timeout=30
    )
    print(f"tmeet record list: {result.stdout[:200]}")
    
    if "total_count\": 0" in result.stdout:
        print("\n[W] tmeet 返回空，需要触发录制生成")
        try_trigger_recording_api(args.meeting_code, args.meeting_id)
        try_direct_api_call(args.meeting_code)
    else:
        print("\n[✓] tmeet 已有数据，无需触发")


if __name__ == "__main__":
    main()
