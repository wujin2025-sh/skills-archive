#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
session.py — 科技平台共享会话管理（性能优化核心）

三大能力：
1. **JWT Token 持久化**：登录一次（Playwright），token 存入 session.json，8h 内复用。
   → 后续 fetch/split/submit 全部走 requests 直调 API，秒级返回，不再每次启动浏览器。
2. **API 封装**：api_get/api_post 自动带 `token` 请求头，401 时自动重登重试一次。
3. **浏览器会话复用**：open_page() 用持久化 profile（.browser_profile/），
   二次打开页面直接跳过登录表单（实测 ~1.6s 完成认证）。

用法：
    import session
    s = session.get_session()
    data = s.post("/demand-service/demandsub/queryDemandsubInfo", {"demandId": "R..."})
    page = session.open_page()   # 供 submit_review / split_story 使用
"""
import json
import time
import base64
import threading
from pathlib import Path

import requests

import config

CFG_PATH = config.get_config_file()   # 兼容旧引用；凭据统一走 config.load_config()
SESSION_FILE = config.get_state_file("session.json")
PROFILE_DIR = config.get_state_dir() / ".browser_profile"

API = config.get_api_base()

# 客户端头（模拟前端 SPA 调用）
CLIENT_HEADERS = {
    "source": "kjpt",
    "content-type": "application/json",
    "accept": "application/json",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "origin": config.get_origin(),
}

_lock = threading.Lock()


def _load_cfg() -> dict:
    return config.load_config()


def _decode_jwt_exp(token: str) -> float:
    """从 JWT payload 解析 exp 过期时间戳（秒）"""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return float(payload.get("exp", 0))
    except Exception:
        return 0


def _read_session() -> dict:
    if SESSION_FILE.exists():
        try:
            return json.loads(SESSION_FILE.read_text())
        except Exception:
            pass
    return {}


def _write_session(data: dict):
    tmp = SESSION_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(SESSION_FILE)


def token_is_valid(token: str) -> bool:
    if not token:
        return False
    exp = _decode_jwt_exp(token)
    if exp and exp > time.time() + 300:  # 提前 5 分钟视为过期
        return True
    return False


# ---------------------------------------------------------------------------
# 登录（仅首次 / token 失效时调用）
# ---------------------------------------------------------------------------
def _playwright_login(profile=False) -> dict:
    """用 Playwright 执行登录，返回 {token, user_info}。profile=True 时用持久化目录（供 open_page 复用）。"""
    from playwright.async_api import async_playwright

    cfg = _load_cfg()

    async def _do():
        async with async_playwright() as p:
            if profile:
                ctx = await p.chromium.launch_persistent_context(
                    str(PROFILE_DIR), headless=True, viewport={"width": 1920, "height": 1080})
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            else:
                ctx = None
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1920, "height": 1080})

            await page.goto(cfg["login_url"], wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(400)
            await page.fill('#workno', cfg["username"])
            await page.fill('#password', cfg["password"])
            await page.click('button:has-text("Submit")')
            # 等待登录完成（token 写入 localStorage 或跳转）
            token = ""
            for _ in range(20):
                await page.wait_for_timeout(500)
                try:
                    token = await page.evaluate('localStorage.getItem("GTJA_TOKEN") || ""')
                except Exception:
                    token = ""
                if token:
                    break
            user_info = None
            if token:
                try:
                    user_info = await page.evaluate('localStorage.getItem("userInfo")')
                    if user_info:
                        user_info = json.loads(user_info)
                except Exception:
                    pass

            if profile:
                await ctx.close()
            else:
                await browser.close()
            return token, user_info

    import asyncio
    token, user_info = asyncio.run(_do())
    if not token:
        raise RuntimeError("登录失败：未获取到 GTJA_TOKEN")
    return {"token": token, "user_info": user_info, "fetched_at": int(time.time())}


# ---------------------------------------------------------------------------
# 对外：获取有效会话
# ---------------------------------------------------------------------------
def get_session(force=False) -> dict:
    """返回 {token, user_info, fetched_at, expires_at}，token 失效时自动重登"""
    with _lock:
        sess = _read_session()
        token = sess.get("token", "")
        if not force and token_is_valid(token):
            sess["expires_at"] = _decode_jwt_exp(token)
            return sess

        # 重登（非 profile，纯 API 用）
        print("[session] token 失效，重新登录...", flush=True)
        fresh = _playwright_login(profile=False)
        fresh["expires_at"] = _decode_jwt_exp(fresh["token"])
        _write_session(fresh)
        return fresh


def api_post(path: str, json_body: dict = None, timeout: int = 20) -> dict:
    """POST API，返回 data 字段；401 自动重登重试一次"""
    sess = get_session()
    headers = dict(CLIENT_HEADERS, token=sess["token"])
    url = f"{API}{path}"
    for attempt in range(2):
        r = requests.post(url, json=json_body or {}, headers=headers, timeout=timeout)
        if r.status_code == 401 and attempt == 0:
            sess = get_session(force=True)
            headers = dict(CLIENT_HEADERS, token=sess["token"])
            continue
        r.raise_for_status()
        j = r.json()
        if j.get("code") not in (200, 0):
            raise RuntimeError(f"API 错误 {path}: {j.get('msg', j)}")
        return j.get("data")


def api_get(path: str, params: dict = None, timeout: int = 20) -> dict:
    """GET API，返回 data 字段；401 自动重登重试一次"""
    sess = get_session()
    headers = dict(CLIENT_HEADERS, token=sess["token"])
    url = f"{API}{path}"
    for attempt in range(2):
        r = requests.get(url, params=params or {}, headers=headers, timeout=timeout)
        if r.status_code == 401 and attempt == 0:
            sess = get_session(force=True)
            headers = dict(CLIENT_HEADERS, token=sess["token"])
            continue
        r.raise_for_status()
        j = r.json()
        if j.get("code") not in (200, 0):
            raise RuntimeError(f"API 错误 {path}: {j.get('msg', j)}")
        return j.get("data")


def api_download(url: str, fpath: Path, timeout: int = 30) -> bool:
    """带 token 下载文件（图片/附件），成功返回 True"""
    ok, _ = api_download_ext(url, fpath, timeout)
    return ok


def api_download_ext(url: str, fpath: Path, timeout: int = 30):
    """带 token 下载，返回 (ok: bool, content_type: str)"""
    sess = get_session()
    headers = {"token": sess["token"], "user-agent": CLIENT_HEADERS["user-agent"]}
    for attempt in range(2):
        r = requests.get(url, headers=headers, timeout=timeout, stream=True)
        if r.status_code == 401 and attempt == 0:
            sess = get_session(force=True)
            headers = {"token": sess["token"], "user-agent": CLIENT_HEADERS["user-agent"]}
            continue
        if r.status_code == 200:
            fpath.parent.mkdir(parents=True, exist_ok=True)
            with open(fpath, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
            return True, r.headers.get("content-type", "")
        return False, ""
    return False, ""


# ---------------------------------------------------------------------------
# 对外：浏览器页面（submit_review / split_story 用）
# ---------------------------------------------------------------------------
async def open_page_direct(url: str, timeout: int = 45000):
    """直开目标 URL（不再先 goto login_url），仅被重定向到登录页才登录。

    - 二次运行：profile 里已有 GTJA_TOKEN → 直开目标页（~1.6s 认证，省去 login_url 往返）。
    - 首次 / token 过期：被重定向到登录页时自动走登录表单，再回目标页。
    - 返回 (page, context, playwright)，调用方用 close_page 释放。
    """
    from playwright.async_api import async_playwright

    cfg = _load_cfg()
    p = await async_playwright().start()
    ctx = await p.chromium.launch_persistent_context(
        str(PROFILE_DIR), headless=True, viewport={"width": 1920, "height": 1400})
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    except Exception:
        pass
    if await _is_login_page(page):
        await _browser_login(page, cfg)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        except Exception:
            pass
    return page, ctx, p


async def _is_login_page(page) -> bool:
    """判断页面是否处于登录/未认证状态"""
    try:
        if await page.query_selector('#password, input[type="password"]'):
            return True
        u = page.url.lower()
        if any(k in u for k in ("login", "sso", "auth")):
            return True
    except Exception:
        pass
    return False


async def _browser_login(page, cfg: dict):
    """在登录页用凭据登录，并刷新本地 session 缓存"""
    print("[session] 浏览器会话过期，执行登录...", flush=True)
    try:
        await page.wait_for_selector('#workno, #password', timeout=10000)
    except Exception:
        pass
    await page.fill('#workno', cfg["username"])
    await page.fill('#password', cfg["password"])
    await page.click('button:has-text("Submit")')
    token = ""
    for _ in range(20):
        await page.wait_for_timeout(500)
        try:
            token = await page.evaluate('localStorage.getItem("GTJA_TOKEN") || ""')
        except Exception:
            token = ""
        if token:
            break
    if token:
        try:
            ui = await page.evaluate('localStorage.getItem("userInfo")')
            fresh = {"token": token, "user_info": json.loads(ui) if ui else None,
                     "fetched_at": int(time.time()), "expires_at": _decode_jwt_exp(token)}
            _write_session(fresh)
        except Exception:
            pass


async def wait_for_condition(page, js_fn: str, timeout: int = 10000,
                             interval: int = 300, desc: str = ""):
    """条件等待：轮询执行 JS 表达式，返回 truthy 即成功；超时返回 False（不抛异常）。

    js_fn 形如 "() => document.querySelector('.ant-modal-content') !== null"
    """
    import asyncio
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            if await page.evaluate(js_fn):
                return True
        except Exception:
            pass
        await page.wait_for_timeout(interval)
    if desc:
        print(f"  ⚠️ 等待超时: {desc}", flush=True)
    return False


async def wait_select_echo(page, selector: str, expected: str,
                           timeout: int = 10000, desc: str = ""):
    """条件等待：locator(selector) 的 innerText 回显包含 expected（ant-select 值生效校验）。"""
    import asyncio
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0:
                txt = (await loc.inner_text()).replace("\n", " ").strip()
                if expected in txt:
                    return True
        except Exception:
            pass
        await page.wait_for_timeout(250)
    if desc:
        print(f"  ⚠️ 等待超时: {desc}", flush=True)
    return False


async def open_page_async():
    """异步打开一个已登录的浏览器页面（持久化 profile），返回 (page, context, playwright)。

    - 二次运行：profile 里已有 GTJA_TOKEN → 直接直开目标页，跳过登录表单（~1.6s）。
    - 首次 / token 过期：自动走登录表单，并刷新 profile。
    - 调用方务必用 `await close_page(ctx, p)` 释放资源。
    """
    from playwright.async_api import async_playwright

    cfg = _load_cfg()
    p = await async_playwright().start()
    ctx = await p.chromium.launch_persistent_context(
        str(PROFILE_DIR), headless=True, viewport={"width": 1920, "height": 1400})
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    # 先到应用域，读 localStorage 判断是否已登录
    await page.goto(cfg["login_url"], wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(300)
    token = ""
    try:
        token = await page.evaluate('localStorage.getItem("GTJA_TOKEN") || ""')
    except Exception:
        pass

    if not token_is_valid(token):
        # 尝试用 session.json 的有效 token 补齐 localStorage
        sess = _read_session()
        if token_is_valid(sess.get("token", "")):
            user_info = sess.get("user_info") or {}
            await page.evaluate("""(o) => {
                localStorage.setItem('GTJA_TOKEN', o.t);
                if (o.u && o.u.token) localStorage.setItem('userInfo', JSON.stringify(o.u));
            }""", {"t": sess["token"], "u": user_info})
            await page.reload(wait_until="domcontentloaded")
        else:
            await _browser_login(page, cfg)
    return page, ctx, p


async def close_page(ctx, p):
    """释放 open_page_async 打开的浏览器资源"""
    for closer in (lambda: ctx.close(), lambda: p.stop()):
        try:
            await closer()
        except Exception:
            pass


def open_page():
    """同步包装 open_page_async（供独立脚本顶层调用），返回 (page, context, playwright)"""
    import asyncio
    return asyncio.run(open_page_async())


if __name__ == "__main__":
    s = get_session()
    print(f"token: {s['token'][:50]}... expires_at={s.get('expires_at')}")
    d = api_post("/demand-service/demandsub/queryDemandsubInfo",
                 {"demandId": "R2608070025", "userId": "020822", "userName": "刘辉"})
    print(f"API 验证: {d['demandId']} {d.get('summary')} 项目={d.get('companyProjectNo')}")
