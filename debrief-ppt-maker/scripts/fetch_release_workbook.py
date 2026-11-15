# -*- coding: utf-8 -*-
"""下载全连接文档中心《各系统发版汇总》Excel（02 模块「版本集成发布情况」页数据源）。

登录凭据复用 ~/.workbuddy/skills/meet-minutes/config.json 的 mail.password（Fernet 加密），
密钥 ~/.workbuddy/.meeting_skill_key，用户名默认 wujin。会话保存在 .wps_release_state.json，
**该文件含内网凭据，权限 600，禁止外传或提交仓库**。

用法：
  python fetch_release_workbook.py                      # 复用会话，失败时自动重新登录
  python fetch_release_workbook.py --force-login       # 强制重新登录
  python fetch_release_workbook.py --out <xlsx路径>     # 指定保存路径
"""
import os
import sys
import json
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(SCRIPT_DIR, "quarter_config.json")


def decrypt_password(cfg, key_path):
    from cryptography.fernet import Fernet
    enc = cfg["mail"]["password"]
    if not str(enc).startswith("ENC:"):
        return enc
    key = open(key_path, "rb").read().strip()
    return Fernet(key).decrypt(enc[4:].encode()).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--out", default=None)
    ap.add_argument("--force-login", action="store_true")
    ap.add_argument("--user", default="wujin")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    cfg = json.load(open(args.config, encoding="utf-8"))
    doc = cfg["release_doc"]
    paths = cfg["paths"]
    out = args.out or paths["xlsx"]
    state = paths["wps_state"]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 950},
                                      accept_downloads=True,
                                      **({"storage_state": state}
                                         if os.path.exists(state) and not args.force_login else {}))
        page = context.new_page()

        def download_once():
            page.goto(doc["drive_url"], wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4000)
            if "login" in page.url.lower():
                raise RuntimeError("SESSION_EXPIRED")
            loc = page.locator("text=/%s/" % doc["title"]).first
            loc.wait_for(state="visible", timeout=15000)
            loc.click(button="right")
            page.wait_for_timeout(1200)
            item = page.locator("text=/^Download$|下载/").first
            item.wait_for(state="visible", timeout=8000)
            with page.expect_download(timeout=30000) as info:
                item.click()
            info.value.save_as(out)
            return os.path.getsize(out)

        try:
            size = download_once()
            print("复用会话下载成功：", out, size, "bytes")
        except Exception as e:
            if "SESSION_EXPIRED" not in str(e) and not args.force_login:
                # 也可能是菜单/文件列表变化，先尝试重新登录一次
                print("[warn] 首次下载失败（%s），尝试重新登录" % str(e)[:100])
            pwd = decrypt_password(json.load(open(paths["mail_config"], encoding="utf-8")),
                                   paths["mail_key"])
            page.goto(doc["url"], wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1500)
            page.fill("input[placeholder*='Employee ID']", args.user)
            page.fill("input[placeholder='Password']", pwd)
            page.click("button:has-text('Login')")
            page.wait_for_timeout(6000)
            if "login" in page.url.lower():
                raise RuntimeError("内网登录失败，请检查凭据或手动登录；URL=" + page.url)
            context.storage_state(path=state)
            os.chmod(state, 0o600)
            print("登录成功，会话已保存（权限 600）：", state)
            size = download_once()
            print("重新登录后下载成功：", out, size, "bytes")

        browser.close()
    return 0 if os.path.getsize(out) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
